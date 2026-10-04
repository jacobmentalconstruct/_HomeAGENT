import threading
import unittest

from tests import support  # noqa: F401
from tests.fake_backends import ollama_chunk, ollama_reply
from tests.test_conversation import Base, drain, outcome, watch
from agent_harness.conversation import window
from agent_harness.conversation.generation import GenerationRunner
from agent_harness.conversation.manager import ConversationManager
from agent_harness.conversation.window import (ContextTooLarge, TokenEstimator, budget_tokens, choose_window)

MODEL = "ol:fake:1b"


def msg(text, role="user"):
    return {"role": role, "content": text}


class EstimatorTests(unittest.TestCase):
    def test_before_anything_is_measured_it_uses_the_cautious_default(self):
        e = TokenEstimator()
        self.assertEqual(e.ratio("m"), window.DEFAULT_RATIO)
        self.assertEqual(e.text("m", 350), 100)
        self.assertEqual(e.message("m", msg("x" * 350)), 100 + window.PER_MESSAGE)
        self.assertEqual(e.messages("m", [msg("x" * 350)]), window.BASE + 100 + window.PER_MESSAGE)
        self.assertEqual(e.messages("m", []), window.BASE)

    def test_a_reported_prompt_size_corrects_the_ratio_for_that_model_only(self):
        e = TokenEstimator()
        e.learn("a", 400, 1, 140)  # 140 - base 8 - 1 message of 6 = 126 content tokens
        self.assertAlmostEqual(e.ratio("a"), 400 / 126)
        self.assertEqual(e.ratio("b"), window.DEFAULT_RATIO)
        e.learn("a", 400, 1, 108)  # 94 content tokens: a second sample is blended in, not swapped in
        self.assertAlmostEqual(e.ratio("a"), 0.7 * (400 / 126) + 0.3 * (400 / 94))

    def test_missing_tiny_or_wild_reports_are_ignored_or_clamped(self):
        e = TokenEstimator()
        for args in ((400, 1, None), (400, 1, "many"), (4, 1, 100), (400, 1, 20), (400, 1, 14)):
            e.learn("m", *args)
        self.assertEqual(e.ratio("m"), window.DEFAULT_RATIO)  # nothing usable was learned
        e.learn("m", 100000, 1, 100)  # an absurdly high ratio is clamped, then believed only slowly
        self.assertAlmostEqual(e.ratio("m"), 0.7 * window.DEFAULT_RATIO + 0.3 * 6.0)
        e.learn("low", 100, 1, 5000)  # and so is an absurdly low one
        self.assertEqual(e.ratio("low"), 1.5)


class CautionTests(unittest.TestCase):
    def test_fewer_characters_per_token_is_believed_at_once_and_more_only_slowly(self):
        e = TokenEstimator()
        e.learn("m", 400, 1, 260)  # 246 content tokens: 1.63 characters per token, far below the default
        self.assertAlmostEqual(e.ratio("m"), 400 / 246)
        low = e.ratio("m")
        e.learn("m", 400, 1, 60)  # a suspiciously short count (caching?): moves the ratio up only a little
        self.assertLess(e.ratio("m"), low + 0.3 * (6.0 - low) + 1e-9)
        self.assertGreater(e.ratio("m"), low)

    def test_a_backend_reporting_too_few_tokens_cannot_push_the_estimate_far_below_the_truth(self):
        e = TokenEstimator()
        e.learn("m", 100000, 1, 100)  # one absurd report
        self.assertLess(e.ratio("m"), 4.3)  # the default was 3.5: at most a modest change


class WindowChoiceTests(unittest.TestCase):
    def history(self, n, size=400):
        return [(i, msg("m" * size, "user" if i % 2 == 0 else "assistant")) for i in range(n)]

    def test_budget_leaves_room_for_the_reply_and_a_margin(self):
        self.assertEqual(budget_tokens(8192, 2048), int(8192 * 0.9) - 2048)
        self.assertEqual(budget_tokens(1000, 900), window.MIN_BUDGET)  # never below a floor

    def test_everything_is_sent_when_it_fits(self):
        w = choose_window(self.history(3, 100), "", MODEL, TokenEstimator(), 5000)
        self.assertEqual((w.sent, w.dropped, w.start, len(w.messages)), (3, 0, 0, 3))
        self.assertLess(w.estimated_tokens, 5000)

    def test_a_long_conversation_sends_an_unbroken_run_ending_at_the_newest_message(self):
        history = self.history(51)  # index 50 is a user message: the newest
        e = TokenEstimator()
        w = choose_window(history, "", MODEL, e, 600)
        self.assertLessEqual(w.estimated_tokens, 600)
        self.assertEqual(w.messages[-1], history[-1][1])
        self.assertEqual(w.sent + w.dropped, len(history))
        self.assertEqual(w.start, len(history) - w.sent)  # one unbroken suffix: nothing skipped in the middle
        self.assertEqual(w.sent, 4)
        self.assertEqual(w.estimated_tokens, e.messages(MODEL, w.messages))

    def test_the_system_prompt_goes_first_and_uses_up_budget(self):
        e = TokenEstimator()
        plain = choose_window(self.history(9), "", MODEL, e, 600)
        with_system = choose_window(self.history(9), "s" * 700, MODEL, e, 600)
        self.assertEqual(with_system.messages[0], {"role": "system", "content": "s" * 700})
        self.assertLess(with_system.sent, plain.sent)
        self.assertEqual(with_system.message_count, with_system.sent + 1)

    def test_a_message_too_big_for_the_budget_is_refused_not_cut(self):
        with self.assertRaises(ContextTooLarge) as caught:
            choose_window([(0, msg("w" * 5000))], "", MODEL, TokenEstimator(), 600)
        self.assertGreater(caught.exception.needed, 600)
        self.assertIn("num_ctx", str(caught.exception))

    def test_a_system_prompt_too_big_for_the_budget_blames_the_system_prompt(self):
        with self.assertRaises(ContextTooLarge) as caught:
            choose_window([(0, msg("hi"))], "s" * 5000, MODEL, TokenEstimator(), 600)
        self.assertIn("system prompt", str(caught.exception))
        self.assertNotIn("This message", str(caught.exception))

    def test_an_empty_history_sends_just_the_system_prompt(self):
        w = choose_window([], "be brief", MODEL, TokenEstimator(), 600)
        self.assertEqual((w.sent, w.dropped, len(w.messages)), (0, 0, 1))

    def test_record_holds_what_the_page_and_the_log_need(self):
        w = choose_window(self.history(51), "", MODEL, TokenEstimator(), 600)
        self.assertEqual(set(w.record()), {"start", "sent", "dropped", "estimated_tokens", "budget", "chars", "messages"})


class RunnerWindowTests(Base):
    NUM_CTX, REPLY = 1000, 300  # a budget of 600 tokens

    def runner_for(self, *scripts):
        return self.runner(*scripts, num_ctx=self.NUM_CTX, reply_tokens=self.REPLY)

    def talk(self, runner, conv, texts):
        for text in texts:
            gen = runner.send(conv, text, MODEL)
            self.assertTrue(gen.finished.wait(5))
        return gen

    def test_older_turns_stop_being_sent_but_stay_in_the_record_and_the_reply_says_so(self):
        scripts = [ollama_reply(["r" * 400]) for _ in range(3)]
        fake, runner = self.runner_for(*scripts)
        conv = self.conversations.create()
        self.talk(runner, conv, ["a" * 400, "b" * 400, "c" * 400])
        sent = [m["content"] for m in fake.requests[2]["body"]["messages"]]
        self.assertEqual((len(sent), sent[-1], "a" * 400 in sent), (4, "c" * 400, False))
        self.assertEqual(len(self.conversations.get(conv)["turns"]), 6)  # nothing was lost
        window_record = self.conversations.get(conv)["window"]
        self.assertEqual((window_record["sent"], window_record["dropped"], window_record["start"]), (4, 1, 1))
        self.assertEqual(window_record["budget"], 600)
        assistant = [e for e in self.store.read(conversation_id=conv) if e.kind == "turn.assistant"][-1]
        self.assertEqual(assistant.payload["window"], window_record)

    def test_the_running_message_and_snapshot_carry_the_window(self):
        release = threading.Event()
        fake, runner = self.runner_for([("hold", release)] + ollama_reply(["ok"]))
        conv = self.conversations.create()
        gen = runner.send(conv, "hello", MODEL)
        self.assertTrue(fake.request_seen.wait(5))  # running, held at the backend
        snapshot, q = gen.subscribe()
        self.assertEqual((snapshot["state"], snapshot["window"]["budget"], snapshot["window"]["sent"]),
                         ("running", 600, 1))
        release.set()
        self.assertEqual(drain(q)[-1]["type"], "done")
        self.assertEqual(gen.snapshot()["window"]["sent"], 1)

    def test_a_reported_prompt_size_teaches_the_estimator_and_a_restart_remembers_it(self):
        _fake, runner = self.runner_for(ollama_reply(["ok"], prompt=140))
        conv = self.conversations.create()
        self.talk(runner, conv, ["u" * 400])
        self.assertAlmostEqual(runner.estimator.ratio(MODEL), 400 / 126)
        reborn = GenerationRunner(ConversationManager(self.store), self.registry,
                                  num_ctx=self.NUM_CTX, reply_tokens=self.REPLY)
        self.assertAlmostEqual(reborn.estimator.ratio(MODEL), 400 / 126)  # learned again from the event log

    def test_the_window_start_is_a_turn_index_even_when_a_failed_reply_sits_before_it(self):
        fake, runner = self.runner_for([ollama_chunk("x"), ("reset",)], *[ollama_reply(["r" * 400]) for _ in range(3)])
        conv = self.conversations.create()
        self.talk(runner, conv, ["a" * 400])  # fails: turn 0 is the user, turn 1 the failed reply
        self.talk(runner, conv, ["b" * 400, "c" * 400, "d" * 400])
        record = self.conversations.get(conv)
        turns, w = record["turns"], record["window"]
        sent = [m["content"] for m in fake.requests[-1]["body"]["messages"]]
        self.assertTrue(turns[1]["failed"])
        self.assertEqual((w["sent"], w["dropped"], w["start"]), (len(sent), 2, 3))  # numbered by turn, not position
        self.assertEqual(turns[w["start"]]["text"], sent[0])

    def test_a_backend_that_reports_no_counts_leaves_the_default(self):
        _fake, runner = self.runner_for(ollama_reply(["ok"], prompt=None))
        conv = self.conversations.create()
        self.talk(runner, conv, ["u" * 400])
        self.assertEqual(runner.estimator.ratio(MODEL), window.DEFAULT_RATIO)

    def test_a_message_that_cannot_fit_fails_clearly_without_calling_the_model_and_the_chat_recovers(self):
        fake, runner = self.runner_for(ollama_reply(["fine"]))
        conv = self.conversations.create()
        gen = runner.send(conv, "w" * 5000, MODEL)
        final = outcome(*watch(gen))
        self.assertEqual((final["type"], final["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertEqual(fake.requests, [])  # nothing was sent, and nothing was silently cut
        self.assertIsNone(self.conversations.get(conv)["open_generation"])
        self.talk(runner, conv, ["a short question"])
        sent = [m["content"] for m in fake.requests[0]["body"]["messages"]]
        self.assertEqual(sent, ["a short question"])  # the oversize message does not poison later replies


if __name__ == "__main__":
    unittest.main()
