import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import support
from tests.support import ROOT
from agent_harness.app import build_app
from agent_harness.config import ConfigError, load_config, update_file, word_token
from agent_harness.words import WORDS
from agent_harness.locations import Locations


class ConfigTests(unittest.TestCase):
    def test_first_run_creates_file_with_token_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime" / "config.json"
            cfg = load_config(path)
            self.assertTrue(path.exists())
            self.assertGreaterEqual(len(cfg.token), 20)
            self.assertEqual((cfg.port, cfg.require_token), (8765, True))

    def test_a_missing_empty_or_null_token_is_replaced_and_a_weak_one_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            for stored in ({}, {"token": ""}, {"token": None}, {"token": " " * 20}):
                path.write_text(json.dumps(stored))
                cfg = load_config(path)
                self.assertGreaterEqual(len(cfg.token), 16)
                self.assertEqual(json.loads(path.read_text())["token"], cfg.token)  # and it is saved
            for weak in ("abc", "x" * 15, " " * 8 + "x" * 8, 12345678901234567, ["a" * 20], True):
                path.write_text(json.dumps({"token": weak}))
                with self.assertRaisesRegex(ConfigError, "token"):
                    load_config(path)

    def test_token_is_stable_across_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            first = load_config(path).token
            self.assertEqual(load_config(path).token, first)
            self.assertEqual(json.loads(path.read_text())["token"], first)

    def test_user_edits_are_kept_and_gaps_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"port": 9000, "token": "abc" * 6}))
            cfg = load_config(path)
            self.assertEqual((cfg.port, cfg.token, cfg.host), (9000, "abc" * 6, "0.0.0.0"))

    def test_build_app_twice_keeps_token_and_starts_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            loc = Locations(Path(tmp))
            a = build_app(loc)
            token, count = a.config.token, a.events.count()
            a.close()
            b = build_app(loc)
            self.assertEqual((b.config.token, count), (token, 0))
            b.close()


class BackendConfigTests(unittest.TestCase):
    def load(self, stored):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        path.write_text(stored if isinstance(stored, str) else json.dumps(stored), encoding="utf-8")
        return load_config(path), path

    def test_clean_defaults_give_a_working_ollama_backend_and_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = load_config(path)
            self.assertEqual([(b.id, b.kind, b.url) for b in cfg.backends],
                             [("ollama", "ollama", "http://127.0.0.1:11434")])
            self.assertEqual((cfg.num_ctx, cfg.max_reply_tokens), (8192, 2048))
            self.assertEqual((cfg.timeouts.connect, cfg.timeouts.listing, cfg.timeouts.first_byte,
                              cfg.timeouts.idle, cfg.timeouts.total), (5, 10, 180, 60, 900))
            self.assertEqual(json.loads(path.read_text())["backends"][0]["id"], "ollama")

    def test_partial_timeouts_merge_and_valid_backends_load(self):
        cfg, _ = self.load({"timeouts": {"idle": 5.5},
                            "backends": [{"id": "ollama", "kind": "ollama", "url": "http://h:1/"},
                                         {"id": "cpp_1", "kind": "llamacpp", "url": "https://h:2"}]})
        self.assertEqual((cfg.timeouts.idle, cfg.timeouts.total), (5.5, 900))
        self.assertEqual([b.url for b in cfg.backends], ["http://h:1", "https://h:2"])

    def test_unknown_keys_are_ignored_and_kept(self):
        _, path = self.load({"my_note": {"model": "x"}, "token": "t" * 16})
        self.assertEqual(json.loads(path.read_text())["my_note"], {"model": "x"})

    def test_bad_backend_entries_give_readable_errors(self):
        ok = {"id": "a", "kind": "ollama", "url": "http://h:1"}
        cases = {
            "twice": [ok, dict(ok)],
            "colon": [{**ok, "id": "a:b"}],
            "empty id": [{**ok, "id": ""}],
            "upper id": [{**ok, "id": "A"}],
            "kind": [{**ok, "kind": "vllm"}],
            "no scheme": [{**ok, "url": "127.0.0.1:11434"}],
            "no host": [{**ok, "url": "http://"}],
            "ftp": [{**ok, "url": "ftp://h"}],
            "port out of range": [{**ok, "url": "http://127.0.0.1:99999"}],
            "port not a number": [{**ok, "url": "http://127.0.0.1:abc"}],
            "port zero": [{**ok, "url": "http://127.0.0.1:0"}],
            "space in host": [{**ok, "url": "http://ho st:1"}],
            "path prefix": [{**ok, "url": "http://h:8080/v1"}],
            "not object": ["a"],
        }
        for name, backends in cases.items():
            with self.subTest(name), self.assertRaises(ConfigError) as ctx:
                self.load({"backends": backends})
            self.assertTrue(str(ctx.exception).strip())
        with self.assertRaises(ConfigError):
            self.load({"backends": "ollama"})

    def test_bad_numbers_are_refused(self):
        for key, value in (("num_ctx", -1), ("num_ctx", "big"), ("num_ctx", 1.5), ("max_reply_tokens", 0),
                           ("port", True), ("timeouts", {"idle": -3}), ("timeouts", {"idle": "x"}),
                           ("timeouts", {"total": float("nan")}), ("timeouts", {"idle": float("inf")}),
                           ("num_ctx", float("nan")),
                           ("timeouts", [1]), ("require_token", "false"), ("require_token", 1), ("host", 123),
                           ("host", "  "), ("port", 70000), ("port", 65536), ("max_reply_tokens", 9000),
                           ("num_ctx", 2048)):  # a reply limit that is not smaller than the context

            with self.subTest(key=key, value=value), self.assertRaises(ConfigError):
                self.load({key: value})

    def test_the_reply_limit_must_leave_the_prompt_room_and_the_boundary_is_exact(self):
        from agent_harness.conversation.window import largest_reply
        limit = largest_reply(8192)
        self.assertEqual(self.load({"max_reply_tokens": limit})[0].max_reply_tokens, limit)
        with self.assertRaisesRegex(ConfigError, "too large"):
            self.load({"max_reply_tokens": limit + 1})
        with self.assertRaises(ConfigError):  # smaller than the context, but it would leave the prompt almost nothing
            self.load({"num_ctx": 8192, "max_reply_tokens": 8000})

    def test_malformed_json_gives_a_readable_error(self):
        with self.assertRaisesRegex(ConfigError, "not valid JSON"):
            self.load("{not json")
        with self.assertRaisesRegex(ConfigError, "JSON object"):
            self.load("[1]")


class WordTokenTests(unittest.TestCase):
    def test_the_word_list_is_clean_and_big_enough(self):
        import re
        self.assertEqual(len(WORDS), len(set(WORDS)))
        self.assertTrue(all(re.fullmatch(r"[a-z]{3,8}", w) for w in WORDS))
        self.assertGreaterEqual(len(WORDS), 256)  # five words then carry at least 40 bits

    def test_a_word_token_is_five_listed_words_and_passes_validation(self):
        import re
        seen = set()
        for _ in range(50):
            token = word_token()
            self.assertRegex(token, r"^[a-z]+(-[a-z]+){4}$")
            self.assertTrue(all(w in WORDS for w in token.split("-")))
            self.assertGreaterEqual(len(token), 16)
            seen.add(token)
        self.assertGreater(len(seen), 45)  # random, not a fixed phrase
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"token": word_token()}))
            self.assertGreaterEqual(len(load_config(path).token), 16)

    def test_concurrent_updates_never_corrupt_the_file_or_lose_a_key(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"port": 9100}))
            errors = []

            def hammer(key):
                try:
                    for i in range(120):
                        update_file(path, **{key: i})
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=hammer, args=(k,)) for k in ("a", "b", "c")]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(errors, [])
            stored = json.loads(path.read_text())
            self.assertEqual((stored["port"], stored["a"], stored["b"], stored["c"]), (9100, 119, 119, 119))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["config.json"])

    def test_update_file_changes_only_what_it_is_told_and_leaves_no_scratch_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"port": 9100, "extra": {"keep": True}, "token": "x" * 20}))
            update_file(path, token="y" * 20, default_model="a:b")
            stored = json.loads(path.read_text())
            self.assertEqual((stored["port"], stored["extra"], stored["token"], stored["default_model"]),
                             (9100, {"keep": True}, "y" * 20, "a:b"))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["config.json"])
            path.write_text("{broken")
            with self.assertRaises(ConfigError):
                update_file(path, token="z" * 20)


class EntryPointTests(unittest.TestCase):
    def test_bad_config_prints_a_message_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ROOT / "harness.py", root / "harness.py")
            shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
            (root / "runtime").mkdir()
            (root / "runtime" / "config.json").write_text(
                json.dumps({"backends": [{"id": "a:b", "kind": "ollama", "url": "http://h"}]}))
            done = subprocess.run([sys.executable, "-B", "harness.py", "status"], cwd=root,
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 1)
            self.assertIn("config error", done.stdout)
            self.assertNotIn("Traceback", done.stderr)

    def test_token_words_saves_a_new_easy_token_and_prints_it_and_plain_token_does_not_change_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ROOT / "harness.py", root / "harness.py")
            shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
            (root / "runtime").mkdir()
            old = "old-token-0123456789"
            config = root / "runtime" / "config.json"
            config.write_text(json.dumps({"token": old, "port": 9333}))
            shown = subprocess.run([sys.executable, "-B", "harness.py", "token"], cwd=root, capture_output=True, text=True)
            self.assertIn(old, shown.stdout)
            self.assertEqual(json.loads(config.read_text())["token"], old)  # plain `token` only shows it
            new = subprocess.run([sys.executable, "-B", "harness.py", "token", "--words"], cwd=root,
                                 capture_output=True, text=True)
            self.assertEqual(new.returncode, 0)
            printed = new.stdout.strip().splitlines()[-1]
            stored = json.loads(config.read_text())
            self.assertEqual((stored["token"], stored["port"]), (printed, 9333))
            self.assertRegex(printed, r"^[a-z]+(-[a-z]+){4}$")
            self.assertNotEqual(printed, old)
            self.assertIn("Restart", new.stdout)

    def test_link_prints_login_links_with_the_token_in_the_fragment_and_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ROOT / "harness.py", root / "harness.py")
            shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
            (root / "runtime").mkdir()
            token = "link-test-token-0123456789"
            (root / "runtime" / "config.json").write_text(json.dumps({"token": token, "host": "127.0.0.1", "port": 8123}))
            done = subprocess.run([sys.executable, "-B", "harness.py", "link"], cwd=root, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0)
            self.assertIn(f"http://127.0.0.1:8123/#token={token}", done.stdout)
            self.assertIn("Send them only to your own devices", done.stdout)
            self.assertNotIn("Traceback", done.stderr)

    def test_status_shows_the_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ROOT / "harness.py", root / "harness.py")
            shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
            done = subprocess.run([sys.executable, "-B", "harness.py", "status"], cwd=root, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0)
            self.assertRegex(done.stdout, r"version:\s+[0-9]+[.][0-9]+")

    def test_models_exits_nonzero_when_every_backend_is_down_and_smoke_refuses_a_zero_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ROOT / "harness.py", root / "harness.py")
            shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
            (root / "runtime").mkdir()
            (root / "runtime" / "config.json").write_text(json.dumps(
                {"backends": [{"id": "dead", "kind": "ollama", "url": "http://127.0.0.1:9"}],
                 "timeouts": {"listing": 1, "connect": 1}}))
            models = subprocess.run([sys.executable, "-B", "harness.py", "models"], cwd=root,
                                    capture_output=True, text=True)
            self.assertEqual(models.returncode, 1)
            self.assertIn("dead: UNAVAILABLE", models.stdout)
            smoke = subprocess.run([sys.executable, "-B", "harness.py", "smoke", "dead:m", "hi", "--max-tokens", "0"],
                                   cwd=root, capture_output=True, text=True)
            self.assertEqual(smoke.returncode, 2)
            self.assertIn("at least 1", smoke.stderr)


if __name__ == "__main__":
    unittest.main()
