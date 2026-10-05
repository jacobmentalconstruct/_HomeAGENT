"""T4 Harden: provenance, overflow switch, derived block on the page, docs, memory re-probe, absent dependencies."""

import contextlib
import hashlib
import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import support  # noqa: F401
from tests.fake_backends import FakeBackend, llamacpp_reply, ollama_reply
from tests.live_memory_probe import BACKLOG_QUERY, BACKLOG_SEED
from tests.overflow_fixtures import MAX_REPLY_TOKENS, NUM_CTX, middle_document, primary_document, script_for
from tests.support import blocked_modules
from tests.test_conversation import PATIENT, Base, outcome, watch
from tests.test_memory import embed, event
from tests.test_t3_repair import MemoryCase, boom
from agent_harness.app import build_app
from agent_harness.config import BackendConfig, ConfigError, Timeouts, load_config
from agent_harness.conversation.generation import GenerationRunner
from agent_harness.conversation.manager import ConversationManager
from agent_harness.conversation.provenance import DERIVED_MARKER, verify_derived
from agent_harness.conversation.window import ContextTooLarge, choose_window
from agent_harness.interfaces import control
from agent_harness.locations import Locations
from agent_harness.memory import cartridge
from agent_harness.memory.cartridge import ConversationMemory
from agent_harness.models.errors import BackendError
from agent_harness.models.llamacpp import LlamaCppBackend
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.registry import ModelRegistry
from agent_harness.models.transport import Transport

ROOT = Path(__file__).resolve().parents[1]
MODEL = "ol:fake:1b"
FAST = Timeouts(connect=1, listing=2, first_byte=2, idle=2, total=5)


def msg(text, role="user"):
    return {"role": role, "content": text}


class OverflowBase(Base):
    def overflow_runner(self, *scripts, **kw):
        fake = FakeBackend("ollama", scripts=scripts)
        self.addCleanup(fake.stop)
        backend = OllamaBackend(BackendConfig("ol", "ollama", fake.url), Transport(PATIENT), NUM_CTX,
                                MAX_REPLY_TOKENS)
        self.registry = ModelRegistry([backend])
        return fake, GenerationRunner(self.conversations, self.registry, num_ctx=NUM_CTX,
                                      reply_tokens=MAX_REPLY_TOKENS, **kw)


class DerivedLifetimeTests(OverflowBase):
    def test_derived_context_does_not_outlive_its_reply_across_a_store_reopen(self):
        text, fact = middle_document()
        scripts = script_for(text, {"mid-document access code": fact})
        fake, runner = self.overflow_runner(*scripts, ollama_reply(["JUNIPER"]), ollama_reply(["you are welcome"]))
        conv = self.conversations.create()
        first = runner.send(conv, text, MODEL)
        self.assertEqual(outcome(*watch(first))["type"], "done")
        window = self.conversations.get(conv)["window"]
        derived = window["derived"]
        assistants = [e for e in self.store.read(conversation_id=conv) if e.kind == "turn.assistant"]
        self.assertEqual(assistants[0].payload["window"], window)  # the record lives in the reply's own event

        reopened = ConversationManager(self.store)  # a restart reads the same log
        self.assertEqual(reopened.get(conv)["window"], window)
        turns = reopened.get(conv)["turns"]
        self.assertEqual(turns[0]["text"], text)  # the original message is untouched
        self.assertTrue(all(derived["text"] not in turn["text"] for turn in turns))  # no turn holds derived text

        second = runner.send(conv, "thanks", MODEL)
        self.assertEqual(outcome(*watch(second))["type"], "done")
        self.assertNotIn("derived", self.conversations.get(conv)["window"])  # the next reply starts clean
        self.assertNotIn("derived", ConversationManager(self.store).get(conv)["window"])
        assistants = [e for e in self.store.read(conversation_id=conv) if e.kind == "turn.assistant"]
        self.assertIn("derived", assistants[0].payload["window"])  # still attached to its own reply only
        self.assertNotIn("derived", assistants[1].payload["window"])
        sent = json.dumps(fake.requests[-1]["body"]["messages"])
        self.assertNotIn(derived["text"][:80], sent)  # the follow-up prompt never reused derived text


ORIGINAL = "Head line.\nThe key fact is here.\nTail line.\nQuestion: What is the key fact?"


def hand_built(original=ORIGINAL):
    head_end = original.index("\nThe key")
    mid = (original.index("The key"), original.index("The key") + len("The key fact is here."))
    tail = (original.index("Tail"), original.index("\nQuestion"))
    question = (original.index("Question:"), len(original))
    ranges = [[0, head_end], list(mid), list(tail), list(question)]
    text = "\n".join([original[0:head_end], DERIVED_MARKER, original[mid[0]:mid[1]],
                      original[tail[0]:tail[1]], original[question[0]:]])
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    return {"method": "extractive_map_reduce", "version": 2, "depth": 1, "text": text,
            "sources": [{"event_id": 7, "char_range": r, "source_sha256": digest} for r in ranges]}


class VerifyDerivedTests(OverflowBase):
    def test_a_hand_built_record_verifies(self):
        self.assertEqual(verify_derived(ORIGINAL, hand_built()), [])

    def test_a_real_derived_record_from_the_overflow_path_verifies(self):
        for name, (text, fact) in (("middle", middle_document()),):
            with self.subTest(name=name):
                scripts = script_for(text, {"mid-document access code": fact})
                _fake, runner = self.overflow_runner(*scripts, ollama_reply(["JUNIPER"]))
                conv = self.conversations.create()
                self.assertEqual(outcome(*watch(runner.send(conv, text, MODEL)))["type"], "done")
                derived = self.conversations.get(conv)["window"]["derived"]
                self.assertEqual(verify_derived(text, derived), [])
        text, facts = primary_document()
        scripts = script_for(text, {"opening project marker": facts[0], "hidden project marker": facts[1],
                                    "closing project marker": facts[2]})
        _fake, runner = self.overflow_runner(*scripts, ollama_reply(["COBALT, VIOLET, MARIGOLD"]))
        conv = self.conversations.create()
        self.assertEqual(outcome(*watch(runner.send(conv, text, MODEL)))["type"], "done")
        self.assertEqual(verify_derived(text, self.conversations.get(conv)["window"]["derived"]), [])

    def test_wrong_hash_is_reported(self):
        record = hand_built()
        record["sources"][1]["source_sha256"] = "0" * 64
        self.assertIn("hash_mismatch", verify_derived(ORIGINAL, record))
        self.assertIn("hash_mismatch", verify_derived(ORIGINAL + " edited", hand_built()))  # a changed original

    def test_wrong_range_is_reported(self):
        for name, mutate in (("past the end", lambda r: r["sources"][1].__setitem__("char_range", [10, 9999])),
                             ("empty", lambda r: r["sources"][1].__setitem__("char_range", [20, 20])),
                             ("backwards", lambda r: r["sources"][1].__setitem__("char_range", [30, 12])),
                             ("overlapping", lambda r: r["sources"][2].__setitem__("char_range", [15, 40])),
                             ("not numbers", lambda r: r["sources"][1].__setitem__("char_range", ["a", "b"]))):
            with self.subTest(name=name):
                record = hand_built()
                mutate(record)
                self.assertIn("range_invalid", verify_derived(ORIGINAL, record))

    def test_tampered_text_is_reported(self):
        record = hand_built()
        record["text"] = record["text"].replace("key fact is", "KEY fact is")
        self.assertEqual(verify_derived(ORIGINAL, record), ["text_mismatch"])
        record = hand_built()
        record["text"] = record["text"].replace(DERIVED_MARKER, "[Original text]")
        self.assertIn("text_mismatch", verify_derived(ORIGINAL, record))

    def test_a_missing_or_unknown_record_is_reported(self):
        for bad in (None, "text", 5, []):
            with self.subTest(bad=bad):
                self.assertEqual(verify_derived(ORIGINAL, bad), ["malformed"])
        record = hand_built()
        record["sources"] = []
        self.assertIn("no_sources", verify_derived(ORIGINAL, record))
        record = hand_built()
        record["method"] = "summary"
        self.assertIn("unsupported_method", verify_derived(ORIGINAL, record))
        record = hand_built()
        del record["text"]
        self.assertIn("malformed", verify_derived(ORIGINAL, record))


class OverflowSwitchTests(OverflowBase):
    def load(self, stored):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        path.write_text(json.dumps(stored), encoding="utf-8")
        return load_config(path), path

    def test_default_is_on_and_is_written_to_a_new_config(self):
        cfg, path = self.load({})
        self.assertIs(cfg.overflow_fallback, True)
        self.assertIs(json.loads(path.read_text(encoding="utf-8"))["overflow_fallback"], True)
        cfg, _ = self.load({"overflow_fallback": False})
        self.assertIs(cfg.overflow_fallback, False)

    def test_a_non_boolean_is_refused(self):
        for bad in ("no", 0, 1, None, [], "false"):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                self.load({"overflow_fallback": bad})

    def test_off_gives_todays_context_exceeded_with_the_original_numbers(self):
        text, _facts = primary_document()
        fake, runner = self.overflow_runner(*script_for(text, {}), overflow_fallback=False)
        with self.assertRaises(ContextTooLarge) as expected:
            choose_window([(0, msg(text))], "", MODEL, runner.estimator, runner.budget)
        conv = self.conversations.create()
        result = outcome(*watch(runner.send(conv, text, MODEL)))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertEqual(result["error"]["message"], str(expected.exception))
        self.assertIn("This message needs about", result["error"]["message"])
        self.assertNotIn("Supported fallback shape", result["error"]["message"])
        self.assertEqual(fake.requests, [])  # no extraction call was made
        self.assertNotIn("derived", self.conversations.get(conv).get("window") or {})

    def test_on_is_the_default_and_still_recovers(self):
        text, fact = middle_document()
        _fake, runner = self.overflow_runner(*script_for(text, {"mid-document access code": fact}),
                                             ollama_reply(["JUNIPER"]))
        self.assertTrue(runner.overflow_fallback)
        self.assertEqual(outcome(*watch(runner.send(self.conversations.create(), text, MODEL)))["type"], "done")

    def test_off_does_not_retry_a_backend_context_error(self):
        distractors = [f"Routine archive row {i} contains only unrelated status information." for i in range(35)]
        text = "\n".join(distractors) + "\nQuestion: What is the marker?"
        overflow_error = ("status", 400, "the input length exceeds the context length")
        fake, runner = self.overflow_runner([overflow_error], ollama_reply(["unused"]), overflow_fallback=False)
        result = outcome(*watch(runner.send(self.conversations.create(), text, MODEL)))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertEqual(len(fake.requests), 1)

    def test_build_app_passes_the_switch_to_the_runner(self):
        for value in (True, False):
            with self.subTest(value=value):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                loc = Locations(Path(tmp.name))
                loc.ensure()
                loc.config_file.write_text(json.dumps({"overflow_fallback": value, "memory": {"enabled": False}}))
                app = build_app(loc)
                self.addCleanup(app.close)
                self.assertIs(app.runner.overflow_fallback, value)


NODE_HARNESS = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const script = /<script>([\s\S]*)<\/script>/.exec(html)[1];
const els = {};
function stub(tag) {
  const o = { tag, children: [], style: {}, className: "", _text: "", value: "", options: [], disabled: false,
    classList: { add() {}, remove() {}, toggle() {} }, scrollTop: 0, scrollHeight: 0,
    appendChild(c) { this.children.push(c); return c; }, remove() {}, focus() {}, insertBefore() {},
    addEventListener() {}, requestSubmit() {}, setAttribute(k, v) { this[k] = v; } };
  Object.defineProperty(o, "innerHTML", { set() { throw new Error("innerHTML used"); }, get() { return ""; } });
  Object.defineProperty(o, "textContent", { get() { return this._text; },
    set(v) { this._text = String(v); this.children = []; } });
  return o;
}
const document = { getElementById(id) { return els[id] || (els[id] = stub("#" + id)); },
                   createElement(tag) { return stub(tag); }, querySelectorAll() { return []; } };
const api = new Function("document", "location", "navigator", "localStorage", "history", "window",
  script + "\nreturn { showWindow };")(document,
  { protocol: "file:", hash: "", origin: "", pathname: "", search: "" }, { userAgent: "" },
  { getItem() { return null; }, setItem() {} }, { replaceState() {} }, { innerHeight: 800 });
function walk(e, out) { out.push({ tag: e.tag, text: e._text, open: e.open === undefined ? false : e.open });
                        for (const c of e.children) walk(c, out); return out; }
const base = { estimated_tokens: 10, budget: 100, dropped: 0, sources: [], memory: { state: "ready" } };
api.showWindow({ ...base, derived: { method: "extractive_map_reduce", version: 2, depth: 1,
  text: "SECRET <b>x</b> TEXT",
  sources: [{ event_id: 5, char_range: [0, 10], source_sha256: "ab" }, { event_id: 5, char_range: [20, 40], source_sha256: "ab" }] } });
const withDerived = walk(els.meter, []);
api.showWindow(base);
const without = walk(els.meter, []);
console.log(JSON.stringify({ withDerived, without }));
"""


class PageDerivedTests(unittest.TestCase):
    PAGE = ROOT / "src" / "agent_harness" / "interfaces" / "page.html"

    def test_page_shows_a_collapsed_derived_block_with_source_ranges_using_textcontent(self):
        page = self.PAGE.read_text(encoding="utf-8")
        self.assertIn("w.derived", page)
        self.assertNotIn("innerHTML", page)
        if not shutil.which("node"):
            self.skipTest("node is not installed; only the source-level checks ran")
        with tempfile.TemporaryDirectory() as tmp:
            harness = Path(tmp) / "harness.js"
            harness.write_text(NODE_HARNESS, encoding="utf-8")
            done = subprocess.run(["node", str(harness), str(self.PAGE)], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        nodes = result["withDerived"]
        details = [n for n in nodes if n["tag"] == "details"]
        self.assertEqual(len(details), 1)
        self.assertFalse(details[0]["open"])  # collapsed by default
        self.assertTrue(any(n["tag"] == "summary" for n in nodes))
        self.assertTrue(any(n["text"] == "SECRET <b>x</b> TEXT" for n in nodes))  # shown as text, not parsed
        joined = " ".join(n["text"] for n in nodes)
        self.assertIn("chars 0-10", joined)
        self.assertIn("chars 20-40", joined)
        self.assertEqual([n for n in result["without"] if n["tag"] == "details"], [])

    def test_the_page_script_parses(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        page = self.PAGE.read_text(encoding="utf-8")
        script = re.search(r"<script>(.*)</script>", page, re.S).group(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.js"
            path.write_text(script, encoding="utf-8")
            done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)


class DocsTests(unittest.TestCase):
    def read(self, *parts):
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_readme_explains_the_question_shape_limits_and_failure_behavior(self):
        readme = self.read("README.md")
        for needle in ("Question:", "overflow_fallback", "context_exceeded", "never deleted", "derived"):
            self.assertIn(needle, readme)
        self.assertRegex(readme, r"(?i)limits")
        self.assertRegex(readme, r"(?i)fails? (visibly|with)")

    def test_known_limits_are_documented(self):
        text = self.read("docs", "ARCHITECTURE.md").lower()
        self.assertIn("known limits", text)
        for needle in ("llama.cpp", "reactive", "real llama.cpp server", "line or sentence",
                       "eight", "overlap", "model-call cap"):
            self.assertIn(needle, text)

    def test_dependency_policy_table_lists_every_dependency_and_its_backup(self):
        lines = self.read("docs", "ARCHITECTURE.md").splitlines()
        wanted = (("Chroma", "SQLite vectors"), ("Embeddings", "FTS5"), ("Ollama", "llama.cpp"),
                  ("nvidia-smi", "shows nothing"), ("tkinter", "CLI"))
        for dependency, backup in wanted:
            with self.subTest(dependency=dependency):
                self.assertTrue(any(line.startswith("|") and dependency in line and backup in line for line in lines),
                                f"no table row pairs {dependency} with {backup}")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def join_threads(memory):
    for thread in list(memory._threads):
        thread.join(15)


class ReprobeTests(MemoryCase):
    def test_backoff_schedule_doubles_and_is_capped(self):
        clock = Clock()
        memory = self.make("sqlite", embed=boom, clock=clock)
        memory.reconcile(self.evs)  # the first failure
        seen = [memory.status()["retry_in_seconds"]]
        for _ in range(8):
            clock.t += seen[-1]
            memory.retrieve("home", "a", self.evs)  # due: a background probe runs and fails
            join_threads(memory)
            seen.append(memory.status()["retry_in_seconds"])
        self.assertEqual(seen, [5, 10, 20, 40, 80, 160, 300, 300, 300])
        self.assertEqual((cartridge.PROBE_BASE_SECONDS, cartridge.PROBE_MAX_SECONDS), (5, 300))

    def test_no_vector_attempts_while_backing_off(self):
        calls = []

        def counting(_texts):
            calls.append(1)
            raise RuntimeError("down")

        clock = Clock()
        memory = self.make("sqlite", embed=counting, clock=clock)
        memory.reconcile(self.evs)
        self.assertEqual(len(calls), 1)
        for _ in range(5):
            found = memory.retrieve("home", "a", self.evs)
            self.assertEqual({item["method"] for item in found}, {"lexical"})
        memory.reconcile(self.evs)
        join_threads(memory)
        self.assertEqual(len(calls), 1)  # replies and reconciles made no embedding calls
        clock.t += 4.9
        memory.retrieve("home", "a", self.evs)
        join_threads(memory)
        self.assertEqual(len(calls), 1)
        clock.t += 0.2
        memory.retrieve("home", "a", self.evs)
        join_threads(memory)
        self.assertEqual(len(calls), 2)  # exactly one probe once the delay has passed

    def test_a_due_probe_runs_in_the_background_and_recovers(self):
        up = {"ok": False}

        def flaky(texts):
            if not up["ok"]:
                raise RuntimeError("down")
            return embed(texts)

        clock = Clock()
        memory = self.make("sqlite", embed=flaky, clock=clock)
        memory.reconcile(self.evs)
        self.assertEqual(memory.status()["tier"], "lexical")
        up["ok"] = True
        clock.t += 5
        found = memory.retrieve("home", "a", self.evs)
        self.assertEqual({item["method"] for item in found}, {"lexical"})  # this reply did not wait for the probe
        join_threads(memory)
        status = memory.status()
        self.assertEqual((status["state"], status["tier"], status["reason"]), ("ready", "vector", ""))
        self.assertEqual((status["retry_in_seconds"], status["probe_failures"], status["indexed"]), (0, 0, 4))
        self.assertEqual({item["method"] for item in memory.retrieve("home", "a", self.evs)}, {"vector"})

    def test_at_most_one_probe_runs_and_a_failed_probe_extends_the_backoff(self):
        clock = Clock()
        memory = self.make("sqlite", embed=boom, clock=clock)
        memory.reconcile(self.evs)
        gate, calls = threading.Event(), []

        def slow_failure(_texts):
            calls.append(1)
            gate.wait(5)
            raise RuntimeError("still down")

        memory._embed = slow_failure
        clock.t += 5
        for _ in range(3):
            memory.retrieve("home", "a", self.evs)
        deadline = time.monotonic() + 3
        while not calls and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(calls), 1)  # three due replies, one probe
        gate.set()
        join_threads(memory)
        self.assertEqual(len(calls), 1)
        self.assertEqual(memory.status()["retry_in_seconds"], 10)

    def test_a_successful_probe_does_not_reset_the_backoff_while_the_store_keeps_failing(self):
        clock = Clock()
        memory = self.make("sqlite", clock=clock)  # the embedder works; the vector store's writes fail
        with mock.patch.object(memory._store, "upsert", side_effect=RuntimeError("disk full")):
            memory.reconcile(self.evs)
            delays = [memory.status()["retry_in_seconds"]]
            for _ in range(3):
                clock.t += delays[-1]
                memory.retrieve("home", "a", self.evs)
                join_threads(memory)
                delays.append(memory.status()["retry_in_seconds"])
        self.assertEqual(delays, [5, 10, 20, 40])  # it keeps doubling instead of flapping every 5 s

    def test_status_reports_when_the_next_probe_is_due(self):
        clock = Clock()
        memory = self.make("sqlite", embed=boom, clock=clock)
        self.assertEqual((memory.status()["retry_in_seconds"], memory.status()["probe_failures"]), (0, 0))
        memory.reconcile(self.evs)
        self.assertEqual((memory.status()["retry_in_seconds"], memory.status()["probe_failures"]), (5, 1))
        clock.t += 2
        self.assertEqual(memory.status()["retry_in_seconds"], 3)
        clock.t += 10
        self.assertEqual(memory.status()["retry_in_seconds"], 0)  # due, never negative

    def test_a_reply_does_not_wait_for_a_hung_embedder_while_backing_off(self):
        clock = Clock()
        memory = self.make("sqlite", embed=boom, clock=clock)
        memory.reconcile(self.evs)

        def hung(_texts):
            time.sleep(1.5)
            raise RuntimeError("hung")

        memory._embed = hung
        for label, advance in (("backing off", 0), ("probe due", 5)):
            clock.t += advance
            begun = time.monotonic()
            found = memory.retrieve("home", "a", self.evs)
            self.assertLess(time.monotonic() - begun, 0.5, label)
            self.assertTrue(found, label)
        join_threads(memory)


class AbsentDependencyTests(MemoryCase):
    def test_blocked_modules_hides_and_restores(self):
        import colorsys
        with blocked_modules("colorsys"):
            with self.assertRaises(ImportError):
                importlib.import_module("colorsys")
        self.assertIs(importlib.import_module("colorsys"), colorsys)

    def test_chroma_absent_falls_back_to_sqlite_vectors(self):
        with blocked_modules("chromadb"):
            memory = ConversationMemory(enabled=True, path=self.path / "nochroma", identity="ollama:m", top_k=4,
                                        embed=embed, store_kind="chroma")
            self.addCleanup(memory.close)
            memory.reconcile(self.evs)
            found = memory.retrieve("home", "a", self.evs)
        status = memory.status()
        self.assertEqual((status["state"], status["store"], status["tier"]), ("ready", "sqlite", "vector"))
        self.assertIn("sqlite fallback", status["store_reason"])
        self.assertEqual({item["method"] for item in found}, {"vector"})

    def test_embeddings_absent_falls_back_to_keyword_search(self):
        def unreachable(_texts):
            raise BackendError("unreachable", "Ollama is not running.")

        memory = self.make("sqlite", embed=unreachable)
        found = memory.retrieve("home", "a", self.evs)
        status = memory.status()
        self.assertEqual({item["method"] for item in found}, {"lexical"})
        self.assertEqual((status["state"], status["tier"], status["reason"]),
                         ("ready", "lexical", "embedding_unavailable"))

    def test_ollama_unreachable_llamacpp_backend_still_chats(self):
        down = FakeBackend("ollama")
        down.stop()
        live = FakeBackend("llamacpp", models=("m:1",), scripts=[llamacpp_reply(["from the backup"])])
        self.addCleanup(live.stop)
        registry = ModelRegistry([OllamaBackend(BackendConfig("ol", "ollama", down.url), Transport(FAST), 4096, 256),
                                  LlamaCppBackend(BackendConfig("ll", "llamacpp", live.url), Transport(FAST),
                                                  4096, 256)])
        self.assertEqual({entry.backend_id: entry.available for entry in registry.list_models()},
                         {"ol": False, "ll": True})
        from agent_harness.store.event_store import EventStore
        store = EventStore(self.path.parent / "events.sqlite3")
        self.addCleanup(store.close)
        conversations = ConversationManager(store)
        runner = GenerationRunner(conversations, registry)
        conv = conversations.create()
        gen = runner.send(conv, "hello", "ll:m:1")
        self.assertEqual(outcome(*watch(gen))["type"], "done")
        self.assertEqual(conversations.get(conv)["turns"][-1]["text"], "from the backup")

    def test_nvidia_smi_absent_shows_nothing(self):
        with mock.patch.object(control.subprocess, "run", side_effect=FileNotFoundError("nvidia-smi")):
            self.assertIsNone(control.gpu_memory())

    def test_tkinter_absent_cli_and_server_paths_still_work(self):
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from tests import support\n"
            "import agent_harness.interfaces.cli as cli\n"
            "import agent_harness.interfaces.web, agent_harness.interfaces.control\n"
            "from agent_harness.app import build_app\n"
            "from agent_harness.locations import Locations\n"
            "assert 'tkinter' not in sys.modules, 'cli, web or control imported tkinter'\n"
            "cli.build_app = lambda **kw: build_app(Locations(Path(sys.argv[2])), **kw)\n"
            "sys.exit(cli.main([sys.argv[1]]))\n")
        env = dict(os.environ, AGENT_HARNESS_BLOCK_MODULES="tkinter", PYTHONPATH=str(ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            status = subprocess.run([sys.executable, "-B", "-c", script, "status", tmp], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=60)
            gui = subprocess.run([sys.executable, "-B", "-c", script, "gui", tmp], cwd=ROOT, env=env,
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("events:", status.stdout)
        self.assertEqual(gui.returncode, 1, gui.stderr)
        self.assertIn("tkinter", gui.stdout)
        self.assertIn("python harness.py serve", gui.stdout)
        self.assertNotIn("Traceback", gui.stderr)


class ProbeScriptTests(unittest.TestCase):
    def test_backlog_query_and_seed_share_the_words_home_number(self):
        self.assertIn("home number", BACKLOG_SEED.lower())
        self.assertIn("home number", BACKLOG_QUERY.lower())


if __name__ == "__main__":
    unittest.main()
