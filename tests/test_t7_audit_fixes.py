"""T7 pre-merge audit fixes: sentence coverage, control characters in keyword queries, atomic config write, docs."""

import json
import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import support  # noqa: F401
from tests.fake_backends import ollama_reply
from tests.overflow_fixtures import middle_document, script_for
from tests.test_conversation import outcome, watch
from tests.test_t3_repair import MemoryCase, boom
from tests.test_t4_harden import OverflowBase
import agent_harness
from agent_harness import config as config_module
from agent_harness.config import load_config
from agent_harness.conversation.overflow import sentences
from agent_harness.memory.lexical_store import LexicalStore, _sanitize

ROOT = Path(__file__).resolve().parents[1]
MODEL = "ol:fake:1b"
CONTROLS = [chr(c) for c in range(0x20)] + ["\x7f"]


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def newest_changelog_version():
    return re.search(r"(?m)^## (\d+\.\d+\.\d+)", read("CHANGELOG.md")).group(1)


class SentenceCoverageTests(unittest.TestCase):
    def texts(self, text):
        return [text[u.start:u.end] for u in sentences(text)]

    def test_closing_quote_after_a_sentence_stays_with_its_sentence(self):
        self.assertEqual(self.texts('He said "stop." Then left.'), ['He said "stop."', "Then left."])
        self.assertEqual(self.texts("See the note (it is short.) Next one."), ["See the note (it is short.)", "Next one."])
        self.assertEqual(self.texts("It is 'done.' Next."), ["It is 'done.'", "Next."])
        self.assertEqual(self.texts("She asked “why?” Then ‘no.’ End."),
                         ["She asked “why?”", "Then ‘no.’", "End."])
        self.assertEqual(self.texts('Plain. "Quoted!" ) Odd.'), ["Plain.", '"Quoted!"', ") Odd."])

    def test_every_non_whitespace_character_belongs_to_exactly_one_unit(self):
        rng = random.Random(20261005)
        pieces = ["word", "the", "A", "x1", ".", "!", "?", '"', "'", ")", "(", "”", "’", "“", ",", ":",
                  " ", " ", " ", "  ", "\n", "\n\n", "\t", "...", "Mr.", "e.g.", "-", "]", "["]
        for case in range(3000):
            parts = []
            for _ in range(rng.randint(1, 120)):
                if rng.random() < 0.02:
                    parts.append("z" * rng.randint(400, 1700))  # a long unbroken run forces a hard split
                else:
                    parts.append(rng.choice(pieces))
            text = "".join(parts)
            counts = [0] * len(text)
            for unit in sentences(text):
                self.assertLess(unit.start, unit.end)
                self.assertEqual(unit.text, text[unit.start:unit.end].strip())
                for i in range(unit.start, unit.end):
                    counts[i] += 1
            for i, ch in enumerate(text):
                if not ch.isspace():
                    self.assertEqual(counts[i], 1, f"case {case}: char {i} {ch!r} covered {counts[i]} times in {text!r}")


class LexicalSanitizeTests(MemoryCase):
    def test_control_characters_are_stripped_from_queries(self):
        self.assertEqual(_sanitize("a\x00b"), '"ab"')
        self.assertIsNone(_sanitize("\x00"))
        for ch in CONTROLS:
            with self.subTest(ch=repr(ch)):
                cleaned = _sanitize(f"left{ch}right more")
                self.assertTrue(cleaned is None or not any(c in cleaned for c in CONTROLS if c not in " "))
        store = LexicalStore(self.path / "l.sqlite3")
        store.open()
        self.addCleanup(store.close)
        store.upsert([1], ["some text about ab"], ["c"], ["user"])
        for query in ["\x00", "a\x00b", "\x00\x01\x02", "text\x1b[0m", "\x7fsome"] + [f"some{ch}text" for ch in CONTROLS]:
            with self.subTest(query=repr(query)):
                self.assertIsInstance(store.query(query, 4, "c"), list)
        self.assertEqual([r["content"] for r in store.query("a\x00b", 4, "c")], ["some text about ab"])

    def test_a_query_with_control_characters_does_not_flip_the_memory_status(self):
        memory = self.make("sqlite")
        memory.reconcile(self.evs)
        memory._embed = boom
        memory.retrieve("home", "a", self.evs)  # forces the vector tier down; the keyword tier now serves
        before = memory.status()
        self.assertEqual((before["state"], before["tier"]), ("ready", "lexical"))
        for query in ("\x00", "a\x00b", "home\x00", "\x01\x02 home \x1f"):
            with self.subTest(query=repr(query)):
                self.assertIsInstance(memory.retrieve(query, "a", self.evs), list)
                status = memory.status()
                self.assertEqual((status["state"], status["tier"], status["reason"], status["failed_retrievals"]),
                                 ("ready", "lexical", before["reason"], 0))
                self.assertIsNone(memory._lexical_transient)


class AtomicConfigWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "config.json"
        self.original = json.dumps({"port": 9000, "token": "abc" * 6})  # missing keys, so load_config rewrites it
        self.path.write_text(self.original, encoding="utf-8")

    def leftovers(self):
        return sorted(p.name for p in self.dir.iterdir() if p.name != "config.json")

    def test_a_failed_write_leaves_the_old_config_intact(self):
        real_write = Path.write_text

        def partial_write(path, text, *args, **kwargs):
            real_write(path, text[:10], *args, **kwargs)  # half a file reaches the disk, then the disk is full
            raise OSError("disk full")

        with mock.patch.object(Path, "write_text", partial_write), self.assertRaises(OSError):
            load_config(self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.original)
        self.assertEqual(self.leftovers(), [])
        with mock.patch.object(config_module.os, "replace", side_effect=OSError("cannot replace")), \
                self.assertRaises(OSError):
            load_config(self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.original)
        self.assertEqual(self.leftovers(), [])

    def test_a_successful_write_leaves_no_temporary_file(self):
        cfg = load_config(self.path)
        self.assertEqual(cfg.port, 9000)
        self.assertIn("overflow_fallback", json.loads(self.path.read_text(encoding="utf-8")))
        self.assertEqual(self.leftovers(), [])
        fresh = self.dir / "new" / "config.json"
        load_config(fresh)
        self.assertEqual(sorted(p.name for p in fresh.parent.iterdir()), ["config.json"])


class FollowUpWindowTests(OverflowBase):
    def test_a_follow_up_after_a_fallback_reply_sends_neither_the_document_nor_older_turns(self):
        text, fact = middle_document()
        scripts = script_for(text, {"mid-document access code": fact})
        fake, runner = self.overflow_runner(ollama_reply(["Hi there."]), *scripts, ollama_reply(["JUNIPER"]),
                                            ollama_reply(["It was JUNIPER."]))
        conv = self.conversations.create()
        for message in ("hello", text, "what was that code again?"):
            self.assertEqual(outcome(*watch(runner.send(conv, message, MODEL)))["type"], "done")
        sent = fake.requests[-1]["body"]["messages"]
        self.assertEqual([(m["role"], m["content"]) for m in sent],
                         [("assistant", "JUNIPER"), ("user", "what was that code again?")])
        window = self.conversations.get(conv)["window"]
        self.assertGreater(window["dropped"], 0)
        self.assertNotIn("derived", window)


class T7DocsTests(unittest.TestCase):
    def test_readme_and_architecture_describe_follow_ups_after_a_fallback_reply(self):
        for doc in (read("README.md"), read("docs", "ARCHITECTURE.md")):
            lower = " ".join(doc.lower().split())
            self.assertIn("follow-up questions do not see the document or anything older than it", lower)
            self.assertIn("retrieval may help", lower)
            self.assertIn("embedded from its first part only", lower)

    def test_store_reason_is_documented_in_api_and_configuration(self):
        for doc in (read("docs", "API.md"), read("docs", "CONFIGURATION.md")):
            self.assertIn("`store_reason`", doc)

    def test_backlog_lists_the_five_audit_items(self):
        lines = read("docs", "BACKLOG.md").lower().splitlines()
        for words in (("chunked indexing", "long turns"), ("reuse", "derived context", "follow-up"),
                      ("verify_derived", "command"), ("make_server", "derive_context", "complexity"),
                      ("log", "swallowed", "memory")):
            with self.subTest(words=words):
                self.assertTrue(any(all(w in line for w in words) for line in lines), words)


class ReleaseTests(unittest.TestCase):
    def test_version_is_0_2_1(self):
        self.assertEqual(agent_harness.__version__, "0.2.1")
        self.assertEqual(agent_harness.__version__, newest_changelog_version())

    def test_changelog_has_a_0_2_1_entry(self):
        changelog = read("CHANGELOG.md")
        entry = changelog[changelog.index("## 0.2.1"):changelog.index("## 0.2.0")]
        for needle in ("closing quote", "control character", "atomic", "follow-up", "store_reason"):
            self.assertIn(needle, entry)


if __name__ == "__main__":
    unittest.main()
