"""T6 Release: version, changelog, final docs, size ceilings, silent-wrong warning, smoke matrix, final plan."""

import re
import unittest
from pathlib import Path

from tests import support  # noqa: F401
from tests.eval import runner as eval_runner
from tests.test_t5_measure import full_grid
import agent_harness
from agent_harness.conversation import overflow
from agent_harness.conversation.window import DEFAULT_RATIO, TokenEstimator, budget_tokens, largest_reply

ROOT = Path(__file__).resolve().parents[1]
SILENT_WRONG = (("qwen2.5:0.5b", "unpunctuated_text"), ("qwen2.5:0.5b", "two_facts"),
                ("qwen3.5:2b", "wrapped_text"), ("qwen3.5:2b", "unpunctuated_text"))
CONTEXTS = (2048, 4096, 8192, 16384)
REPLIES = (256, 2048)


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def largest_message(num_ctx, reply):
    """Characters in the largest single message that fits the prompt budget, by the code's own estimate."""
    budget, estimator = budget_tokens(num_ctx, reply), TokenEstimator()
    low, high = 0, 1_000_000
    while low < high:
        mid = (low + high + 1) // 2
        if estimator.messages("any", [{"role": "user", "content": "a" * mid}]) <= budget:
            low = mid
        else:
            high = mid - 1
    return low


def chunk_ceiling(num_ctx):
    """Rough document size the eight-chunk cap allows, rounded to hundreds of characters."""
    chunk = int(num_ctx * overflow.CHUNK_SIZE_FRACTION * DEFAULT_RATIO)
    return int(round(overflow.MAX_EXTRACTION_CHUNKS * chunk * (1 - overflow.CHUNK_OVERLAP_FRACTION), -2))


class ReleaseTests(unittest.TestCase):
    def test_version_is_0_2_0(self):
        self.assertEqual(agent_harness.__version__, "0.2.0")

    def test_changelog_has_a_0_2_0_entry(self):
        changelog = read("CHANGELOG.md")
        self.assertRegex(changelog, r"(?m)^## 0\.2\.0")
        for needle in ("overflow", "memory", "Document", "verify_derived", "EVAL-RESULTS.md"):
            self.assertIn(needle, changelog)


class EvalReportTests(unittest.TestCase):
    def test_the_report_lists_silent_wrong_answers(self):
        cells = full_grid("small_ends", {("qwen3.5:2b", "two_facts"): {"correct": False}})
        for cell in cells:
            if (cell["model"], cell["fixture"]) == ("qwen3.5:2b", "two_facts"):
                cell["answer"] = "The red cabinet key is 4821."
        report = eval_runner.render_report(eval_runner.finish({"meta": {}, "cells": cells}))
        self.assertIn("## Silent wrong answers", report)
        section = report[report.index("## Silent wrong answers"):]
        self.assertIn("qwen3.5:2b", section)
        self.assertIn("two_facts", section)
        self.assertIn("The red cabinet key is 4821.", section)

    def test_the_committed_report_lists_the_four_cells(self):
        report = read("docs", "EVAL-RESULTS.md")
        section = report[report.index("## Silent wrong answers"):]
        winner = section[section.index("### small_ends"):]
        winner = winner[:winner.index("###", 3)] if "###" in winner[3:] else winner
        for model, fixture in SILENT_WRONG:
            self.assertTrue(re.search(rf"\| {re.escape(model)} \| {fixture} \|", winner), (model, fixture))


class ReleaseDocsTests(unittest.TestCase):
    def test_security_says_derived_text_is_stored_in_plaintext_in_the_event_log(self):
        lines = read("docs", "SECURITY.md").lower().splitlines()
        self.assertTrue(any("derived" in line and "plaintext" in line and "event log" in line for line in lines))

    def test_architecture_says_no_graph_is_built(self):
        self.assertIn("no graph is built", read("docs", "ARCHITECTURE.md").lower())

    def test_readme_and_architecture_warn_about_silent_wrong_answers(self):
        for doc in (read("README.md"), read("docs", "ARCHITECTURE.md")):
            self.assertIn("without any warning", doc)
            self.assertIn("4B or larger", doc)
            self.assertIn("EVAL-RESULTS.md", doc)
            for model, fixture in SILENT_WRONG:
                self.assertIn(f"{model} on `{fixture}`", doc)

    def test_size_ceilings_match_the_code(self):
        doc = read("docs", "CONFIGURATION.md")
        self.assertIn("20,000", doc)
        for num_ctx in CONTEXTS:
            for reply in REPLIES:
                if reply > largest_reply(num_ctx):
                    continue
                with self.subTest(num_ctx=num_ctx, reply=reply):
                    row = f"| {num_ctx:,} | {reply:,} | {budget_tokens(num_ctx, reply):,} | {largest_message(num_ctx, reply):,} |"
                    self.assertIn(row, doc)

    def test_the_chunk_cap_ceiling_is_documented(self):
        doc = read("docs", "CONFIGURATION.md")
        for num_ctx in CONTEXTS:
            with self.subTest(num_ctx=num_ctx):
                self.assertIn(f"{chunk_ceiling(num_ctx):,}", doc)

    def test_docs_say_small_ends_was_chosen_by_the_rule_on_a_near_tie(self):
        for doc in (read("README.md"), read("docs", "ARCHITECTURE.md"), read("CHANGELOG.md")):
            self.assertIn("near-tie", doc)
            self.assertIn("pre-declared", doc)
            self.assertIn("small_ends", doc)

    def test_smoke_matrix_lists_every_required_run(self):
        doc = read("docs", "SMOKE-MATRIX.md")
        for needle in ("Document + Question", "in the browser", "Chroma importable", "chromadb blocked",
                       "embedding model unavailable", "--backlog 800", "ollama_overflow_smoke.py", "Eval summary",
                       "fresh clone", "without chromadb", "with chromadb"):
            self.assertIn(needle, doc)

    def test_plan_says_project_complete_and_lists_the_deferred_items(self):
        plan = read("PLAN.md")
        self.assertIn("Project complete", plan)
        tail = plan[plan.index("Project complete"):].lower()
        for item in ("history-overflow condensing", "graph construction", "hybrid ranking",
                     "cross-conversation retrieval", "larger-model routing"):
            self.assertIn(item, tail)


if __name__ == "__main__":
    unittest.main()
