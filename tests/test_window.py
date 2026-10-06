import threading
import time
import unittest
import hashlib
from unittest import mock

from tests import support  # noqa: F401
from tests.fake_backends import FakeBackend, ollama_chunk, ollama_reply
from tests.test_conversation import PATIENT
from agent_harness.config import BackendConfig, Timeouts
from tests.test_conversation import Base, drain, outcome, watch
from agent_harness.conversation import overflow
from agent_harness.conversation import window
from agent_harness.conversation.generation import GenerationRunner
from agent_harness.conversation.manager import ConversationManager
from agent_harness.conversation.window import (ContextTooLarge, TokenEstimator, budget_tokens, choose_window)
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.llamacpp import LlamaCppBackend
from agent_harness.models.registry import ModelRegistry
from agent_harness.models.transport import Transport
from tests.overflow_fixtures import (CHUNK_SIZE_FRACTION, MAX_REPLY_TOKENS, NUM_CTX, OVERFLOW_CONFIG,
                                     hardwrapped_document, middle_document, negative_document,
                                     primary_document, script_for)

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
        self.assertEqual(caught.exception.what, "system prompt")
        self.assertNotIn("This message", str(caught.exception))

    def test_an_empty_history_sends_just_the_system_prompt(self):
        w = choose_window([], "be brief", MODEL, TokenEstimator(), 600)
        self.assertEqual((w.sent, w.dropped, len(w.messages)), (0, 0, 1))

    def test_record_holds_what_the_page_and_the_log_need(self):
        w = choose_window(self.history(51), "", MODEL, TokenEstimator(), 600)
        self.assertEqual(set(w.record()), {"start", "sent", "dropped", "estimated_tokens", "budget", "chars",
                                           "messages", "sources"})


class RunnerWindowTests(Base):
    NUM_CTX, REPLY = 1000, 300  # a budget of 600 tokens

    def runner_for(self, *scripts):
        return self.runner(*scripts, num_ctx=self.NUM_CTX, reply_tokens=self.REPLY)

    def overflow_runner(self, *scripts):
        fake = FakeBackend("ollama", scripts=scripts)
        self.addCleanup(fake.stop)
        backend = OllamaBackend(BackendConfig("ol", "ollama", fake.url), Transport(PATIENT), NUM_CTX,
                                MAX_REPLY_TOKENS)
        self.registry = ModelRegistry([backend])
        return fake, GenerationRunner(self.conversations, self.registry, num_ctx=NUM_CTX,
                                      reply_tokens=MAX_REPLY_TOKENS)

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

    def test_near_limit_chat_is_sent_unchanged_with_ollama_truncation_disabled(self):
        content = "bounded near-limit request " * 75
        fake, runner = self.runner_for(ollama_reply(["ok"]))
        conv = self.conversations.create()
        gen = runner.send(conv, content, MODEL)
        self.assertEqual(outcome(*watch(gen))["type"], "done")

        sent = fake.requests[0]["body"]
        self.assertIs(sent["truncate"], False)
        self.assertEqual(sent["messages"], [msg(content)])
        window_record = gen.snapshot()["window"]
        self.assertGreater(window_record["estimated_tokens"], window_record["budget"] * 0.95)

    def test_queue_wait_does_not_consume_generation_total_timeout(self):
        release = threading.Event()
        fake = FakeBackend("ollama", scripts=[
            [("hold", release)] + ollama_reply(["first"]),
            ollama_reply(["second"]),
        ])
        self.addCleanup(fake.stop)
        self.addCleanup(release.set)
        timeouts = Timeouts(connect=2, listing=2, first_byte=3, idle=3, total=1)
        backend = OllamaBackend(BackendConfig("ol", "ollama", fake.url), Transport(timeouts), 2048, 256)
        runner = GenerationRunner(self.conversations, ModelRegistry([backend]), num_ctx=2048, reply_tokens=256)
        first = runner.send(self.conversations.create(), "first request", MODEL)
        self.assertTrue(fake.request_seen.wait(3))
        second = runner.send(self.conversations.create(), "queued request", MODEL)

        self.assertTrue(first.finished.wait(3))  # its own one-second deadline expires while the backend is held
        self.assertEqual(first.snapshot()["error"]["reason"], "deadline")
        self.assertTrue(second.finished.wait(3))  # it receives a fresh deadline after acquiring the ticket
        self.assertEqual(second.snapshot()["state"], "done")

    def test_three_facts_are_recovered_with_a_question_focused_bounded_window(self):
        self.assertEqual(OVERFLOW_CONFIG, {"num_ctx": NUM_CTX, "max_reply_tokens": MAX_REPLY_TOKENS,
                                           "chunk_size_fraction": CHUNK_SIZE_FRACTION})
        text, facts = primary_document()
        scripts = script_for(text, {"opening project marker": facts[0],
                                    "hidden project marker": facts[1],
                                    "closing project marker": facts[2]})
        chunk_count = len(scripts)
        release = threading.Event()
        scripts[0] = [("hold", release)] + scripts[0]
        fake, runner = self.overflow_runner(*scripts, ollama_reply(["COBALT, VIOLET, MARIGOLD"]),
                                            ollama_reply(["queued turn finished"]))
        conv = self.conversations.create()
        with self.assertRaises(ContextTooLarge):
            choose_window([(0, msg(text))], "", MODEL, runner.estimator, runner.budget)
        gen = runner.send(conv, text, MODEL)
        self.assertTrue(fake.request_seen.wait(5))
        _snapshot, events = gen.subscribe()
        queued = runner.send(self.conversations.create(), "queued ordinary message", MODEL)
        release.set()
        live = drain(events)
        self.assertEqual(outcome(gen.snapshot(), live)["type"], "done")
        self.assertEqual(outcome(*watch(queued))["type"], "done")
        self.assertGreaterEqual(sum(event["type"] == "progress" for event in live), chunk_count)

        self.assertEqual(fake.requests[-1]["body"]["messages"][-1]["content"], "queued ordinary message")
        self.assertIn("Derived middle", fake.requests[-2]["body"]["messages"][-1]["content"])
        final_prompt = "\n".join(item["content"] for item in fake.requests[-2]["body"]["messages"])
        self.assertTrue(all(fact in final_prompt for fact in facts))
        question = text[text.rfind("Question:"):]
        self.assertIn(question, final_prompt)
        window_record = self.conversations.get(conv)["window"]
        derived = window_record["derived"]
        self.assertEqual((derived["method"], derived["version"]), ("extractive_map_reduce", 2))
        self.assertGreaterEqual(derived["depth"], 1)
        self.assertLessEqual(derived["depth"], overflow.MAX_DEPTH)
        self.assertEqual(derived["text"], fake.requests[-2]["body"]["messages"][-1]["content"])
        source = next(event for event in self.store.read(conversation_id=conv) if event.kind == "turn.user")
        self.assertTrue(all(entry["event_id"] == source.seq for entry in derived["sources"]))
        self.assertTrue(all(entry["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()
                            for entry in derived["sources"]))
        self.assertTrue(all(any(fact in text[s["char_range"][0]:s["char_range"][1]] for s in derived["sources"])
                            for fact in facts))
        extractor_calls = [request for request in fake.requests
                           if "copying tool" in request["body"]["messages"][0]["content"]]
        self.assertLessEqual(len(extractor_calls), overflow.MAX_MODEL_CALLS)

    def test_mid_document_fact_among_distractors_is_retained(self):
        text, fact = middle_document()
        scripts = script_for(text, {"mid-document access code": fact})
        fake, runner = self.overflow_runner(*scripts, ollama_reply(["JUNIPER"]))
        gen = runner.send(self.conversations.create(), text, MODEL)
        self.assertEqual(outcome(*watch(gen))["type"], "done")
        self.assertIn(fact, fake.requests[-1]["body"]["messages"][-1]["content"])

    def test_hardwrapped_unpunctuated_fixture_uses_exact_source_spans(self):
        text, fact = hardwrapped_document()
        scripts = script_for(text, {"hidden access code": fact})
        fake, runner = self.overflow_runner(*scripts, ollama_reply(["SILVER FERN"]))
        gen = runner.send(self.conversations.create(), text, MODEL)
        self.assertEqual(outcome(*watch(gen))["type"], "done")
        self.assertIn(fact, fake.requests[-1]["body"]["messages"][-1]["content"])
        question_range = gen.snapshot()["window"]["derived"]["sources"][-1]["char_range"]
        self.assertEqual(text[slice(*question_range)], text[text.index("Question:"):])

    def test_span_validation_normalizes_whitespace_and_merges_overlap(self):
        source = "one\n  exact   source\tspan\nnext"
        span = overflow.find_exact_span(source, "exact source span")
        self.assertIsNotNone(span)
        self.assertEqual(overflow.normalize_sentence(source[slice(*span)]), "exact source span")
        units = overflow.sentences("alpha\nbeta\ngamma")
        merged = overflow.snap_and_merge([(0, 7), (5, 13)], units)
        self.assertEqual([(item.start, item.end) for item in merged], [(0, 16)])

    def test_chunks_overlap_by_about_twelve_percent(self):
        items = [overflow.Sentence(i * 10, i * 10 + 10, "x" * 10) for i in range(30)]
        parts = overflow.chunks(items, 100)
        overlap = len(set(item.start for item in parts[0]) & set(item.start for item in parts[1]))
        self.assertGreaterEqual(overlap / len(parts[0]), 0.10)
        self.assertLessEqual(overlap / len(parts[0]), 0.15)

    def test_chunks_measure_empty_merged_spans_by_offsets(self):
        spans = [overflow.Sentence(i * 77, (i + 1) * 77, "") for i in range(20)]
        parts = overflow.chunks(spans, 500)
        self.assertEqual(sum(span.end - span.start for span in spans), 1540)
        self.assertEqual(len(parts), 4)
        self.assertTrue(all(sum(span.end - span.start for span in part) <= 500 for part in parts))

    def test_oversized_merged_span_is_restored_to_source_units_before_chunking(self):
        units = [overflow.Sentence(i * 100, (i + 1) * 100, "x" * 100) for i in range(10)]
        merged = [overflow.Sentence(0, 1000, "")]
        parts = overflow.chunks(merged, 250, units=units)
        self.assertGreaterEqual(len(parts), 4)
        self.assertTrue(all(sum(unit.end - unit.start for unit in part) <= 250 for part in parts))
        self.assertEqual({unit.start for part in parts for unit in part}, {unit.start for unit in units})

    def test_recursive_reduction_splits_first_pass_selection_into_multiple_chunks(self):
        text, facts = primary_document()
        payload = text[:text.rfind("Question:")].rstrip()
        estimator = TokenEstimator()
        budget = budget_tokens(NUM_CTX, MAX_REPLY_TOKENS)
        head, tail = overflow.keep_ends(payload, MODEL, estimator, budget)
        protected = {item.start for item in head + tail}
        middle = [item for item in overflow.sentences(payload) if item.start not in protected]
        max_chars = int(NUM_CTX * CHUNK_SIZE_FRACTION * estimator.ratio(MODEL))
        parts = overflow.chunks(middle, max_chars)
        units = overflow.sentences(payload)
        selected = overflow.snap_and_merge([(middle[0].start, middle[-1].end)], units)
        reduce_parts = overflow.chunks(selected, max_chars, units=units)
        self.assertGreaterEqual(len(reduce_parts), 2)
        scripts = [ollama_reply(["\n".join(item.text for item in part)]) for part in parts]
        scripts.extend(ollama_reply([facts[1] if any(facts[1] in item.text for item in part) else "NONE"])
                       for part in reduce_parts)
        scripts.append(ollama_reply(["VIOLET"]))
        fake, runner = self.overflow_runner(*scripts)
        gen = runner.send(self.conversations.create(), text, MODEL)
        self.assertEqual(outcome(*watch(gen))["type"], "done")
        derived = gen.snapshot()["window"]["derived"]
        self.assertEqual(derived["depth"], 2)
        self.assertLessEqual(derived["depth"], overflow.MAX_DEPTH)
        extractor_calls = [request for request in fake.requests
                           if "copying tool" in request["body"]["messages"][0]["content"]]
        self.assertEqual(len(extractor_calls), len(parts) + len(reduce_parts))
        self.assertIn(facts[1], fake.requests[-1]["body"]["messages"][-1]["content"])

    def test_non_shrinking_reduction_fails_closed(self):
        text, _facts = primary_document()
        payload = text[:text.rfind("Question:")].rstrip()
        estimator = TokenEstimator()
        budget = budget_tokens(NUM_CTX, MAX_REPLY_TOKENS)
        head, tail = overflow.keep_ends(payload, MODEL, estimator, budget)
        protected = {item.start for item in head + tail}
        middle = [item for item in overflow.sentences(payload) if item.start not in protected]
        max_chars = int(NUM_CTX * CHUNK_SIZE_FRACTION * estimator.ratio(MODEL))
        parts = overflow.chunks(middle, max_chars)
        units = overflow.sentences(payload)
        selected = overflow.snap_and_merge([(middle[0].start, middle[-1].end)], units)
        reduce_parts = overflow.chunks(selected, max_chars, units=units)
        scripts = [ollama_reply(["\n".join(item.text for item in part)]) for part in parts]
        scripts.extend(ollama_reply(["\n".join(item.text for item in part)]) for part in reduce_parts)
        fake, runner = self.overflow_runner(*scripts)
        result = outcome(*watch(runner.send(self.conversations.create(), text, MODEL)))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertIn("did not strictly shrink", result["error"]["message"])
        self.assertEqual(len(fake.requests), len(parts) + len(reduce_parts))

    def test_total_extraction_model_call_cap_fails_closed(self):
        text, _facts = primary_document()
        fake, runner = self.overflow_runner(ollama_reply(["unused"]))
        with mock.patch.object(overflow, "MAX_MODEL_CALLS", 0):
            gen = runner.send(self.conversations.create(), text, MODEL)
            result = outcome(*watch(gen))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertIn("model-call limit", result["error"]["message"])
        self.assertEqual(fake.requests, [])

    def test_extraction_refuses_documents_that_exceed_the_chunk_cap(self):
        text = "\n".join(f"Unrelated archive item {i} records routine status without a project fact."
                         for i in range(500)) + "\nQuestion: What fact is recorded?"
        fake, runner = self.overflow_runner(ollama_reply(["unused"]))
        gen = runner.send(self.conversations.create(), text, MODEL)
        result = outcome(*watch(gen))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertEqual(fake.requests, [])

    def test_context_diagnostic_is_preserved_with_supported_question_shape_hint(self):
        fake, runner = self.overflow_runner()
        conv = self.conversations.create()
        gen = runner.send(conv, "a very large message with no parsed question " * 500, MODEL)
        result = outcome(*watch(gen))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertIn("This message needs about", result["error"]["message"])
        self.assertIn("at most", result["error"]["message"])
        self.assertIn("fit in the model's context", result["error"]["message"])
        self.assertIn("final explicit Question: section", result["error"]["message"])
        self.assertEqual(fake.requests, [])

    def test_oversized_system_prompt_fails_before_retrieval_or_backend_call(self):
        fake = FakeBackend("ollama")
        self.addCleanup(fake.stop)
        backend = OllamaBackend(BackendConfig("ol", "ollama", fake.url), Transport(PATIENT), NUM_CTX, 256)
        runner = GenerationRunner(self.conversations, ModelRegistry([backend]),
                                  system_prompt="system " * 1000, num_ctx=NUM_CTX, reply_tokens=256)
        class MemorySpy:
            def retrieve(self, *args):
                raise AssertionError("retrieval must not run for an oversized system prompt")
        runner.memory = MemorySpy()
        gen = runner.send(self.conversations.create(), "ordinary message", MODEL)
        result = outcome(*watch(gen))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertIn("system prompt alone needs", result["error"]["message"])
        self.assertEqual(fake.requests, [])

    def test_oversized_retrieval_uses_only_bounded_question_query(self):
        text, _facts = primary_document()
        fake, runner = self.overflow_runner(*script_for(text, {}))
        class MemorySpy:
            query = None
            def retrieve(self, query, _conversation_id, _events):
                self.query = query
                return []
        spy = MemorySpy()
        runner.memory = spy
        gen = runner.send(self.conversations.create(), text, MODEL)
        outcome(*watch(gen))
        self.assertIsNotNone(spy.query)
        self.assertTrue(spy.query.startswith("Question:"))
        self.assertLess(len(spy.query), len(text) // 3)

    def test_reactive_context_retry_is_not_enabled_for_llamacpp(self):
        fake = FakeBackend("llamacpp", scripts=[[('status', 400, 'context length exceeded')]])
        self.addCleanup(fake.stop)
        backend = LlamaCppBackend(BackendConfig("ll", "llamacpp", fake.url), Transport(PATIENT),
                                  NUM_CTX, MAX_REPLY_TOKENS)
        runner = GenerationRunner(self.conversations, ModelRegistry([backend]), num_ctx=NUM_CTX,
                                  reply_tokens=MAX_REPLY_TOKENS)
        gen = runner.send(self.conversations.create(), "short question", "ll:m:1")
        result = outcome(*watch(gen))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertEqual(len(fake.requests), 1)

    def test_reactive_context_error_retries_once_through_fallback(self):
        distractors = [f"Routine archive row {i} contains only unrelated status information."
                       for i in range(35)]
        fact = "The reactive fallback marker is AMBER."
        payload = "\n".join([*distractors[:17], fact, *distractors[17:]])
        text = payload + "\nQuestion: What is the reactive fallback marker?"
        self.assertLessEqual(TokenEstimator().messages(MODEL, [msg(text)]), budget_tokens(NUM_CTX, MAX_REPLY_TOKENS))
        scripts = script_for(text, {"reactive fallback marker": fact})
        release = threading.Event()
        scripts[0] = [("hold", release)] + scripts[0]
        overflow_error = ("status", 400, "the input length exceeds the context length")
        fake, runner = self.overflow_runner([overflow_error], *scripts, ollama_reply(["AMBER"]))
        conv = self.conversations.create()
        gen = runner.send(conv, text, MODEL)
        self.assertTrue(fake.request_seen.wait(5))
        _snapshot, events = gen.subscribe()
        deadline = time.monotonic() + 5
        while len(fake.requests) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreaterEqual(len(fake.requests), 2)
        release.set()
        live = drain(events)
        self.assertTrue(any(event["type"] == "reset" for event in live))
        self.assertEqual(outcome(gen.snapshot(), live)["type"], "done")
        self.assertIn(fact, fake.requests[-1]["body"]["messages"][-1]["content"])
        self.assertEqual(sum(1 for request in fake.requests if request["body"].get("truncate") is False),
                         len(fake.requests))

    def test_no_relevant_source_sentence_fails_visibly_and_later_chat_recovers(self):
        text = negative_document()
        scripts = script_for(text, {})
        fake, runner = self.overflow_runner(*scripts, ollama_reply(["ordinary recovery works"]))
        conv = self.conversations.create()
        failed = runner.send(conv, text, MODEL)
        result = outcome(*watch(failed))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "context_exceeded"))
        self.assertEqual(len(fake.requests), len(scripts))  # no final answer call after empty extraction
        self.assertEqual(self.conversations.get(conv)["turns"][0]["text"], text)
        self.talk(runner, conv, ["short follow-up"])
        self.assertEqual(fake.requests[-1]["body"]["messages"][-1]["content"], "short follow-up")

    def test_partial_extractor_text_is_not_exposed_as_a_failed_assistant_answer(self):
        text, _facts = primary_document()
        fake, runner = self.overflow_runner([ollama_chunk("internal extraction fragment"), ("reset",)])
        conv = self.conversations.create()
        gen = runner.send(conv, text, MODEL)
        result = outcome(*watch(gen))
        self.assertEqual((result["type"], result["error"]["reason"]), ("failed", "connection_reset"))
        self.assertEqual(result["error"]["partial_text"], "")
        self.assertEqual(self.conversations.get(conv)["turns"][-1]["text"], "")

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


class RetrievedWindowTests(unittest.TestCase):
    def test_retrieval_uses_remaining_budget_and_keeps_the_newest_message(self):
        history = [(i, {"role": "user", "content": "old " + str(i) + " " * 100}) for i in range(8)]
        history.append((8, {"role": "user", "content": "newest question"}))
        item = {"id": "conv:2", "role": "assistant", "content": "The old detail is Cedar Rapids.",
                "distance": 0.12}
        result = choose_window(history, "", MODEL, TokenEstimator(), 120, [item])
        self.assertLessEqual(result.estimated_tokens, result.budget)
        self.assertEqual(result.messages[-1]["content"], "newest question")
        self.assertTrue(any("Cedar Rapids" in message["content"] for message in result.messages))
        self.assertEqual(result.record()["sources"][0]["id"], "conv:2")
        self.assertGreater(result.dropped, 0)

    def test_recent_duplicate_is_not_repeated_as_a_retrieved_excerpt(self):
        content = "This exact fact is already in recent history."
        history = [(0, {"role": "user", "content": content})]
        item = {"id": "conv:1", "role": "user", "content": content, "distance": 0.0}
        result = choose_window(history, "", MODEL, TokenEstimator(), 500, [item])
        self.assertEqual(result.sources, [])
        self.assertEqual([m["content"] for m in result.messages], [content])


if __name__ == "__main__":
    unittest.main()
