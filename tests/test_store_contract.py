"""Contract tests: the same assertions run against both vector store backends."""

import tempfile
import unittest
from pathlib import Path

from tests import support  # noqa: F401
from agent_harness.memory.chroma_store import ChromaStore
from agent_harness.memory.sqlite_store import SqliteStore


# ---------------------------------------------------------------------------
# Minimal fake Chroma client (no chromadb package required)
# ---------------------------------------------------------------------------

class _FakeCollection:
    def __init__(self, metadata=None):
        self.metadata = metadata or {}
        self.rows = {}

    def get(self, ids=None, include=None):
        rows = [(k, v) for k, v in self.rows.items() if ids is None or k in ids]
        result = {"ids": [k for k, _ in rows],
                  "metadatas": [v["metadata"] for _, v in rows]}
        if include and "embeddings" in include:
            result["embeddings"] = [v["embedding"] for _, v in rows]
        return result

    def upsert(self, ids, embeddings, documents, metadatas):
        for key, vec, doc, meta in zip(ids, embeddings, documents, metadatas):
            self.rows[key] = {"embedding": vec, "document": doc, "metadata": meta}

    def modify(self, metadata):
        if "hnsw:space" in metadata:
            raise ValueError("Changing the distance function is not supported.")
        self.metadata = metadata

    def query(self, query_embeddings, n_results, where, include):
        q = query_embeddings[0]
        rows = [(k, r) for k, r in self.rows.items()
                if r["metadata"]["conversation_id"] == where["conversation_id"]]
        rows.sort(key=lambda p: sum(a * b for a, b in zip(q, p[1]["embedding"])), reverse=True)
        rows = rows[:n_results]
        return {
            "documents": [[r["document"] for _, r in rows]],
            "metadatas": [[r["metadata"] for _, r in rows]],
            "distances": [[1.0 - sum(a * b for a, b in zip(q, r["embedding"])) for _, r in rows]],
        }


class _FakeClient:
    def __init__(self, collection):
        self._coll = collection

    def get_or_create_collection(self, name, metadata):
        if not self._coll.metadata:
            self._coll.metadata = metadata
        return self._coll


# ---------------------------------------------------------------------------
# Contract mixin — NOT a TestCase; subclasses provide make_store / reopen
# ---------------------------------------------------------------------------

_META_A1 = {"conversation_id": "conv-a", "seq": 1, "role": "user"}
_META_A2 = {"conversation_id": "conv-a", "seq": 2, "role": "assistant"}
_META_B3 = {"conversation_id": "conv-b", "seq": 3, "role": "user"}

_VEC_A = [1.0, 0.0]        # unit vector along x
_VEC_B = [0.0, 1.0]        # unit vector along y (orthogonal)
_VEC_C = [0.7071, 0.7071]  # 45-degree diagonal, approx L2-normalised


class StoreContractMixin:
    """
    Subclasses must implement:
      self.store   — an already-opened store (default identity "ollama:test-model")
      self.reopen(identity="ollama:test-model") -> an already-opened store pointing to the
                                                   same backing storage
    """

    def test_upsert_is_idempotent(self):
        self.store.set_dimensions(2)
        self.store.upsert(["event-1"], [_VEC_A], ["hello"], [_META_A1])
        self.store.upsert(["event-1"], [_VEC_A], ["hello"], [_META_A1])
        self.assertEqual(self.store.ids(), {"event-1"})

    def test_conversation_scoping(self):
        self.store.set_dimensions(2)
        self.store.upsert(["event-1"], [_VEC_A], ["in conv-a"], [_META_A1])
        self.store.upsert(["event-3"], [_VEC_A], ["in conv-b"], [_META_B3])
        results = self.store.query(_VEC_A, 10, "conv-a")
        contents = [r["content"] for r in results]
        self.assertIn("in conv-a", contents)
        self.assertNotIn("in conv-b", contents)
        self.assertTrue(all(r["id"].startswith("conv-a:") for r in results))

    def test_distance_ordering(self):
        self.store.set_dimensions(2)
        self.store.upsert(
            ["event-1", "event-2", "event-3"],
            [_VEC_A, _VEC_B, _VEC_C],
            ["close", "far", "mid"],
            [{"conversation_id": "conv-a", "seq": 1, "role": "user"},
             {"conversation_id": "conv-a", "seq": 2, "role": "user"},
             {"conversation_id": "conv-a", "seq": 3, "role": "user"}])
        results = self.store.query(_VEC_A, 3, "conv-a")
        self.assertEqual([r["content"] for r in results], ["close", "mid", "far"])
        for r in results:
            self.assertGreaterEqual(r["distance"], 0.0)

    def test_reopen_persistence(self):
        self.store.set_dimensions(2)
        self.store.upsert(["event-1"], [_VEC_A], ["persisted"], [_META_A1])
        store2 = self.reopen()
        self.assertIn("event-1", store2.ids())
        self.assertEqual(store2.dimensions(), 2)
        results = store2.query(_VEC_A, 1, "conv-a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "persisted")

    def test_identity_mismatch_raises_on_open(self):
        self.store.set_dimensions(2)
        self.store.upsert(["event-1"], [_VEC_A], ["text"], [_META_A1])
        with self.assertRaises(ValueError) as ctx:
            self.reopen(identity="different:model")
        self.assertIn("rebuild", str(ctx.exception).lower())

    def test_dimension_mismatch_raises(self):
        self.store.set_dimensions(2)
        self.store.upsert(["event-1"], [_VEC_A], ["text"], [_META_A1])
        store2 = self.reopen()
        with self.assertRaises(ValueError) as ctx:
            store2.set_dimensions(3)
        self.assertIn("rebuild", str(ctx.exception).lower())

    def test_missing_id_detection(self):
        self.store.set_dimensions(2)
        self.store.upsert(["event-1", "event-2"], [_VEC_A, _VEC_B], ["a", "b"],
                          [_META_A1, _META_A2])
        all_ids = self.store.ids()
        self.assertIn("event-1", all_ids)
        self.assertIn("event-2", all_ids)
        self.assertNotIn("event-99", all_ids)
        self.assertEqual({"event-99"} - all_ids, {"event-99"})


# ---------------------------------------------------------------------------
# Concrete: SQLite
# ---------------------------------------------------------------------------

class TestSqliteStoreContract(StoreContractMixin, unittest.TestCase):
    _IDENTITY = "ollama:test-model"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = self._make(self._IDENTITY)

    def _make(self, identity):
        s = SqliteStore(Path(self._tmp.name) / "vectors.sqlite3", identity)
        self.addCleanup(s.close)  # registered before open() so it runs even if open() raises midway
        s.open()
        return s

    def reopen(self, identity=None):
        return self._make(identity or self._IDENTITY)


# ---------------------------------------------------------------------------
# Concrete: Chroma (fake client)
# ---------------------------------------------------------------------------

class TestChromaStoreContract(StoreContractMixin, unittest.TestCase):
    _IDENTITY = "ollama:test-model"

    def setUp(self):
        self._coll = _FakeCollection()
        self.store = self._make(self._IDENTITY)

    def _make(self, identity):
        coll = self._coll
        factory = lambda path, settings=None: _FakeClient(coll)
        s = ChromaStore(Path("unused"), identity, client_factory=factory)
        s.open()
        return s

    def reopen(self, identity=None):
        return self._make(identity or self._IDENTITY)


# ---------------------------------------------------------------------------
# Optional: assert real Chroma and SQLite agree on top-k ordering
# ---------------------------------------------------------------------------

try:
    import importlib as _il
    _il.import_module("chromadb")
    _HAS_CHROMADB = True
except ImportError:
    _HAS_CHROMADB = False


@unittest.skipUnless(_HAS_CHROMADB, "chromadb not installed")
class TestRealChromaOrdering(unittest.TestCase):
    """SQLite and real Chroma must agree on top-k ordering for L2-normalised vectors."""

    def test_same_top_k_order(self):
        vecs = [[1.0, 0.0], [0.0, 1.0], [0.7071, 0.7071],
                [0.9239, 0.3827], [0.3827, 0.9239]]
        identity = "ollama:test-order"
        ids = [f"event-{i}" for i in range(len(vecs))]
        docs = [f"doc-{i}" for i in range(len(vecs))]
        metas = [{"conversation_id": "c", "seq": i, "role": "user"} for i in range(len(vecs))]
        query_vec = [1.0, 0.0]

        sq_order = ch_order = None
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            sq = SqliteStore(Path(tmp) / "v.sqlite3", identity)
            sq.open()
            sq.set_dimensions(2)
            sq.upsert(ids, vecs, docs, metas)
            sq_order = [r["seq"] for r in sq.query(query_vec, len(vecs), "c")]
            sq.close()

            ch = ChromaStore(Path(tmp) / "chroma", identity)
            ch.open()
            ch.set_dimensions(2)
            ch.upsert(ids, vecs, docs, metas)
            ch_order = [r["seq"] for r in ch.query(query_vec, len(vecs), "c")]
            ch.close()

        self.assertEqual(sq_order, ch_order)


if __name__ == "__main__":
    unittest.main()
