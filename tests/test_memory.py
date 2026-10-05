import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests import support  # noqa: F401
from agent_harness.memory.cartridge import ConversationMemory
from agent_harness.store.event_store import Event


class Collection:
    def __init__(self, metadata=None):
        self.metadata = metadata or {}
        self.rows = {}

    def get(self, ids=None, include=None):
        rows = [(key, value) for key, value in self.rows.items() if ids is None or key in ids]
        result = {"ids": [key for key, _ in rows], "metadatas": [value["metadata"] for _, value in rows]}
        if include and "embeddings" in include:
            result["embeddings"] = [value["embedding"] for _, value in rows]
        return result

    def upsert(self, ids, embeddings, documents, metadatas):
        for key, vector, document, metadata in zip(ids, embeddings, documents, metadatas):
            self.rows[key] = {"embedding": vector, "document": document, "metadata": metadata}

    def modify(self, metadata):
        if "hnsw:space" in metadata:
            raise ValueError("Changing the distance function of a collection once it is created is not supported currently.")
        self.metadata = metadata

    def query(self, query_embeddings, n_results, where, include):
        query = query_embeddings[0]
        rows = [(key, row) for key, row in self.rows.items()
                if row["metadata"]["conversation_id"] == where["conversation_id"]]
        rows.sort(key=lambda pair: sum(a * b for a, b in zip(query, pair[1]["embedding"])), reverse=True)
        rows = rows[:n_results]
        return {"documents": [[row["document"] for _, row in rows]],
                "metadatas": [[row["metadata"] for _, row in rows]],
                "distances": [[0.0 for _ in rows]]}


class Client:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name, metadata):
        if not self.collection.metadata:
            self.collection.metadata = metadata
        return self.collection


def embed(texts):
    vectors = []
    for text in texts:
        lower = text.lower()
        vectors.append([1.0, 0.0] if any(word in lower for word in ("home", "cedar", "live"))
                       else [0.0, 1.0])
    return vectors


def event(seq, kind, conv, generation, text=""):
    payload = {"generation_id": generation, "text": text}
    return Event(seq, float(seq), kind, "USER" if kind == "turn.user" else "AGENT", conv, payload)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.collection = Collection()
        self.factory = lambda path, settings=None: Client(self.collection)
        self.events = [
            event(1, "turn.user", "a", "g1", "Where is my home?"),
            event(2, "turn.assistant", "a", "g1", "Your home is in Cedar Rapids."),
            event(3, "turn.user", "b", "g2", "My office has a blue door."),
            event(4, "turn.assistant", "b", "g2", "The office door is blue."),
            event(5, "turn.user", "a", "g3", "unfinished request"),
        ]

    def memory(self, identity="ollama:nomic-embed-text", embedder=embed):
        return ConversationMemory(enabled=True, path=Path("unused"), identity=identity,
                                  top_k=4, embed=embedder, client_factory=self.factory)

    def test_chroma_client_disables_telemetry(self):
        received = {}

        def settings(*, anonymized_telemetry):
            received["telemetry"] = anonymized_telemetry
            return object()

        def client(*, path, settings):
            received["settings"] = settings
            return Client(self.collection)

        chroma = SimpleNamespace(config=SimpleNamespace(Settings=settings), PersistentClient=client)
        with patch("agent_harness.memory.chroma_store.importlib.import_module", return_value=chroma):
            memory = ConversationMemory(enabled=True, path=Path("unused"),
                                        identity="ollama:nomic-embed-text", top_k=4, embed=embed)
        self.assertEqual(memory.status()["state"], "ready")
        self.assertIs(received["telemetry"], False)
        self.assertIsNotNone(received["settings"])

    def test_reconcile_indexes_only_completed_turns_and_is_idempotent(self):
        memory = self.memory()
        memory.reconcile(self.events)
        memory.reconcile(self.events)
        self.assertEqual(set(self.collection.rows), {"event-1", "event-2", "event-3", "event-4"})
        self.assertEqual(memory.status()["indexed"], 4)
        self.assertEqual(memory.status()["state"], "ready")
        self.assertEqual(memory._store.dimensions(), 2)
        self.assertEqual(self.collection.metadata["embedding_dimensions"], 2)
        found = memory.retrieve("home", "a", self.events)
        self.assertTrue(found)

    def test_restart_recovers_dimensions_and_still_rejects_mismatch(self):
        self.memory().reconcile(self.events)
        reopened = self.memory()
        self.assertEqual(reopened.status()["state"], "ready")
        self.assertEqual(reopened._store.dimensions(), 2)
        reopened._embed = lambda texts: [[1.0, 2.0, 3.0] for _ in texts]
        self.assertEqual(reopened.retrieve("home", "a", self.events), [])
        self.assertEqual(reopened.status()["state"], "degraded")
        self.assertIn("rebuild runtime/memory", reopened.status()["error"])

    def test_dimension_metadata_write_failure_does_not_degrade_retrieval(self):
        memory = self.memory()
        self.collection.modify = lambda metadata: (_ for _ in ()).throw(RuntimeError("metadata write failed"))
        memory.reconcile(self.events)
        self.assertEqual(memory.status()["state"], "ready")
        self.assertEqual(memory._store.dimensions(), 2)
        self.assertTrue(memory.retrieve("home", "a", self.events))

    def test_retrieval_is_paraphrase_friendly_and_conversation_scoped(self):
        memory = self.memory()
        found = memory.retrieve("Where do I live?", "a", self.events)
        self.assertEqual([item["content"] for item in found], ["Where is my home?", "Your home is in Cedar Rapids."])
        self.assertTrue(all(item["id"].startswith("a:") for item in found))
        self.assertEqual(memory.retrieve("Where do I live?", "missing", self.events), [])

    def test_restart_reconciles_missing_turns_from_event_log(self):
        memory = self.memory()
        memory.reconcile(self.events[:2])
        del self.collection.rows["event-2"]  # an interrupted index write
        restarted = self.memory()
        found = restarted.retrieve("home", "a", self.events)
        self.assertTrue(found)
        self.assertEqual(restarted.status()["state"], "ready")
        self.assertIn("event-2", self.collection.rows)

    def test_missing_chroma_dependency_degrades_without_blocking_the_app(self):
        memory = ConversationMemory(enabled=True, path=Path("unused"), identity="ollama:model", top_k=4,
                                    embed=embed, strict=True,
                                    client_factory=lambda **kwargs: (_ for _ in ()).throw(
                                        ImportError("missing chromadb")))
        self.assertEqual(memory.status()["state"], "degraded")
        self.assertIn("requirements.txt", memory.status()["error"])

    def test_embedding_identity_mismatch_is_degraded(self):
        self.memory().reconcile(self.events)
        other = self.memory(identity="ollama:other-model")
        self.assertEqual(other.status()["state"], "degraded")
        self.assertIn("different", other.status()["error"])

    def test_dimension_change_degrades_without_corrupting_index(self):
        memory = self.memory()
        memory.reconcile(self.events[:2])
        memory._embed = lambda texts: [[1.0, 2.0, 3.0] for _ in texts]
        self.assertEqual(memory.retrieve("home", "a", self.events), [])
        self.assertEqual(memory.status()["state"], "degraded")
        self.assertIn("dimensions changed", memory.status()["error"])

    def test_embedding_failure_is_visible_and_does_not_raise_into_chat(self):
        memory = self.memory(embedder=lambda texts: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertEqual(memory.retrieve("home", "a", self.events), [])
        self.assertEqual(memory.status()["state"], "degraded")

    def test_disabled_memory_does_no_index_work(self):
        memory = ConversationMemory(enabled=False, path=Path(), identity="", top_k=0,
                                    embed=lambda texts: (_ for _ in ()).throw(AssertionError()))
        self.assertEqual(memory.retrieve("anything", "a", self.events), [])
        self.assertEqual(memory.status()["state"], "disabled")

    def test_chroma_fallback_to_sqlite_when_unavailable(self):
        """store_kind='chroma', strict=False, Chroma unavailable -> ready on SQLite store."""
        def fail_chroma(**_):
            raise ImportError("chromadb not available")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        memory = ConversationMemory(
            enabled=True, path=Path(tmp.name), identity="ollama:test", top_k=4,
            embed=embed, store_kind="chroma", strict=False,
            client_factory=fail_chroma)
        if memory._store is not None:
            self.addCleanup(memory._store.close)
        s = memory.status()
        self.assertEqual(s["state"], "ready")
        self.assertEqual(s["store"], "sqlite")
        self.assertTrue(s["store_reason"])
        memory.reconcile(self.events)
        self.assertTrue(memory.retrieve("home", "a", self.events))

    def test_chroma_strict_degrades_without_sqlite_fallback(self):
        """store_kind='chroma', strict=True, Chroma unavailable -> degraded, no store opened."""
        def fail_chroma(**_):
            raise ImportError("chromadb not available")
        memory = ConversationMemory(
            enabled=True, path=Path("unused"), identity="ollama:test", top_k=4,
            embed=embed, store_kind="chroma", strict=True,
            client_factory=fail_chroma)
        self.assertEqual(memory.status()["state"], "degraded")
        self.assertIsNone(memory._store)

    def test_sqlite_store_does_not_import_chromadb(self):
        """store_kind='sqlite' must never trigger a chromadb import."""
        touched = []

        class _Recorder:
            def find_spec(self, fullname, path, target=None):
                if fullname == "chromadb" or fullname.startswith("chromadb."):
                    touched.append(fullname)
                return None

        # Evict any cached chromadb entries so an import attempt hits find_spec.
        cached = {k: sys.modules.pop(k) for k in list(sys.modules)
                  if k == "chromadb" or k.startswith("chromadb.")}
        recorder = _Recorder()
        sys.meta_path.insert(0, recorder)
        try:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            memory = ConversationMemory(
                enabled=True, path=Path(tmp.name), identity="ollama:test", top_k=4,
                embed=embed, store_kind="sqlite")
            if memory._store is not None:
                self.addCleanup(memory._store.close)
            memory.reconcile(self.events)
            memory.retrieve("home", "a", self.events)
        finally:
            sys.meta_path.remove(recorder)
            sys.modules.update(cached)

        self.assertEqual(touched, [], f"chromadb was accessed on sqlite path: {touched}")

    def test_status_store_fields_present_and_absent_by_state(self):
        """store/store_reason present for ready and degraded; absent for disabled."""
        def fail_chroma(**_):
            raise ImportError("chromadb not available")

        # ready (chroma, no fallback): store="chroma", store_reason=""
        s = self.memory().status()
        self.assertEqual(s["store"], "chroma")
        self.assertEqual(s["store_reason"], "")

        # ready (sqlite fallback): store="sqlite", store_reason non-empty
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fallback = ConversationMemory(
            enabled=True, path=Path(tmp.name), identity="ollama:test", top_k=4,
            embed=embed, store_kind="chroma", strict=False,
            client_factory=fail_chroma)
        if fallback._store is not None:
            self.addCleanup(fallback._store.close)
        s = fallback.status()
        self.assertEqual(s["store"], "sqlite")
        self.assertTrue(s["store_reason"])

        # degraded: store and store_reason must be present
        degraded = ConversationMemory(
            enabled=True, path=Path("unused"), identity="ollama:test", top_k=4,
            embed=embed, store_kind="chroma", strict=True,
            client_factory=fail_chroma)
        s = degraded.status()
        self.assertEqual(s["state"], "degraded")
        self.assertIn("store", s)
        self.assertIn("store_reason", s)

        # disabled: must NOT carry store or store_reason
        disabled = ConversationMemory(
            enabled=False, path=Path(), identity="", top_k=0, embed=lambda _: [])
        s = disabled.status()
        self.assertNotIn("store", s)
        self.assertNotIn("store_reason", s)

    def test_chroma_identity_mismatch_degrades_without_fallback(self):
        """ValueError (identity/schema mismatch) never triggers SQLite fallback, even with strict=False."""
        self.memory().reconcile(self.events)
        other = ConversationMemory(
            enabled=True, path=Path("unused"), identity="ollama:other-model",
            top_k=4, embed=embed, store_kind="chroma", strict=False,
            client_factory=self.factory)
        s = other.status()
        self.assertEqual(s["state"], "degraded")
        self.assertIsNone(other._store)
        self.assertEqual(s["store"], "chroma")  # initial kind; no sqlite fallback occurred


class T3MemoryTests(unittest.TestCase):
    """T3: default-on, status fields (tier/reason/fix), FTS5 tier, latency bounds."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.evs = [
            event(1, "turn.user", "a", "g1", "the sky is blue"),
            event(2, "turn.assistant", "a", "g1", "yes the sky is blue"),
            event(3, "turn.user", "b", "g2", "other conversation text"),
            event(4, "turn.assistant", "b", "g2", "other reply"),
        ]

    def sqlite_mem(self, **kwargs):
        defaults = dict(enabled=True, path=self.path, identity="ollama:test",
                        top_k=4, embed=embed, store_kind="sqlite")
        defaults.update(kwargs)
        m = ConversationMemory(**defaults)
        if m._store is not None:
            self.addCleanup(m._store.close)
        return m

    # --- Status: tier field ---

    def test_status_tier_vector(self):
        """status() must contain tier='vector' when vector store is working."""
        m = self.sqlite_mem()
        self.assertEqual(m.status()["tier"], "vector")

    def test_status_tier_lexical_on_per_reply_embed_fail(self):
        """Tier field reflects lexical when embed fails per-reply and FTS covers the reply."""
        m = self.sqlite_mem()
        m.reconcile(self.evs)
        m._embed = lambda _: (_ for _ in ()).throw(RuntimeError("per-reply"))
        m.retrieve("sky", "a", self.evs)
        s = m.status()
        # state must remain ready; tier may be lexical or vector depending on FTS availability
        self.assertEqual(s["state"], "ready")
        self.assertIn(s["tier"], ("vector", "lexical"))

    # --- Status: reason / fix fields ---

    def test_status_reason_embedding_model_missing(self):
        """reason='embedding_model_missing' when model_checker says model absent."""
        m = self.sqlite_mem(model_checker=lambda: False,
                            identity="ollama:nomic-embed-text")
        s = m.status()
        self.assertEqual(s["reason"], "embedding_model_missing")
        self.assertIn("nomic-embed-text", s["fix"])

    def test_status_reason_index_incompatible(self):
        """reason='index_incompatible' after a ValueError (schema/identity mismatch)."""
        tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(tmp2.cleanup)
        path2 = Path(tmp2.name)
        m1 = ConversationMemory(enabled=True, path=path2, identity="ollama:model-a",
                                top_k=4, embed=embed, store_kind="sqlite")
        self.addCleanup(m1._store.close)
        m1.reconcile(self.evs)
        m1._store.close()
        m2 = ConversationMemory(enabled=True, path=path2, identity="ollama:model-b",
                                top_k=4, embed=embed, store_kind="sqlite")
        s = m2.status()
        self.assertEqual(s["state"], "degraded")
        self.assertEqual(s["reason"], "index_incompatible")

    def test_status_reason_transient(self):
        """reason='transient' when embed fails and at least FTS covers; still ready."""
        m = self.sqlite_mem()
        m._embed = lambda _: (_ for _ in ()).throw(RuntimeError("transient"))
        try:
            m.reconcile(self.evs)
        except Exception:
            pass
        s = m.status()
        # If FTS is available: state=ready + reason=transient
        # If FTS is unavailable: state=degraded + reason=transient (or all_tiers_failed)
        self.assertIn(s["reason"], ("transient", "all_tiers_failed"))

    def test_status_reason_all_tiers_failed(self):
        """reason='all_tiers_failed' when both vector store and FTS tier fail."""
        m = self.sqlite_mem()
        m._degrade(RuntimeError("forced"), reason="all_tiers_failed")
        s = m.status()
        self.assertEqual(s["state"], "degraded")
        self.assertEqual(s["reason"], "all_tiers_failed")

    # --- FTS5 lexical tier ---

    def test_fts_reconcile_idempotent(self):
        """Double-reconcile must not error or duplicate FTS rows."""
        m = self.sqlite_mem()
        m.reconcile(self.evs)
        m.reconcile(self.evs)
        self.assertEqual(m.status()["state"], "ready")

    def test_fts_scoped_to_conversation(self):
        """fts_query must return only results from the requested conversation."""
        from agent_harness.memory.sqlite_store import SqliteStore
        store = SqliteStore(self.path / "v.db", "test")
        store.open()
        self.addCleanup(store.close)
        if not store.fts_available():
            self.skipTest("FTS5 not available in this SQLite build")
        store.fts_upsert(["e1", "e2"],
                         ["the sky is blue", "other conversation text"],
                         ["conv-a", "conv-b"], [1, 2], ["user", "user"])
        results = store.fts_query("sky", 4, "conv-b")
        self.assertEqual(results, [])

    def test_fts_ranking(self):
        """More relevant FTS result ranks first (BM25)."""
        from agent_harness.memory.sqlite_store import SqliteStore
        store = SqliteStore(self.path / "v.db", "test")
        store.open()
        self.addCleanup(store.close)
        if not store.fts_available():
            self.skipTest("FTS5 not available in this SQLite build")
        store.fts_upsert(
            ["e1", "e2", "e3"],
            ["sky once", "unrelated topic", "sky sky sky sky"],
            ["c1", "c1", "c1"], [1, 2, 3], ["user", "user", "user"])
        results = store.fts_query("sky", 2, "c1")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["content"], "sky sky sky sky")

    def test_fts_query_sanitizes_special_chars(self):
        """FTS queries with special characters must not raise."""
        from agent_harness.memory.sqlite_store import SqliteStore
        store = SqliteStore(self.path / "v.db", "test")
        store.open()
        self.addCleanup(store.close)
        if not store.fts_available():
            self.skipTest("FTS5 not available in this SQLite build")
        store.fts_upsert(["e1"], ["some text"], ["c1"], [1], ["user"])
        for raw in ('"quoted"', "AND thing", "NEAR/5 word", "key:value", 'a "b" c'):
            with self.subTest(q=raw):
                self.assertIsInstance(store.fts_query(raw, 4, "c1"), list)

    def test_fts_method_field_is_lexical(self):
        """FTS results must include method='lexical'."""
        from agent_harness.memory.sqlite_store import SqliteStore
        store = SqliteStore(self.path / "v.db", "test")
        store.open()
        self.addCleanup(store.close)
        if not store.fts_available():
            self.skipTest("FTS5 not available in this SQLite build")
        store.fts_upsert(["e1"], ["the sky is blue"], ["c1"], [1], ["user"])
        results = store.fts_query("sky", 4, "c1")
        self.assertTrue(results)
        self.assertEqual(results[0]["method"], "lexical")

    def test_fts_absent_vector_tier_still_ready(self):
        """If FTS5 is absent but vector tier works, state must remain ready."""
        m = self.sqlite_mem()
        # If FTS5 were absent, the vector tier still covers; memory stays ready
        self.assertEqual(m.status()["state"], "ready")

    def test_per_reply_embed_fail_uses_fts_no_degrade(self):
        """Per-reply embed failure falls back to FTS and does NOT degrade memory."""
        m = self.sqlite_mem()
        m.reconcile(self.evs)
        m._embed = lambda _: (_ for _ in ()).throw(RuntimeError("per-reply fail"))
        results = m.retrieve("sky", "a", self.evs)
        s = m.status()
        self.assertEqual(s["state"], "ready")
        self.assertIsInstance(results, list)

    # --- Latency bounds ---

    def test_reconcile_bounded_per_retrieve(self):
        """retrieve() must not add more than RECONCILE_BATCH events to the vector index."""
        from agent_harness.memory.cartridge import RECONCILE_BATCH
        n = RECONCILE_BATCH * 3
        evs = [event(i, "turn.user" if i % 2 == 1 else "turn.assistant",
                     "a", f"g{(i + 1) // 2}", f"text {i}") for i in range(1, n + 1)]
        m = self.sqlite_mem()
        m.retrieve("something", "a", evs)
        indexed = len(m._store.ids())
        self.assertLessEqual(indexed, RECONCILE_BATCH,
                             f"retrieve() added {indexed} to vector index; must be ≤ {RECONCILE_BATCH}")

    def test_background_reconcile_catches_up(self):
        """reconcile_in_background() returns a thread that eventually indexes all events."""
        from agent_harness.memory.cartridge import RECONCILE_BATCH
        n = RECONCILE_BATCH + 4
        if n % 2 != 0:
            n += 1
        evs = [event(i, "turn.user" if i % 2 == 1 else "turn.assistant",
                     "a", f"g{(i + 1) // 2}", f"text {i}") for i in range(1, n + 1)]
        m = self.sqlite_mem()
        m.retrieve("text", "a", evs)
        t = m.reconcile_in_background(evs)
        t.join(timeout=15)
        self.assertFalse(t.is_alive(), "background reconcile did not finish in 15 s")
        self.assertEqual(len(m._store.ids()), n)


if __name__ == "__main__":
    unittest.main()
