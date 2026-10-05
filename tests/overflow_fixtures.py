"""Deterministic inputs for the bounded context-overflow proof."""

from __future__ import annotations

from agent_harness.conversation.overflow import chunks, keep_ends, sentences
from agent_harness.conversation.provenance import COMPOSITIONS, DEFAULT_COMPOSITION
from agent_harness.conversation.window import TokenEstimator

NUM_CTX = 2048
MAX_REPLY_TOKENS = 256
CHUNK_SIZE_FRACTION = 0.40
OVERFLOW_CONFIG = {"num_ctx": NUM_CTX, "max_reply_tokens": MAX_REPLY_TOKENS,
                   "chunk_size_fraction": CHUNK_SIZE_FRACTION}


def primary_document() -> tuple[str, list[str]]:
    distractors = [f"Distractor record {i} says the sample remains ordinary and unchanged."
                   for i in range(200)]
    middle_fact = "The hidden project marker is VIOLET."
    payload = "\n".join(["The opening project marker is COBALT.", *distractors[:100], middle_fact,
                         *distractors[100:], "The closing project marker is MARIGOLD."])
    question = "Question: Copy the exact sentence that states the hidden project marker."
    return payload + "\n" + question, ["The opening project marker is COBALT.", middle_fact,
                                      "The closing project marker is MARIGOLD."]


def middle_document() -> tuple[str, str]:
    distractors = [f"Archive entry {i} contains no answer and records routine status only."
                   for i in range(100)]
    fact = "The mid-document access code is JUNIPER."
    payload = "\n".join([*distractors[:50], fact, *distractors[50:]])
    return payload + "\nQuestion: What is the mid-document access code?", fact


def negative_document() -> str:
    distractors = [f"Archive entry {i} records routine status and contains no project answer."
                   for i in range(180)]
    return "\n".join(distractors) + "\nQuestion: What is the missing access code?"


def hardwrapped_document() -> tuple[str, str]:
    """Unpunctuated, hard-wrapped source exercises line-boundary span handling."""
    lines = [f"archive row {i:03d} contains routine unpunctuated background information"
             for i in range(160)]
    fact = "the hidden access code is SILVER FERN"
    lines.insert(35, fact)
    return "\n".join(lines) + "\nQuestion: what is the hidden access code", fact


def script_for(text: str, replies: dict[str, str], num_ctx: int = NUM_CTX,
               max_reply_tokens: int = MAX_REPLY_TOKENS, composition: str = DEFAULT_COMPOSITION) -> list[list[tuple]]:
    """Build rule-based exact extractors for each deterministic chunk, then final answer."""
    from tests.fake_backends import ollama_reply

    model = "ol:fake:1b"
    estimator = TokenEstimator()
    payload = text[:text.rfind("Question:")].rstrip()
    head, tail = keep_ends(payload, model, estimator,
                           max(256, int(num_ctx * 0.9) - max_reply_tokens), COMPOSITIONS[composition]["share"])
    protected = {item.start for item in head + tail}
    middle = [item for item in sentences(payload) if item.start not in protected]
    max_chars = int(num_ctx * CHUNK_SIZE_FRACTION * estimator.ratio(model))
    scripted = []
    for part in chunks(middle, max_chars):
        match = next((answer for marker, answer in replies.items()
                      if any(marker in sentence.text for sentence in part)), None)
        scripted.append(ollama_reply([match or "NONE"]))
    return scripted
