"""The eight deterministic eval documents. Each is a document followed by a final `Question:` line.

`facts` are the answer sentences that must reach the derived text; `answers` are the keys the model's final
answer must contain (case-insensitive). The absent-fact fixture has neither: it must fail visibly.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from agent_harness.conversation.overflow import keep_ends
from agent_harness.conversation.window import TokenEstimator, budget_tokens

NUM_CTX = 2048
MAX_REPLY_TOKENS = 256
MODEL = "ol:fake:1b"

FIXTURE_NAMES = ("middle_fact", "wrapped_text", "unpunctuated_text", "absent_fact", "two_facts",
                 "head_tail_boundary", "earlier_question_lines", "long_question")


@dataclass(frozen=True)
class Fixture:
    name: str
    text: str
    facts: tuple[str, ...] = ()
    answers: tuple[str, ...] = ()
    expect_failure: bool = False


def _lines(prefix: str, count: int) -> list[str]:
    return [f"{prefix} {i} records routine status and contains no project answer." for i in range(count)]


def _with(lines: list[str], at: dict[int, str]) -> list[str]:
    result = list(lines)
    for index in sorted(at, reverse=True):
        result.insert(index, at[index])
    return result


def _fixture(name, payload_lines, question, facts=(), answers=(), expect_failure=False) -> Fixture:
    return Fixture(name, "\n".join(payload_lines) + "\nQuestion: " + question, tuple(facts), tuple(answers),
                   expect_failure)


def _middle_fact() -> Fixture:
    fact = "The vault code word is PELICAN."
    return _fixture("middle_fact", _with(_lines("Archive entry", 150), {75: fact}),
                    "What is the vault code word?", [fact], ["PELICAN"])


def _wrapped_text() -> Fixture:
    fact = "The maintenance window opens on the third Thursday of each month at 04:30 sharp."
    sentences = [f"Section {i} of the maintenance handbook describes routine inspection and cleaning steps."
                 for i in range(110)]
    sentences.insert(55, fact)
    paragraphs = [" ".join(sentences[i:i + 6]) for i in range(0, len(sentences), 6)]
    payload = "\n\n".join(textwrap.fill(p, width=60) for p in paragraphs)
    return Fixture("wrapped_text", payload + "\nQuestion: When does the maintenance window open?", (fact,),
                   ("third Thursday",))


def _unpunctuated_text() -> Fixture:
    words = ("harbor lantern copper river signal granite meadow anchor cobalt timber velvet orchard "
             "summit marble ember willow current thistle beacon quarry").split()
    body = [words[(i * 7 + i // 5) % len(words)] for i in range(1500)]
    fact = "the beacon frequency is 4471 megahertz"
    body[750:750] = fact.split()
    return Fixture("unpunctuated_text", " ".join(body) + "\nQuestion: what is the beacon frequency", (fact,),
                   ("4471",))


def _absent_fact() -> Fixture:
    return _fixture("absent_fact", _lines("Archive entry", 150), "What is the escrow release password?",
                    expect_failure=True)


def _two_facts() -> Fixture:
    red, blue = "The red cabinet key is 4821.", "The blue cabinet key is 9157."
    return _fixture("two_facts", _with(_lines("Archive entry", 150), {50: red, 100: blue}),
                    "What are the red cabinet key and the blue cabinet key?", [red, blue], ["4821", "9157"])


def _head_tail_boundary() -> Fixture:
    base = _lines("Ledger line", 150)
    estimator, budget = TokenEstimator(), budget_tokens(NUM_CTX, MAX_REPLY_TOKENS)
    head, _tail = keep_ends("\n".join(base), MODEL, estimator, budget)
    # Longer than any ledger line, so it does not fit in the head and is the first middle unit.
    fact = "The ferry schedule code kept in the ledger for the quarter under review is HALCYON."
    return _fixture("head_tail_boundary", _with(base, {len(head): fact}), "What is the ferry schedule code?",
                    [fact], ["HALCYON"])


def _earlier_question_lines() -> Fixture:
    fact = "The evacuation assembly point is Pier Nine."
    earlier = {20: "Question: Is the archive complete?\nAnswer: Not yet.",
               45: "Question: Who maintains these records?\nAnswer: The records office.",
               90: "Question: Are the entries reviewed?\nAnswer: Quarterly.",
               115: "Question: Where are the originals kept?\nAnswer: In the basement."}
    lines = _with(_lines("Archive entry", 150), {65: fact, **earlier})
    return _fixture("earlier_question_lines", lines, "Where is the evacuation assembly point?", [fact],
                    ["Pier Nine"])


def _long_question() -> Fixture:
    fact = "The night shift is carried by the ferry Aurelia."
    question = ("I am compiling the quarterly report for the harbor authority, and I have read many of the entries "
                "in the document above, most of which are routine status notes that do not matter for my purpose. "
                "My manager has asked for a short note on how the crossings are staffed, and she wants it to rely "
                "only on what the document actually says rather than on anything remembered from earlier years. "
                "Using only the document above, tell me the name of the ferry that carries the night shift across "
                "the harbor. Please answer with just the name of the ferry and nothing else.")
    return _fixture("long_question", _with(_lines("Archive entry", 150), {75: fact}), question, [fact], ["Aurelia"])


def all_fixtures() -> list[Fixture]:
    built = [_middle_fact(), _wrapped_text(), _unpunctuated_text(), _absent_fact(), _two_facts(),
             _head_tail_boundary(), _earlier_question_lines(), _long_question()]
    assert tuple(f.name for f in built) == FIXTURE_NAMES
    return built
