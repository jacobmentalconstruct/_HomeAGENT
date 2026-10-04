import json
import unittest

from tests import support  # noqa: F401
from tests.fake_backends import FakeBackend
from tests.test_web import Base
from agent_harness.app import build_app
from agent_harness.config import BackendConfig, Timeouts
from agent_harness.models.errors import UnknownModelChoice
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.registry import ModelRegistry
from agent_harness.models.transport import Transport

FAST = Timeouts(connect=1, listing=2, first_byte=2, idle=2, total=5)


class RegistryDefaultTests(unittest.TestCase):
    def registry(self, saved, default="ol:a:1"):
        fake = FakeBackend("ollama", models=("a:1", "b:2", "embed:1"), embedding_models=("embed:1",))
        self.addCleanup(fake.stop)
        backend = OllamaBackend(BackendConfig("ol", "ollama", fake.url), Transport(FAST), 4096, 256)
        return ModelRegistry([backend], default, saved.append), fake

    def test_a_listed_chat_model_becomes_the_default_and_is_saved(self):
        saved = []
        registry, _ = self.registry(saved)
        self.assertEqual(registry.default, "ol:a:1")
        self.assertEqual(registry.set_default("ol:b:2"), "ol:b:2")
        self.assertEqual((registry.default, saved), ("ol:b:2", ["ol:b:2"]))

    def test_anything_else_is_refused_and_changes_nothing(self):
        saved = []
        registry, _ = self.registry(saved)
        for choice in ("ol:embed:1", "ol:ghost:9", "nope:a:1", "ol", ""):
            with self.subTest(choice=choice), self.assertRaises(UnknownModelChoice):
                registry.set_default(choice)
        self.assertEqual((registry.default, saved), ("ol:a:1", []))

    def test_a_failed_save_leaves_the_old_default_in_force(self):
        def broken(_choice):
            raise OSError("disk full")

        registry, _ = self.registry([])
        registry._persist = broken
        with self.assertRaises(OSError):
            registry.set_default("ol:b:2")
        self.assertEqual(registry.default, "ol:a:1")


class DefaultRouteTests(Base):
    def post(self, body, **kw):
        return self.call("POST", "/api/default", body, **kw)

    def test_the_default_can_be_set_shared_saved_and_survives_a_restart(self):
        self.serve()
        self.fake.models.append("other:2b")
        self.assertEqual(self.call("GET", "/api/models").body["default"], "ol:fake:1b")
        self.assertEqual(self.post({"model": "ol:other:2b"}, token=None).status, 401)
        reply = self.post({"model": "ol:other:2b"})
        self.assertEqual((reply.status, reply.body), (200, {"default": "ol:other:2b"}))
        self.assertEqual(self.call("GET", "/api/models").body["default"], "ol:other:2b")
        saved = json.loads(self.loc.config_file.read_text(encoding="utf-8"))
        self.assertEqual((saved["default_model"], saved["token"]), ("ol:other:2b", "t" * 32))  # the rest is kept
        self.app.close()
        again = build_app(self.loc)
        self.addCleanup(again.close)
        self.assertEqual(again.models.default, "ol:other:2b")

    def test_bad_requests_are_refused_and_the_default_stays(self):
        self.serve()
        for body in ({"model": "ol:embed:1"}, {"model": "ol:ghost:9"}, {"model": "nope:x"}, {"model": 5}, {}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status, 400)
        self.assertEqual(self.call("POST", "/api/default", b"{nope").status, 400)
        self.assertEqual(self.call("GET", "/api/models").body["default"], "ol:fake:1b")

    def test_a_failed_save_gives_a_clear_500_without_a_path_and_keeps_the_old_default(self):
        self.serve()
        self.fake.models.append("other:2b")

        def broken(_choice):
            raise OSError("cannot write C" + ":/secret/place/config.json")

        self.app.models._persist = broken
        reply = self.post({"model": "ol:other:2b"})
        self.assertEqual(reply.status, 500)
        self.assertNotIn("secret", json.dumps(reply.body))  # a local path is not sent to the client
        self.assertEqual(self.call("GET", "/api/models").body["default"], "ol:fake:1b")

    def test_a_backend_that_is_down_gives_a_readable_502(self):
        self.serve()
        self.fake.stop()
        reply = self.post({"model": "ol:fake:1b"})
        self.assertEqual(reply.status, 502)
        self.assertTrue(reply.body["error"])

    def test_the_page_offers_the_control_and_marks_the_default(self):
        self.serve()
        page = self.call("GET", "/", token=None).body
        for needed in ("Make the selected model the default", "/api/default", "★"):
            self.assertIn(needed, page)


if __name__ == "__main__":
    unittest.main()
