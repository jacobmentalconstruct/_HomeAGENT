"""T3 repair: embedding failure handling, independent lexical index, server-owned memory, visibility."""

import contextlib
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import support  # noqa: F401
from tests.fake_backends import FakeBackend
from tests.test_memory import Client, Collection, embed, event
from agent_harness.app import build_app
from agent_harness.interfaces import cli
from agent_harness.locations import Locations
from agent_harness.memory.cartridge import ConversationMemory, describe
from agent_harness.memory.lexical_store import LexicalStore
from agent_harness.memory.sqlite_store import QUERY_SQL, SqliteStore
from agent_harness.models.ollama import has_model

ROOT = Path(__file__).resolve().parents[1]


def boom(_texts):
    raise RuntimeError("offline")


class MemoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "memory"
        self.evs = [
            event(1, "turn.user", "a", "g1", "Where is my home?"),
            event(2, "turn.assistant", "a", "g1", "Your home is in Cedar Rapids."),
            event(3, "turn.user", "b", "g2", "My office has a blue door."),
            event(4, "turn.assistant", "b", "g2", "The office door is blue."),
            event(5, "turn.user", "a", "g3", "unfinished request"),
        ]

    def make(self, kind, sub=None, **kw):
        collection = Collection()
        opts = dict(enabled=True, path=self.path / (sub or kind), identity="ollama:nomic-embed-text",
                    top_k=4, embed=embed, store_kind="sqlite" if kind == "sqlite" else "chroma")
        if kind == "chroma":
            opts["client_factory"] = lambda path, settings=None: Client(collection)
        opts.update(kw)
        memory = ConversationMemory(**opts)
        self.addCleanup(memory.close)
        return memory


class EmbeddingModelNameTests(MemoryCase):
    def test_has_model_treats_a_missing_tag_as_latest(self):
        listed = ["nomic-embed-text:latest", "qwen3.5:9b"]
        self.assertTrue(has_model("nomic-embed-text", listed))
        self.assertTrue(has_model("nomic-embed-text:latest", listed))
        self.assertTrue(has_model("qwen3.5:9b", listed))
        self.assertTrue(has_model("plain", ["plain"]))
        self.assertFalse(has_model("nomic-embed-text:v1.5", listed))
        self.assertFalse(has_model("missing", listed))

    def test_tagged_model_list_does_not_report_lexical_while_vectors_serve(self):
        listed = ["nomic-embed-text:latest"]
        memory = self.make("sqlite", model_checker=lambda: has_model("nomic-embed-text", listed))
        memory.reconcile(self.evs)
        found = memory.retrieve("home", "a", self.evs)
        status = memory.status()
        self.assertEqual((status["state"], status["tier"], status["reason"]), ("ready", "vector", ""))
        self.assertEqual({item["method"] for item in found}, {"vector"})

    def test_tier_follows_what_retrieval_actually_used(self):
        memory = self.make("sqlite")
        memory.reconcile(self.evs)
        working = memory._embed
        memory._embed = boom
        found = memory.retrieve("home", "a", self.evs)
        status = memory.status()
        self.assertEqual({item["method"] for item in found}, {"lexical"})
        self.assertEqual((status["state"], status["tier"], status["reason"]),
                         ("ready", "lexical", "embedding_unavailable"))
        self.assertTrue(status["fix"])
        memory._embed = working
        found = memory.retrieve("home", "a", self.evs)
        status = memory.status()
        self.assertEqual({item["method"] for item in found}, {"vector"})
        self.assertEqual((status["tier"], status["reason"], status["fix"]), ("vector", "", ""))


class ReconcileEmbeddingFailureTests(MemoryCase):
    def check_lexical_ready(self, memory):
        memory.reconcile(self.evs)  # must not raise
        status = memory.status()
        self.assertEqual((status["state"], status["tier"], status["reason"]),
                         ("ready", "lexical", "embedding_unavailable"))
        self.assertTrue(status["fix"])
        self.assertEqual(status["lexical_indexed"], 4)  # FTS indexing continued
        found = memory.retrieve("home", "a", self.evs)
        self.assertTrue(found)
        self.assertEqual({item["method"] for item in found}, {"lexical"})

    def test_embed_error_during_reconcile_keeps_memory_ready_on_both_store_kinds(self):
        for kind in ("sqlite", "chroma"):
            with self.subTest(kind=kind):
                self.check_lexical_ready(self.make(kind, embed=boom))

    def test_embed_error_during_reconcile_with_chromadb_blocked(self):
        with patch("agent_harness.memory.chroma_store.importlib.import_module",
                   side_effect=ImportError("chromadb blocked")):
            memory = ConversationMemory(enabled=True, path=self.path / "blocked", identity="ollama:m",
                                        top_k=4, embed=boom, store_kind="chroma")
        self.addCleanup(memory.close)
        self.assertEqual(memory.status()["store"], "sqlite")
        self.check_lexical_ready(memory)

    def test_retrieve_uses_the_lexical_tier_after_a_reconcile_embed_error(self):
        memory = self.make("sqlite", embed=boom)
        found = memory.retrieve("home", "a", self.evs)  # reconcile runs inside and fails to embed
        self.assertEqual([item["method"] for item in found], ["lexical", "lexical"])
        self.assertEqual(memory.status()["state"], "ready")

    def test_degraded_only_when_every_tier_fails(self):
        with patch.object(LexicalStore, "open", side_effect=RuntimeError("no fts5")):
            memory = self.make("sqlite", sub="nolex", embed=boom)
            memory.reconcile(self.evs)
            status = memory.status()
            self.assertEqual((status["state"], status["reason"]), ("degraded", "all_tiers_failed"))
            self.assertEqual(memory.retrieve("home", "a", self.evs), [])
            working = self.make("sqlite", sub="nolex2")  # vectors alone still count as a working tier
            working.reconcile(self.evs)
            self.assertEqual((working.status()["state"], working.status()["tier"]), ("ready", "vector"))


class BothTiersFailTests(MemoryCase):
    def test_a_reply_where_both_tiers_fail_is_reported_not_silent(self):
        memory = self.make("sqlite")
        memory.reconcile(self.evs)
        memory._embed = boom
        with patch.object(memory._lexical, "query", side_effect=sqlite3.OperationalError("disk I/O error")):
            self.assertEqual(memory.retrieve("home", "a", self.evs), [])
            status = memory.status()
        self.assertEqual(status["failed_retrievals"], 1)
        self.assertTrue(status["last_error"])
        self.assertEqual((status["state"], status["reason"]), ("degraded", "all_tiers_failed"))
        found = memory.retrieve("home", "a", self.evs)  # the lexical tier recovers on its own
        self.assertTrue(found)
        self.assertEqual(memory.status()["state"], "ready")
        self.assertEqual(memory.status()["failed_retrievals"], 1)


class IndependentLexicalIndexTests(MemoryCase):
    def test_default_chroma_configuration_serves_lexical_results_when_embeddings_fail(self):
        memory = self.make("chroma", embed=boom)
        self.assertEqual(memory.status()["store"], "chroma")
        found = memory.retrieve("home", "a", self.evs)
        self.assertTrue(found)
        self.assertEqual({item["method"] for item in found}, {"lexical"})
        self.assertEqual(memory.status()["state"], "ready")

    def test_lexical_index_is_opened_for_every_vector_store(self):
        for kind in ("sqlite", "chroma"):
            with self.subTest(kind=kind):
                self.make(kind)
                self.assertTrue((self.path / kind / "lexical.sqlite3").exists())

    def test_lexical_index_survives_a_failed_vector_store(self):
        memory = self.make("sqlite", sub="mismatch", identity="ollama:a")
        memory.reconcile(self.evs)
        memory.close()
        other = self.make("sqlite", sub="mismatch", identity="ollama:b")
        status = other.status()
        self.assertEqual((status["state"], status["tier"], status["reason"]),
                         ("ready", "lexical", "index_incompatible"))
        self.assertTrue(other.retrieve("home", "a", self.evs))


class LexicalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = LexicalStore(Path(self.tmp.name) / "lexical.sqlite3")
        self.store.open()
        self.addCleanup(self.store.close)

    def test_lexical_distance_is_smaller_is_better_and_score_is_larger_is_better(self):
        self.store.upsert([1, 2, 3], ["sky once", "unrelated topic", "sky sky sky sky"],
                          ["c", "c", "c"], ["user", "user", "user"])
        results = self.store.query("sky", 4, "c")
        self.assertEqual([r["content"] for r in results], ["sky sky sky sky", "sky once"])
        self.assertLess(results[0]["distance"], results[1]["distance"])
        self.assertGreater(results[0]["score"], results[1]["score"])
        self.assertTrue(all(0.0 < r["distance"] <= 1.0 and r["method"] == "lexical" for r in results))

    def test_query_is_scoped_to_the_conversation(self):
        self.store.upsert([1, 2], ["the sky is blue", "other text"], ["a", "b"], ["user", "user"])
        self.assertEqual(self.store.query("sky", 4, "b"), [])
        self.assertEqual(self.store.query("sky", 4, "a")[0]["id"], "a:1")

    def test_operators_quotes_and_colons_in_user_text_do_not_raise(self):
        self.store.upsert([1], ["some text"], ["c"], ["user"])
        for raw in ('"quoted"', "AND thing", "NEAR/5 word", "key:value", 'a "b" c', "", "   ", "***"):
            with self.subTest(raw=raw):
                self.assertIsInstance(self.store.query(raw, 4, "c"), list)

    def test_upsert_is_idempotent_and_survives_reopen(self):
        self.store.upsert([1], ["the sky"], ["c"], ["user"])
        self.store.upsert([1], ["the sky"], ["c"], ["user"])
        self.assertEqual(self.store.seqs(), {1})
        self.assertEqual(len(self.store.query("sky", 4, "c")), 1)
        path = self.store._path
        self.store.close()
        again = LexicalStore(path)
        again.open()
        self.addCleanup(again.close)
        self.assertEqual(again.seqs(), {1})


class SqliteIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "v.sqlite3"

    def plan(self):
        conn = sqlite3.connect(str(self.path))
        try:
            return " ".join(row[-1] for row in conn.execute("EXPLAIN QUERY PLAN " + QUERY_SQL, ("a",)))
        finally:
            conn.close()

    def test_conversation_query_uses_an_index(self):
        store = SqliteStore(self.path, "id")
        store.open()
        self.addCleanup(store.close)
        self.assertIn("idx_vectors_conversation", self.plan())

    def test_existing_database_without_the_index_gets_it_on_reopen(self):
        conn = sqlite3.connect(str(self.path))
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("""CREATE TABLE vectors (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                        seq INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, vector BLOB NOT NULL)""")
        conn.execute("INSERT INTO meta VALUES ('schema', '1')")
        conn.execute("INSERT INTO meta VALUES ('embedding_identity', 'id')")
        conn.execute("INSERT INTO vectors VALUES ('event-1', 'a', 1, 'user', 'hi', x'0000803f')")
        conn.commit()
        conn.close()
        self.assertNotIn("idx_vectors_conversation", self.plan())
        store = SqliteStore(self.path, "id")
        store.open()
        self.addCleanup(store.close)
        self.assertIn("idx_vectors_conversation", self.plan())
        self.assertEqual(store.ids(), {"event-1"})


class AppCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.loc = Locations(Path(self.tmp.name))
        self.loc.ensure()

    def configure(self, models=("nomic-embed-text:latest",), backend_id="ol", memory=None, backends=True):
        self.fake = FakeBackend("ollama", models=models)
        self.addCleanup(self.fake.stop)
        config = {"token": "t" * 32, "host": "127.0.0.1", "default_model": f"{backend_id}:fake:1b",
                  "backends": [{"id": backend_id, "kind": "ollama", "url": self.fake.url}],
                  "memory": {"enabled": True, "embedding_backend": backend_id,
                             "embedding_model": "nomic-embed-text", "store": "sqlite"}}
        config["memory"].update(memory or {})
        self.loc.config_file.write_text(json.dumps(config))

    def seed(self):
        app = build_app(self.loc)
        for seq, (kind, actor, text) in enumerate([("turn.user", "USER", "Where is my home?"),
                                                    ("turn.assistant", "AGENT", "Your home is in Cedar Rapids.")]):
            app.events.append(kind, actor, {"text": text, "generation_id": "g1"}, "c1")
        app.close()


class ServerOwnsMemoryTests(AppCase):
    def test_building_the_app_for_a_non_serve_command_opens_no_store_and_starts_no_thread(self):
        self.configure()
        self.seed()
        before = set(threading.enumerate())
        app = build_app(self.loc)
        self.addCleanup(app.close)
        self.assertEqual(app.memory.status()["state"], "disabled")
        self.assertIsNone(app.memory._store)
        self.assertFalse((self.loc.runtime / "memory").exists())
        self.assertEqual(set(threading.enumerate()) - before, set())

    def test_building_the_app_with_memory_opens_the_stores_and_catches_up_in_the_background(self):
        self.configure()
        self.seed()
        app = build_app(self.loc, with_memory=True)
        self.addCleanup(app.close)
        self.assertEqual(app.memory.status()["state"], "ready")
        self.assertIsNotNone(app.memory._store)
        self.assertTrue((self.loc.runtime / "memory" / "lexical.sqlite3").exists())
        for thread in list(app.memory._threads):
            thread.join(10)
        self.assertEqual(app.memory.status()["indexed"], 2)

    def test_only_serve_builds_the_app_with_memory(self):
        self.configure()
        real = build_app
        flags = {}

        def recording(*args, **kwargs):
            app = real(self.loc, **kwargs)
            flags[self.command] = (kwargs.get("with_memory", False), app.memory.status()["state"])
            return app

        for command in ("status", "models", "token", "link", "unload"):
            self.command = command
            argv = [command]
            with patch.object(cli, "build_app", recording), contextlib.redirect_stdout(io.StringIO()):
                cli.main(argv)
        self.command = "serve"
        with patch.object(cli, "build_app", recording), patch.object(cli, "_serve", return_value=0), \
                contextlib.redirect_stdout(io.StringIO()):
            cli.main(["serve"])
        self.assertEqual({name: flag for name, (flag, _state) in flags.items()},
                         {"status": False, "models": False, "token": False, "link": False,
                          "unload": False, "serve": True})
        self.assertEqual(flags["serve"][1], "ready")
        self.assertTrue(all(state == "disabled" for name, (_f, state) in flags.items() if name != "serve"))

    def test_the_smoke_command_builds_without_memory(self):
        self.configure(models=("fake:1b",))
        seen = {}

        def recording(*args, **kwargs):
            seen["kwargs"] = kwargs
            return build_app(self.loc, **kwargs)

        with patch.object(cli, "build_app", recording), contextlib.redirect_stdout(io.StringIO()):
            cli.main(["smoke", "ol:fake:1b", "hi"])
        self.assertFalse(seen["kwargs"].get("with_memory", False))

    def test_status_command_shows_the_memory_configuration_without_opening_it(self):
        self.configure(memory={"store": "chroma"})
        out = io.StringIO()
        with patch.object(cli, "build_app", lambda *a, **k: build_app(self.loc, **k)), \
                contextlib.redirect_stdout(out):
            cli.main(["status"])
        self.assertIn("memory:", out.getvalue())
        self.assertIn("enabled in config", out.getvalue())
        self.assertIn("chroma", out.getvalue())
        self.assertFalse((self.loc.runtime / "memory").exists())

    def test_status_command_says_how_to_enable_a_disabled_memory(self):
        self.configure(memory={"enabled": False})
        out = io.StringIO()
        with patch.object(cli, "build_app", lambda *a, **k: build_app(self.loc, **k)), \
                contextlib.redirect_stdout(out):
            cli.main(["status"])
        self.assertIn("memory is disabled in config; set memory.enabled to true", out.getvalue())


class AppMemoryStateTests(AppCase):
    def test_a_tagged_ollama_model_list_reports_the_vector_tier(self):
        self.configure(models=("nomic-embed-text:latest",))
        app = build_app(self.loc, with_memory=True)
        self.addCleanup(app.close)
        status = app.memory.status()
        self.assertEqual((status["state"], status["tier"], status["reason"]), ("ready", "vector", ""))

    def test_a_missing_embedding_model_reports_lexical_with_the_pull_command(self):
        self.configure(models=("fake:1b",))
        app = build_app(self.loc, with_memory=True)
        self.addCleanup(app.close)
        status = app.memory.status()
        self.assertEqual((status["state"], status["tier"], status["reason"]),
                         ("ready", "lexical", "embedding_model_missing"))
        self.assertIn("ollama pull nomic-embed-text", status["fix"])

    def test_a_missing_embedding_backend_is_an_explained_lexical_state_not_a_silent_stub(self):
        self.configure(backend_id="other", memory={"embedding_backend": "ollama"})
        app = build_app(self.loc, with_memory=True)
        self.addCleanup(app.close)
        status = app.memory.status()
        self.assertEqual((status["enabled"], status["state"], status["tier"], status["reason"]),
                         (True, "ready", "lexical", "embedding_backend_missing"))
        self.assertIn("ollama", status["fix"])


class VisibilityTests(unittest.TestCase):
    def test_describe_gives_info_for_fallbacks_a_warning_for_degraded_and_a_hint_for_disabled(self):
        level, text = describe({"enabled": False, "state": "disabled", "indexed": 0, "error": ""})
        self.assertEqual(level, "info")
        self.assertIn("memory is disabled in config; set memory.enabled to true", text.lower())
        level, text = describe({"enabled": True, "state": "degraded", "error": "Both failed.",
                                "reason": "all_tiers_failed", "fix": "check Ollama", "tier": "none"})
        self.assertEqual(level, "warning")
        self.assertIn("check Ollama", text)
        level, text = describe({"enabled": True, "state": "ready", "tier": "lexical",
                                "reason": "embedding_model_missing", "fix": "run: ollama pull x",
                                "store_reason": ""})
        self.assertEqual(level, "info")
        self.assertIn("embedding_model_missing", text)
        self.assertIn("ollama pull x", text)
        level, text = describe({"enabled": True, "state": "ready", "tier": "vector", "reason": "", "fix": "",
                                "store_reason": "chroma unavailable (ImportError); using sqlite fallback."})
        self.assertEqual(level, "info")
        self.assertIn("sqlite fallback", text)
        self.assertIsNone(describe({"enabled": True, "state": "ready", "tier": "vector", "reason": "",
                                    "fix": "", "store_reason": ""}))

    def test_the_page_shows_a_memory_note_for_disabled_fallback_and_degraded(self):
        page = (ROOT / "src" / "agent_harness" / "interfaces" / "page.html").read_text(encoding="utf-8")
        self.assertIn('id="memnote"', page)
        self.assertIn("memory.enabled to true", page)
        self.assertNotIn("innerHTML", page)

    def test_requirements_file_says_recommended(self):
        first = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("recommended", first.lower())


if __name__ == "__main__":
    unittest.main()
