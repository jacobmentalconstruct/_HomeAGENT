import threading
import unittest

from tests import support  # noqa: F401
from tests.fake_backends import FakeBackend, ollama_reply
from tests.test_web import Base
from agent_harness.config import BackendConfig, Timeouts
from agent_harness.models.llamacpp import LlamaCppBackend
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.registry import ModelRegistry
from agent_harness.models.transport import Transport

FAST = Timeouts(connect=5, listing=5, first_byte=2, idle=2, total=5)


class LoadedModelsTests(unittest.TestCase):
    def backend(self, cls, fake, ident="b", kind="ollama"):
        return cls(BackendConfig(ident, kind, fake.url), Transport(FAST), 4096, 256)

    def test_ollama_reports_what_it_holds_in_memory_with_sizes(self):
        fake = FakeBackend("ollama", loaded=("big:9b", "small:1b"))
        self.addCleanup(fake.stop)
        self.assertEqual(self.backend(OllamaBackend, fake).loaded_models(),
                         [{"name": "big:9b", "size": 5_000_000_000}, {"name": "small:1b", "size": 5_000_000_000}])

    def test_unload_all_still_returns_the_names_it_released(self):
        fake = FakeBackend("ollama", loaded=("big:9b",))
        self.addCleanup(fake.stop)
        self.assertEqual(self.backend(OllamaBackend, fake).unload_all(), ["big:9b"])
        self.assertEqual(self.backend(OllamaBackend, fake).loaded_models(), [])

    def test_llamacpp_cannot_say_and_reports_nothing(self):
        fake = FakeBackend("llamacpp")
        self.addCleanup(fake.stop)
        self.assertEqual(self.backend(LlamaCppBackend, fake, kind="llamacpp").loaded_models(), [])

    def test_the_registry_reports_each_backend_and_a_failure_as_text(self):
        up = FakeBackend("ollama", loaded=("big:9b",))
        down = FakeBackend("ollama")
        down.stop()
        self.addCleanup(up.stop)
        registry = ModelRegistry([self.backend(OllamaBackend, up, "up"), self.backend(OllamaBackend, down, "down")])
        result = registry.loaded()
        self.assertEqual(result["up"], [{"name": "big:9b", "size": 5_000_000_000}])
        self.assertTrue(result["down"].startswith("unreachable"))


class StatusRouteTests(Base):
    def test_status_needs_the_token_and_reports_the_picture_the_panel_shows(self):
        self.serve()
        self.fake.loaded = ["fake:1b"]
        self.assertEqual(self.call("GET", "/api/status", token=None).status, 401)
        status = self.call("GET", "/api/status").body
        self.assertEqual((status["replies_in_progress"], status["conversations"], status["default_model"]),
                         (0, 0, "ol:fake:1b"))
        self.assertEqual(status["loaded"], {"ol": [{"name": "fake:1b", "size": 5_000_000_000}]})
        self.assertEqual(status["memory"], {"enabled": False, "state": "disabled", "indexed": 0, "error": ""})
        self.assertGreaterEqual(status["uptime_seconds"], 0)

    def test_status_counts_replies_in_progress_and_conversations(self):
        release = threading.Event()
        self.serve([("hold", release)] + ollama_reply(["A"]))
        conv = self.new_conversation()
        self.send(conv)
        self.assertTrue(self.fake.request_seen.wait(5))
        status = self.call("GET", "/api/status").body
        self.assertEqual((status["replies_in_progress"], status["conversations"]), (1, 1))
        release.set()
        self.assertTrue(self.app.runner.get(self.app.conversations.get(conv)["open_generation"]).finished.wait(5))
        self.assertEqual(self.call("GET", "/api/status").body["replies_in_progress"], 0)


if __name__ == "__main__":
    unittest.main()
