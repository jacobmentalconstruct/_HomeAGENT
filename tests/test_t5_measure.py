"""T5 Measure and Compose: eval fixtures and runner, composition variants, thresholds, Document + Question UI."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from tests import support  # noqa: F401
from tests.eval import fixtures as eval_fixtures
from tests.eval import runner as eval_runner
from tests.eval.fixtures import FIXTURE_NAMES, all_fixtures
from tests.fake_backends import FakeBackend, ollama_reply
from tests.overflow_fixtures import NUM_CTX, MAX_REPLY_TOKENS, primary_document, script_for
from tests.page_harness import HAVE_NODE, PAGE, run_page_js
from tests.test_conversation import PATIENT, Base, outcome, watch
from tests.test_t4_harden import OverflowBase
from agent_harness.config import BackendConfig
from agent_harness.conversation import overflow, provenance
from agent_harness.conversation.overflow import UnsupportedOverflow, chunks, keep_ends, parse_question, sentences
from agent_harness.conversation.provenance import COMPOSITIONS, DERIVED_MARKER, verify_derived
from agent_harness.conversation.window import ContextTooLarge, TokenEstimator, budget_tokens, choose_window
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.transport import Transport

ROOT = Path(__file__).resolve().parents[1]
MODEL = "ol:fake:1b"
BUDGET = budget_tokens(NUM_CTX, MAX_REPLY_TOKENS)
DOC_FIXTURES = {f.name: f for f in all_fixtures()}


def norm(text):
    return " ".join(text.split())


class EvalFixtureTests(unittest.TestCase):
    def test_there_are_eight_fixtures_with_the_declared_kinds(self):
        self.assertEqual(FIXTURE_NAMES, ("middle_fact", "wrapped_text", "unpunctuated_text", "absent_fact",
                                         "two_facts", "head_tail_boundary", "earlier_question_lines",
                                         "long_question"))
        self.assertEqual([f.name for f in all_fixtures()], list(FIXTURE_NAMES))

    def test_the_duplicated_sentence_fixture_is_replaced_by_earlier_question_lines(self):
        self.assertNotIn("duplicated_sentence", FIXTURE_NAMES)
        self.assertIn("earlier_question_lines", FIXTURE_NAMES)

    def test_every_fixture_overflows_the_budget_and_ends_with_its_question(self):
        for fixture in all_fixtures():
            with self.subTest(fixture=fixture.name):
                with self.assertRaises(ContextTooLarge):
                    choose_window([(0, {"role": "user", "content": fixture.text})], "", MODEL,
                                  TokenEstimator(), BUDGET)
                payload, question, _range = parse_question(fixture.text)
                self.assertTrue(fixture.text.endswith(question))
                self.assertTrue(question.startswith("Question:"))
                self.assertNotIn("Question:", question[len("Question:"):])  # the last marker is the only one in it

    def test_every_answer_sentence_is_in_its_document_and_the_absent_fixture_has_none(self):
        for fixture in all_fixtures():
            with self.subTest(fixture=fixture.name):
                payload, _question, _range = parse_question(fixture.text)
                if fixture.expect_failure:
                    self.assertEqual((fixture.facts, fixture.answers), ((), ()))
                    continue
                self.assertTrue(fixture.facts and fixture.answers)
                for fact in fixture.facts:
                    self.assertIn(norm(fact), norm(payload))
                for key in fixture.answers:
                    self.assertTrue(any(key.lower() in fact.lower() for fact in fixture.facts), key)

    def test_the_earlier_question_lines_fixture_parses_to_the_final_question(self):
        fixture = DOC_FIXTURES["earlier_question_lines"]
        self.assertGreaterEqual(len(re.findall(r"(?m)^Question:", fixture.text)), 4)  # three earlier + the real one
        payload, question, _range = parse_question(fixture.text)
        self.assertGreaterEqual(len(re.findall(r"(?m)^Question:", payload)), 3)
        self.assertIn("evacuation", question.lower())

    def test_the_boundary_fixture_puts_its_fact_first_after_the_protected_head(self):
        fixture = DOC_FIXTURES["head_tail_boundary"]
        payload, _question, _range = parse_question(fixture.text)
        units = sentences(payload)
        head, _tail = keep_ends(payload, MODEL, TokenEstimator(), BUDGET)
        self.assertGreater(len(head), 0)
        self.assertEqual(norm(units[len(head)].text), norm(fixture.facts[0]))

    def test_the_long_question_fixture_has_a_long_question(self):
        _payload, question, _range = parse_question(DOC_FIXTURES["long_question"].text)
        self.assertGreaterEqual(len(question), 500)

    def test_every_fixture_fits_the_extraction_chunk_cap(self):
        estimator = TokenEstimator()
        max_chars = int(NUM_CTX * overflow.CHUNK_SIZE_FRACTION * estimator.ratio(MODEL))
        for name, composition in COMPOSITIONS.items():
            for fixture in all_fixtures():
                with self.subTest(variant=name, fixture=fixture.name):
                    payload, _question, _range = parse_question(fixture.text)
                    head, tail = keep_ends(payload, MODEL, estimator, BUDGET, composition["share"])
                    protected = {u.start for u in head + tail}
                    middle = [u for u in sentences(payload) if u.start not in protected]
                    self.assertLessEqual(len(chunks(middle, max_chars)), overflow.MAX_EXTRACTION_CHUNKS)


class CompositionTests(OverflowBase):
    def derive(self, variant, text=None, facts=None):
        text = text or primary_document()[0]
        replies = facts or {"opening project marker": "The opening project marker is COBALT.",
                            "hidden project marker": "The hidden project marker is VIOLET.",
                            "closing project marker": "The closing project marker is MARIGOLD."}
        scripts = script_for(text, replies, composition=variant)
        _fake, runner = self.overflow_runner(*scripts, ollama_reply(["VIOLET"]), overflow_composition=variant)
        conv = self.conversations.create()
        self.assertEqual(outcome(*watch(runner.send(conv, text, MODEL)))["type"], "done")
        return text, self.conversations.get(conv)["window"]["derived"]

    def test_there_are_exactly_three_named_compositions(self):
        self.assertEqual(set(COMPOSITIONS), {"baseline", "small_ends", "block_by_question"})
        self.assertIn(overflow.DEFAULT_COMPOSITION, COMPOSITIONS)

    def test_baseline_output_is_unchanged(self):
        text, derived = self.derive("baseline")
        roles = [s["role"] for s in derived["sources"]]
        self.assertEqual(derived["composition"], "baseline")
        self.assertEqual(roles[0], "head")
        self.assertEqual(roles[-2:], ["tail", "question"])
        self.assertTrue(all(r == "middle" for r in roles[1:-2]))
        lines = derived["text"].split("\n")
        self.assertEqual(lines[lines.index(DERIVED_MARKER) + 1], "The hidden project marker is VIOLET.")
        self.assertEqual(derived["text"].index("The closing project marker"), derived["text"].rindex(
            "The closing project marker"))
        self.assertLess(derived["text"].index(DERIVED_MARKER), derived["text"].index("The closing project marker"))
        self.assertTrue(derived["text"].endswith(text[text.rfind("Question:"):]))

    def test_small_ends_keeps_less_of_the_head_and_tail(self):
        def ends(derived):
            return sum(s["char_range"][1] - s["char_range"][0] for s in derived["sources"]
                       if s["role"] in ("head", "tail"))
        _t, base = self.derive("baseline")
        _t, small = self.derive("small_ends")
        self.assertLess(ends(small), ends(base))
        self.assertEqual(small["composition"], "small_ends")

    def test_block_by_question_puts_the_derived_block_just_before_the_question(self):
        text, base = self.derive("baseline")
        _t, block = self.derive("block_by_question")
        tail = next(s for s in block["sources"] if s["role"] == "tail")
        tail_text = text[tail["char_range"][0]:tail["char_range"][1]]
        self.assertLess(block["text"].index(tail_text), block["text"].index(DERIVED_MARKER))
        self.assertLess(base["text"].index(DERIVED_MARKER), base["text"].index(tail_text))
        question = text[text.rfind("Question:"):]
        before_question = block["text"][:-len(question)].rstrip("\n")
        self.assertTrue(before_question.endswith("The hidden project marker is VIOLET."))  # a derived span is last

    def test_every_composition_verifies_with_verify_derived(self):
        for variant in COMPOSITIONS:
            with self.subTest(variant=variant):
                text, derived = self.derive(variant)
                self.assertEqual(verify_derived(text, derived), [])
        record = {"method": "extractive_map_reduce", "version": 2, "text": "x",
                  "sources": [{"event_id": 1, "char_range": [0, 1], "source_sha256": "0" * 64}],
                  "composition": "no_such_variant"}
        self.assertIn("unknown_composition", verify_derived("x", {**record, "sources": [
            {**record["sources"][0], "role": "head"}]}))

    def test_the_default_composition_is_the_recorded_winner(self):
        results = json.loads((ROOT / "docs" / "eval-results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["winner"], overflow.DEFAULT_COMPOSITION)


def make_cell(variant, model, fixture, *, extraction=True, correct=True, visible=False, calls=3, seconds=1.0):
    return {"variant": variant, "model": model, "fixture": fixture, "state": "done", "error_reason": "",
            "answer": "", "derived": True, "extraction_ok": extraction, "correct": correct,
            "visible_failure": visible, "model_calls": calls, "seconds": seconds}


def full_grid(variant, overrides=None):
    """Every model x fixture cell for one variant, all passing, with per-cell overrides by (model, fixture)."""
    cells = []
    for model in eval_runner.MODELS:
        for name in FIXTURE_NAMES:
            absent = name == "absent_fact"
            base = dict(extraction=True, correct=True, visible=absent)
            base.update((overrides or {}).get((model, name), {}))
            cells.append(make_cell(variant, model, name, **base))
    return cells


class ThresholdTests(unittest.TestCase):
    def test_extraction_threshold_by_model_size(self):
        met = eval_runner.evaluate_thresholds(full_grid("baseline"), "baseline")
        self.assertTrue(met["checks"]["extraction_models_ge_1_5b"]["met"])
        self.assertTrue(met["checks"]["extraction_0_5b"]["met"])
        miss_one_small = eval_runner.evaluate_thresholds(
            full_grid("baseline", {("qwen2.5:0.5b", "two_facts"): {"extraction": False}}), "baseline")
        self.assertTrue(miss_one_small["checks"]["extraction_0_5b"]["met"])  # 7/8 is enough for 0.5B
        miss_two_small = eval_runner.evaluate_thresholds(
            full_grid("baseline", {("qwen2.5:0.5b", "two_facts"): {"extraction": False},
                                     ("qwen2.5:0.5b", "wrapped_text"): {"extraction": False}}), "baseline")
        self.assertFalse(miss_two_small["checks"]["extraction_0_5b"]["met"])
        miss_mid = eval_runner.evaluate_thresholds(
            full_grid("baseline", {("qwen2.5:1.5b", "two_facts"): {"extraction": False}}), "baseline")
        self.assertFalse(miss_mid["checks"]["extraction_models_ge_1_5b"]["met"])  # 100% for 1.5B and up

    def test_correctness_threshold_gates_only_models_4b_and_up(self):
        small_wrong = full_grid("baseline", {(m, f): {"correct": False} for m in ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen3.5:2b")
                                               for f in FIXTURE_NAMES if f != "absent_fact"})
        result = eval_runner.evaluate_thresholds(small_wrong, "baseline")
        self.assertTrue(result["checks"]["correctness_models_ge_4b"]["met"])  # smaller models are reported only
        self.assertIn("qwen2.5:1.5b", result["report_only"]["correctness"])
        big_one_wrong = eval_runner.evaluate_thresholds(
            full_grid("baseline", {("qwen3.5:4b", "two_facts"): {"correct": False}}), "baseline")
        self.assertTrue(big_one_wrong["checks"]["correctness_models_ge_4b"]["met"])  # 7/8 = 87.5% >= 80%
        big_two_wrong = eval_runner.evaluate_thresholds(
            full_grid("baseline", {("qwen3.5:9b", "two_facts"): {"correct": False},
                                     ("qwen3.5:9b", "middle_fact"): {"correct": False}}), "baseline")
        self.assertFalse(big_two_wrong["checks"]["correctness_models_ge_4b"]["met"])  # 6/8 = 75% < 80%

    def test_absent_fact_must_fail_visibly_every_time(self):
        result = eval_runner.evaluate_thresholds(full_grid("baseline"), "baseline")
        self.assertTrue(result["checks"]["absent_fact_fails_visibly"]["met"])
        once = eval_runner.evaluate_thresholds(
            full_grid("baseline", {("qwen3.5:9b", "absent_fact"): {"visible": False}}), "baseline")
        self.assertFalse(once["checks"]["absent_fact_fails_visibly"]["met"])

    def test_timings_are_reported_not_gated(self):
        slow = full_grid("baseline")
        for cell in slow:
            cell["seconds"] = 99999.0
            cell["model_calls"] = 99
        result = eval_runner.evaluate_thresholds(slow, "baseline")
        self.assertTrue(all(check["met"] for check in result["checks"].values()))
        self.assertEqual(set(result["timings"]), set(eval_runner.MODELS))
        self.assertEqual(result["timings"]["qwen3.5:9b"]["seconds"], 99999.0 * len(FIXTURE_NAMES))
        self.assertNotIn("timings", result["checks"])


class EvalRunnerTests(unittest.TestCase):
    def backend(self, *scripts):
        fake = FakeBackend("ollama", scripts=list(scripts))
        self.addCleanup(fake.stop)
        return OllamaBackend(BackendConfig("ol", "ollama", fake.url), Transport(PATIENT), NUM_CTX, MAX_REPLY_TOKENS)

    def scripts_for(self, name, answer):
        fixture = DOC_FIXTURES[name]
        replies = {fact[:24]: fact for fact in fixture.facts}
        scripts = script_for(fixture.text, replies)
        return fixture, scripts, [ollama_reply([answer])]

    def test_the_declared_models_and_variants(self):
        self.assertEqual(eval_runner.MODELS, ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen3.5:2b", "qwen3.5:4b",
                                              "qwen3.5:9b"))
        self.assertEqual(set(eval_runner.VARIANTS), set(COMPOSITIONS))
        self.assertLessEqual(len(eval_runner.VARIANTS), 3)

    def test_a_cell_records_extraction_answer_correctness_calls_and_time(self):
        fixture, scripts, final = self.scripts_for("middle_fact", fixture_answer("middle_fact"))
        cell = eval_runner.run_cell(self.backend(*scripts, *final), "fake:1b", fixture, "baseline")
        self.assertEqual((cell["state"], cell["derived"], cell["extraction_ok"], cell["correct"],
                          cell["visible_failure"]), ("done", True, True, True, False))
        self.assertEqual(cell["model_calls"], len(scripts) + 1)
        self.assertGreaterEqual(cell["seconds"], 0)
        self.assertEqual(cell["answer"], fixture_answer("middle_fact"))
        self.assertEqual((cell["variant"], cell["model"], cell["fixture"]), ("baseline", "fake:1b", "middle_fact"))
        wrong = self.scripts_for("middle_fact", "I do not know")
        cell = eval_runner.run_cell(self.backend(*wrong[1], *wrong[2]), "fake:1b", wrong[0], "baseline")
        self.assertEqual((cell["extraction_ok"], cell["correct"]), (True, False))

    def test_an_absent_fact_cell_records_a_visible_failure(self):
        fixture = DOC_FIXTURES["absent_fact"]
        scripts = script_for(fixture.text, {})
        cell = eval_runner.run_cell(self.backend(*scripts), "fake:1b", fixture, "baseline")
        self.assertEqual((cell["state"], cell["error_reason"], cell["visible_failure"], cell["derived"]),
                         ("failed", "context_exceeded", True, False))
        self.assertTrue(cell["extraction_ok"] and cell["correct"])  # by the recorded interpretation
        self.assertEqual(cell["model_calls"], len(scripts))

    def test_results_are_saved_after_each_cell_and_resumed(self):
        fixture, scripts, final = self.scripts_for("middle_fact", fixture_answer("middle_fact"))
        absent = script_for(DOC_FIXTURES["absent_fact"].text, {})
        backend = self.backend(*scripts, *final, *absent)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "results.json"
            seen = []
            pair = [DOC_FIXTURES["middle_fact"], DOC_FIXTURES["absent_fact"]]
            eval_runner.run_matrix(backend, ("fake:1b",), ("baseline",), pair, out,
                                   progress=lambda cell: seen.append(len(json.loads(out.read_text())["cells"])))
            self.assertEqual(seen, [1, 2])  # written after each cell
            doc = json.loads(out.read_text())
            self.assertEqual(len(doc["cells"]), 2)

            class Forbidden:
                def chat(self, *args, **kwargs):
                    raise AssertionError("a finished cell must not run again")
            again = eval_runner.run_matrix(Forbidden(), ("fake:1b",), ("baseline",), pair, out)
            self.assertEqual(len(again["cells"]), 2)

    def test_the_report_lists_every_cell_and_the_thresholds(self):
        cells = [c for variant in COMPOSITIONS for c in full_grid(variant)]
        doc = eval_runner.finish({"meta": {}, "cells": cells})
        report = eval_runner.render_report(doc)
        for model in eval_runner.MODELS:
            self.assertIn(model, report)
        for variant in COMPOSITIONS:
            self.assertIn(variant, report)
        for name in FIXTURE_NAMES:
            self.assertIn(name, report)
        for check in ("extraction_models_ge_1_5b", "extraction_0_5b", "correctness_models_ge_4b",
                      "absent_fact_fails_visibly"):
            self.assertIn(check, report)
        self.assertIn("Winner: ", report)
        self.assertIn("Exit thresholds", report)

    def test_the_winner_rule_follows_the_declared_order(self):
        def cells_with(**per_variant):
            cells = []
            for variant in COMPOSITIONS:
                cells += full_grid(variant, per_variant.get(variant, {}))
            return cells
        # 1. more thresholds met wins
        worse = {("qwen3.5:9b", "absent_fact"): {"visible": False}}
        self.assertEqual(eval_runner.choose_winner(cells_with(baseline=worse, small_ends=worse))["winner"],
                         "block_by_question")
        # 2. equal thresholds: more correct answers wins (smaller models are report-only for thresholds)
        fewer = {("qwen2.5:0.5b", "middle_fact"): {"correct": False}}
        self.assertEqual(eval_runner.choose_winner(cells_with(baseline=fewer, block_by_question=fewer))["winner"],
                         "small_ends")
        # 3. equal correctness: more extraction passes wins
        miss = {("qwen2.5:0.5b", "middle_fact"): {"extraction": False}}
        self.assertEqual(eval_runner.choose_winner(cells_with(baseline=miss, small_ends=miss))["winner"],
                         "block_by_question")
        # 4. then fewer model calls
        cells = cells_with()
        for cell in cells:
            if cell["variant"] == "small_ends":
                cell["model_calls"] = 2
        self.assertEqual(eval_runner.choose_winner(cells)["winner"], "small_ends")
        # 5. a complete tie goes to the baseline
        self.assertEqual(eval_runner.choose_winner(cells_with())["winner"], "baseline")


def fixture_answer(name):
    return DOC_FIXTURES[name].answers[0]


class RecordedArtifactTests(unittest.TestCase):
    def test_threshold_constants_are_the_declared_ones(self):
        self.assertEqual(eval_runner.THRESHOLDS, {"extraction_models_ge_1_5b": 1.0, "extraction_0_5b": 7 / 8,
                                                  "correctness_models_ge_4b": 0.8})
        self.assertEqual(eval_runner.MODEL_SIZE_B, {"qwen2.5:0.5b": 0.5, "qwen2.5:1.5b": 1.5, "qwen3.5:2b": 2.0,
                                                    "qwen3.5:4b": 4.0, "qwen3.5:9b": 9.0})

    def test_the_results_cover_every_model_variant_and_fixture(self):
        doc = json.loads((ROOT / "docs" / "eval-results.json").read_text(encoding="utf-8"))
        wanted = {(v, m, f) for v in eval_runner.VARIANTS for m in eval_runner.MODELS for f in FIXTURE_NAMES}
        got = {(c["variant"], c["model"], c["fixture"]) for c in doc["cells"]}
        self.assertEqual(got, wanted)
        self.assertEqual(len(doc["cells"]), 120)
        report = (ROOT / "docs" / "EVAL-RESULTS.md").read_text(encoding="utf-8")
        self.assertIn("Exit thresholds", report)
        self.assertIn(f"Winner: {doc['winner']}", report)


class DocumentQuestionPageTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_NODE, "node is not installed")
    def test_compose_joins_document_and_question_in_the_backend_shape(self):
        result = run_page_js("""
          out({ both: api.prepareMessage("The doc line.\\nSecond line.\\n\\n", "  What is it? "),
                plain: api.prepareMessage("", "hello"), blank: api.prepareMessage("   \\n", "hello"),
                noquestion: api.prepareMessage("a document", "  ") });""", "prepareMessage")
        self.assertEqual(result["both"], {"text": "The doc line.\nSecond line.\nQuestion: What is it?", "error": ""})
        self.assertEqual(result["plain"], {"text": "hello", "error": ""})
        self.assertEqual(result["blank"], {"text": "hello", "error": ""})
        self.assertEqual(result["noquestion"]["text"], "")
        self.assertIn("question", result["noquestion"]["error"].lower())

    @unittest.skipUnless(HAVE_NODE, "node is not installed")
    def test_the_composed_message_parses_with_the_backend_parser(self):
        doc, question = "Line one.\nQuestion: an earlier line stays in the document.\nLine three.", "Who wrote it?"
        result = run_page_js("out(api.prepareMessage(%s, %s));" % (json.dumps(doc), json.dumps(question)),
                             "prepareMessage")
        payload, parsed_question, _range = parse_question(result["text"])
        self.assertEqual(payload, doc)
        self.assertEqual(parsed_question, "Question: Who wrote it?")

    @unittest.skipUnless(HAVE_NODE, "node is not installed")
    def test_an_over_limit_message_is_refused_in_the_browser(self):
        result = run_page_js("""
          out({ over: api.prepareMessage("x".repeat(20001), "q"), edge: api.prepareMessage("x".repeat(19960), "q").error,
                plain: api.prepareMessage("", "y".repeat(20001)) });""", "prepareMessage")
        self.assertIn("20,000", result["over"]["error"])
        self.assertEqual(result["over"]["text"], "")
        self.assertEqual(result["edge"], "")
        self.assertIn("20,000", result["plain"]["error"])

    def test_the_page_has_document_and_question_fields_and_uses_textcontent(self):
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn('id="doc"', page)
        self.assertIn('id="docmode"', page)
        self.assertIn("prepareMessage", page)
        self.assertNotIn("innerHTML", page)
        self.assertIn('placeholder="Document', page)

    def test_parse_question_is_unchanged(self):
        payload, question, span = parse_question("Doc.\nQuestion: early?\nMore.\nQuestion: final?")
        self.assertEqual((payload, question), ("Doc.\nQuestion: early?\nMore.", "Question: final?"))
        self.assertEqual(span, (len("Doc.\nQuestion: early?\nMore.\n"), len("Doc.\nQuestion: early?\nMore.\nQuestion: final?")))
        for bad in ("no marker here", "Doc.\nQuestion:   ", "Question: only a question"):
            with self.subTest(bad=bad), self.assertRaises(UnsupportedOverflow):
                parse_question(bad)
        self.assertEqual(provenance.DERIVED_MARKER, "[Derived middle: extractive, source-linked context]")


if __name__ == "__main__":
    unittest.main()
