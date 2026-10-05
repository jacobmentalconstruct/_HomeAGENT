import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests import support  # noqa: F401
from tests.fake_backends import FakeBackend, ollama_chunk, ollama_reply
from agent_harness.config import BackendConfig, Timeouts
from agent_harness.conversation import generation
from agent_harness.conversation.generation import GenerationRunner
from agent_harness.conversation.manager import Busy, ConversationManager
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.errors import UnknownModelChoice
from agent_harness.models.registry import ModelRegistry
from agent_harness.models.transport import Transport
from agent_harness.store.event_store import EventStore

PATIENT = Timeouts(connect=1, listing=2, first_byte=8, idle=8, total=30)
CHUNKS = ["Hel", "lo ", "wor", "ld"]


def drain(q: queue.Queue) -> list[dict]:
    """Everything a subscriber receives until the end-of-stream marker."""
    out = []
    while True:
        message = q.get(timeout=5)
        if message is None:
            return out
        out.append(message)


def watch(gen) -> tuple[dict, list[dict]]:
    """What a client attaching now sees: the snapshot, then everything after it up to the end.

    A reply that is already over is just its snapshot: nothing more will come, so nothing is waited for."""
    snapshot, q = gen.subscribe()
    return snapshot, (drain(q) if snapshot["state"] in ("queued", "running") else [])


def outcome(snapshot: dict, messages: list[dict]) -> dict:
    """The final word on a reply: its last message, or its snapshot if it was already over when attached."""
    if messages:
        return messages[-1]
    return {"type": snapshot["state"], "error": snapshot["error"], "summary": snapshot["summary"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = EventStore(Path(self.tmp.name) / "e.sqlite3")
        self.addCleanup(self.store.close)
        self.conversations = ConversationManager(self.store)

    def runner(self, *scripts, system_prompt="", **kw):
        fake = FakeBackend("ollama", scripts=list(scripts))
        self.addCleanup(fake.stop)
        backend = OllamaBackend(BackendConfig("ol", "ollama", fake.url), Transport(PATIENT), 4096, 256)
        self.registry = ModelRegistry([backend])
        return fake, GenerationRunner(self.conversations, self.registry, system_prompt=system_prompt, **kw)

    def kinds(self, conversation_id=None):
        return [e.kind for e in self.store.read(conversation_id=conversation_id)]


class ReplyTests(Base):
    def test_event_history_can_be_scoped_to_one_conversation(self):
        first, second = self.conversations.create(), self.conversations.create()
        self.conversations.begin_turn(first, "g1", "one", "ol:fake:1b", "")
        self.conversations.begin_turn(second, "g2", "two", "ol:fake:1b", "")
        self.assertTrue(self.conversations.event_history())
        self.assertEqual({event.conversation_id for event in self.conversations.event_history(first)}, {first})

    def test_reply_streams_is_stored_once_and_survives_a_restart(self):
        _fake, runner = self.runner(ollama_reply(CHUNKS))
        conv = self.conversations.create("phone")
        gen = runner.send(conv, "Say hello", "ol:fake:1b", "phone")
        snapshot, messages = watch(gen)  # the reply may or may not be over by now: both are handled
        self.assertEqual(snapshot["text"] + "".join(m["text"] for m in messages if m["type"] == "delta"),
                         "Hello world")
        self.assertEqual(outcome(snapshot, messages)["type"], "done")
        self.assertEqual(self.kinds(conv).count("turn.assistant"), 1)
        turns = self.conversations.get(conv)["turns"]
        self.assertEqual([(t["role"], t["text"]) for t in turns], [("user", "Say hello"), ("assistant", "Hello world")])
        self.assertEqual(self.conversations.get(conv)["title"], "Say hello")
        reloaded = ConversationManager(self.store)  # a restart reads the same log
        self.assertEqual(reloaded.get(conv)["turns"], turns)
        self.assertEqual([c["id"] for c in reloaded.list()], [conv])

    def test_event_payloads_record_who_what_and_how(self):
        _fake, runner = self.runner(ollama_reply(CHUNKS, done_reason="length", prompt=9, evals=4))
        conv = self.conversations.create()
        gen = runner.send(conv, "hi", "ol:fake:1b", "192.0.2.5")
        gen.finished.wait(5)
        user, assistant = [e for e in self.store.read(conversation_id=conv) if e.kind.startswith("turn.")]
        self.assertEqual((user.actor, user.payload["client"]), ("USER", "192.0.2.5"))
        self.assertEqual((assistant.actor, assistant.payload["model"], assistant.payload["truncated"],
                          assistant.payload["prompt_tokens"], assistant.payload["generation_id"]),
                         ("AGENT", "ol:fake:1b", True, 9, gen.id))

    def test_later_replies_see_earlier_turns_and_the_system_prompt(self):
        fake, runner = self.runner(ollama_reply(["one"]), ollama_reply(["two"]), system_prompt="Be brief.")
        conv = self.conversations.create()
        runner.send(conv, "first", "ol:fake:1b").finished.wait(5)
        runner.send(conv, "second", "ol:fake:1b").finished.wait(5)
        self.assertEqual(fake.requests[1]["body"]["messages"],
                         [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "first"},
                          {"role": "assistant", "content": "one"}, {"role": "user", "content": "second"}])

    def test_retrieved_turn_and_source_reference_reach_the_actual_model_prompt(self):
        class Memory:
            def retrieve(self, query, conversation_id, events):
                return [{"id": f"{conversation_id}:1", "role": "assistant",
                         "content": "The saved project codename is Cedar Lantern.", "distance": 0.08}]

            def status(self):
                return {"enabled": True, "state": "ready", "indexed": 1, "error": ""}

            def reconcile_in_background(self, events):
                import threading
                return threading.Thread(target=lambda: None, daemon=True)

        fake, runner = self.runner(ollama_reply(["first"]), ollama_reply(["recalled"]), memory=Memory())
        conv = self.conversations.create()
        runner.send(conv, "first", "ol:fake:1b").finished.wait(5)
        gen = runner.send(conv, "What was that codename?", "ol:fake:1b")
        self.assertTrue(gen.finished.wait(5))
        sent = fake.requests[-1]["body"]["messages"]
        retrieved = next(m for m in sent if "Retrieved excerpts" in m["content"])
        self.assertIn("Cedar Lantern", retrieved["content"])
        self.assertIn(f"{conv}:1", retrieved["content"])
        self.assertEqual(self.conversations.get(conv)["window"]["sources"][0]["id"], f"{conv}:1")

    def test_degraded_memory_is_reported_while_the_reply_continues(self):
        class Memory:
            def retrieve(self, query, conversation_id, events):
                return []

            def status(self):
                return {"enabled": True, "state": "degraded", "indexed": 0, "error": "Embedding service offline."}

            def reconcile_in_background(self, events):
                import threading
                return threading.Thread(target=lambda: None, daemon=True)

        fake, runner = self.runner(ollama_reply(["ordinary reply"]), memory=Memory())
        conv = self.conversations.create()
        gen = runner.send(conv, "A normal question", "ol:fake:1b")
        self.assertTrue(gen.finished.wait(5))
        self.assertEqual(gen.state, "done")
        self.assertEqual(gen.window["memory"]["state"], "degraded")
        self.assertIn("A normal question", fake.requests[0]["body"]["messages"][-1]["content"])

    def test_unknown_model_and_unknown_conversation_record_nothing(self):
        fake, runner = self.runner(ollama_reply(CHUNKS))
        conv = self.conversations.create()
        before = self.store.count()
        with self.assertRaises(UnknownModelChoice):
            runner.send(conv, "hi", "nope:x")
        with self.assertRaises(KeyError):
            runner.send("missing", "hi", "ol:fake:1b")
        self.assertEqual((self.store.count(), len(fake.requests)), (before, 0))


class RobustnessTests(Base):
    def test_a_failed_write_leaves_the_conversation_usable(self):
        conv = self.conversations.create()
        real = self.store.append
        with mock.patch.object(self.store, "append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.conversations.begin_turn(conv, "g1", "hi", "ol:x", "c")
        self.store.append = real
        self.assertIsNone(self.conversations.get(conv)["open_generation"])  # not stuck busy
        self.conversations.begin_turn(conv, "g2", "hi", "ol:x", "c")

    def test_every_backend_has_its_turnstile_from_the_start(self):
        _fake, runner = self.runner(ollama_reply(CHUNKS))
        self.assertEqual(set(runner._turnstiles), {"ol"})


class OrderingTests(Base):
    def test_requests_to_one_backend_run_in_order_and_the_second_sees_position_one(self):
        release = threading.Event()
        fake, runner = self.runner([("hold", release)] + ollama_reply(["A"]), ollama_reply(["B"]))
        a, b = self.conversations.create(), self.conversations.create()
        first = runner.send(a, "q1", "ol:fake:1b")
        self.assertTrue(fake.request_seen.wait(5))
        second = runner.send(b, "q2", "ol:fake:1b")
        snapshot, q = second.subscribe()
        self.assertEqual((snapshot["state"], snapshot["position"]), ("queued", 1))
        self.assertEqual(len(fake.requests), 1)  # the second has not reached the backend
        release.set()
        messages = drain(q)
        self.assertEqual([m["type"] for m in messages if m["type"] in ("position", "running", "done")],
                         ["running", "done"])  # "running" means its turn came: position 0
        self.assertTrue(first.finished.is_set())
        assistant = [e.conversation_id for e in self.store.read() if e.kind == "turn.assistant"]
        self.assertEqual(assistant, [a, b])

    def test_a_conversation_with_a_reply_in_flight_refuses_another_send(self):
        release = threading.Event()
        fake, runner = self.runner([("hold", release)] + ollama_reply(["A"]), ollama_reply(["B"]))
        conv = self.conversations.create()
        first = runner.send(conv, "q1", "ol:fake:1b")
        self.assertTrue(fake.request_seen.wait(5))
        with self.assertRaises(Busy):
            runner.send(conv, "q2", "ol:fake:1b")
        self.assertEqual(self.kinds(conv).count("turn.user"), 1)  # the refused message was not recorded
        release.set()
        self.assertTrue(first.finished.wait(5))
        runner.send(conv, "q3", "ol:fake:1b").finished.wait(5)
        self.assertEqual(self.kinds(conv).count("turn.assistant"), 2)


class FailureAndClientTests(Base):
    def test_failure_keeps_partial_text_frees_the_conversation_and_the_backend(self):
        fake, runner = self.runner([ollama_chunk("Hel"), ("reset",)], ollama_reply(["fine"]))
        conv = self.conversations.create()
        gen = runner.send(conv, "q1", "ol:fake:1b")
        final = outcome(*watch(gen))
        self.assertEqual(final["type"], "failed")
        self.assertEqual((final["error"]["reason"], final["error"]["partial_text"]), ("connection_reset", "Hel"))
        failed = [e for e in self.store.read(conversation_id=conv) if e.kind == "generation.failed"]
        self.assertEqual((len(failed), failed[0].actor, failed[0].payload["partial_text"]), (1, "SYSTEM", "Hel"))
        turn = self.conversations.get(conv)["turns"][-1]
        self.assertTrue(turn["failed"].startswith("connection_reset"))
        self.assertIsNone(self.conversations.get(conv)["open_generation"])
        runner.send(conv, "q2", "ol:fake:1b").finished.wait(5)  # backend slot was released
        history = self.conversations.history_indexed(conv)
        self.assertEqual([m["content"] for _, m in history], ["q1", "q2", "fine"])  # failed reply left out

    def test_a_client_that_never_listens_does_not_stop_the_reply(self):
        _fake, runner = self.runner(ollama_reply(CHUNKS))
        conv = self.conversations.create()
        gen = runner.send(conv, "q", "ol:fake:1b")  # nobody subscribes
        self.assertTrue(gen.finished.wait(5))
        late_snapshot, q = gen.subscribe()  # a client arriving afterwards still gets the outcome
        self.assertEqual((late_snapshot["state"], late_snapshot["text"]), ("done", "Hello world"))
        self.assertEqual(watch(gen), (late_snapshot, []))  # and has nothing left to wait for
        self.assertEqual(outcome(late_snapshot, [])["type"], "done")
        self.assertEqual(self.conversations.get(conv)["turns"][-1]["text"], "Hello world")

    def test_attaching_mid_reply_gets_the_text_so_far_then_the_rest(self):
        release = threading.Event()
        _fake, runner = self.runner([ollama_chunk("Hel"), ("hold", release)] + ollama_reply(["lo ", "world"])[:-1]
                                    + [ollama_reply(["x"])[-1]])
        conv = self.conversations.create()
        gen = runner.send(conv, "q", "ol:fake:1b")
        _s, early = gen.subscribe()
        while True:  # wait until the first chunk has really arrived
            message = early.get(timeout=5)
            if message["type"] == "delta":
                break
        snapshot, late = gen.subscribe()
        self.assertEqual((snapshot["state"], snapshot["text"]), ("running", "Hel"))
        release.set()
        rest = "".join(m["text"] for m in drain(late) if m["type"] == "delta")
        self.assertEqual(snapshot["text"] + rest, self.conversations.get(conv)["turns"][-1]["text"])
        self.assertEqual(snapshot["text"] + rest, "Hello world")

    def test_a_client_too_slow_to_keep_up_is_dropped_and_the_reply_still_completes(self):
        release = threading.Event()
        with mock.patch.object(generation, "SUBSCRIBER_BUFFER", 2):
            fake, runner = self.runner([("hold", release)] + ollama_reply([f"c{i} " for i in range(12)]))
            conv = self.conversations.create()
            gen = runner.send(conv, "q", "ol:fake:1b")
            self.assertTrue(fake.request_seen.wait(5))  # held at the backend, so the client really attaches mid-reply
            _snapshot, q = gen.subscribe()  # and never reads
            release.set()
            self.assertTrue(gen.finished.wait(5))
        self.assertEqual(self.conversations.get(conv)["turns"][-1]["text"], "".join(f"c{i} " for i in range(12)))
        self.assertLessEqual(q.qsize(), 2)


if __name__ == "__main__":
    unittest.main()
