"""Small, bounded extractive fallback for one oversized final user message."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass

from ..models.errors import BackendError
from .window import ContextTooLarge, choose_window

QUESTION = re.compile(r"(?m)^Question:\s*")
SENTENCE = re.compile(r"(?<=[.!?])(?:[\"'”’)]*)\s+")
CHUNK_SIZE_FRACTION = 0.40
HEAD_TAIL_BUDGET_SHARE = 0.10
MAX_EXTRACTION_CHUNKS = 8
MAX_DEPTH = 2


class UnsupportedOverflow(ValueError):
    """The oversized message does not match the prototype's explicit input shape."""


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    text: str


def parse_question(text: str) -> tuple[str, str]:
    """Split a payload from its final explicit Question section, preserving that section verbatim."""
    matches = list(QUESTION.finditer(text))
    if not matches:
        raise UnsupportedOverflow("The oversized message must end with an explicit Question: section.")
    marker = matches[-1]
    question = text[marker.start():]
    if not question[len("Question:"):].strip():
        raise UnsupportedOverflow("The final Question: section is empty.")
    payload = text[:marker.start()].rstrip()
    if not payload:
        raise UnsupportedOverflow("The Question: section must follow a document payload.")
    return payload, question


def sentences(text: str, offset: int = 0) -> list[Sentence]:
    """Return sentence slices with offsets into the original event text."""
    result = []
    start = 0
    for match in SENTENCE.finditer(text):
        end = match.start()
        if text[start:end].strip():
            left = start + len(text[start:end]) - len(text[start:end].lstrip())
            right = start + len(text[start:end].rstrip())
            result.append(Sentence(offset + left, offset + right, text[left:right]))
        start = match.end()
    if text[start:].strip():
        left = start + len(text[start:]) - len(text[start:].lstrip())
        right = len(text.rstrip())
        result.append(Sentence(offset + left, offset + right, text[left:right]))
    return result


def normalize_sentence(text: str) -> str:
    return " ".join(text.split())


def keep_ends(payload: str, model: str, estimator, budget: int) -> tuple[list[Sentence], list[Sentence]]:
    """Keep source sentences from each end within a 10% prompt-budget share apiece."""
    all_sentences = sentences(payload)
    allowance = max(0, int(budget * HEAD_TAIL_BUDGET_SHARE))
    def cost(items):
        if not items:
            return 0
        return estimator.messages(model, [{"role": "user", "content": " ".join(x.text for x in items)}])

    head = []
    for item in all_sentences:
        if cost(head + [item]) > allowance:
            break
        head.append(item)
    tail = []
    for item in reversed(all_sentences[len(head):]):
        if cost(tail + [item]) > allowance:
            break
        tail.insert(0, item)
    return head, tail


def chunks(items: list[Sentence], max_chars: int) -> list[list[Sentence]]:
    result: list[list[Sentence]] = []
    current: list[Sentence] = []
    count = 0
    for item in items:
        size = item.end - item.start
        if current and count + size > max_chars:
            result.append(current)
            current, count = [], 0
        current.append(item)
        count += size + 1
    if current:
        result.append(current)
    return result


def derive_context(original: str, history: list[tuple[int, dict]], source_event_id: int, model: str,
                   backend, estimator, budget: int, num_ctx: int, system_prompt: str,
                   retrieved: list[dict], options: dict | None, deadline: float,
                   progress) -> tuple[dict, list[tuple[int, dict]]]:
    """Derive one bounded message. All model calls use the caller's queue and deadline."""
    try:
        payload, question = parse_question(original)
    except UnsupportedOverflow as exc:
        raise BackendError("context_exceeded", str(exc)) from exc
    head, tail = keep_ends(payload, model, estimator, budget)
    protected = {item.start for item in head + tail}
    middle = [item for item in sentences(payload) if item.start not in protected]
    max_chars = max(1, int(num_ctx * CHUNK_SIZE_FRACTION * estimator.ratio(model)))
    if any(item.end - item.start > max_chars for item in middle):
        raise BackendError("context_exceeded", "A source sentence is too large for the bounded extraction chunk.")
    source_chunks = chunks(middle, max_chars)
    if not source_chunks or len(source_chunks) > MAX_EXTRACTION_CHUNKS:
        raise BackendError("context_exceeded", "The document exceeds the extraction chunk limit.")
    source_sentences = {normalize_sentence(item.text): item for item in middle}
    source_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()

    def extract(items: list[Sentence], phase: str, completed: int, total: int) -> list[Sentence]:
        if time.monotonic() >= deadline:
            raise BackendError("deadline", "The generation-wide model deadline expired.")
        content = question + "\n\nSource chunk:\n" + "\n".join(item.text for item in items)
        messages = [
            {"role": "system", "content": "You are a copying tool. Your only allowed output is exact complete "
             "sentence(s) already present in SOURCE. Never answer in your own words, change labels, or invent text. "
             "If the question asks for a value, copy the whole source sentence containing that value. "
             "If no source sentence directly matches the question, output exactly NONE."},
            {"role": "user", "content": "Question and source:\n" + content +
             "\n\nCopy the exact matching source sentence(s) only. No labels, bullets, or explanation."},
        ]
        call_options = dict(options or {})
        call_options["temperature"] = 0
        stream = backend.chat(model, messages, call_options, deadline=deadline)
        try:
            for _part in stream:
                pass
        except BackendError as exc:
            # Extractor text is internal and must never be shown as a partial user-facing answer.
            raise BackendError(exc.reason, exc.message, status=exc.status, detail=exc.detail) from exc
        candidates = [normalize_sentence(line.strip()) for line in stream.text.splitlines()
                      if line.strip() and line.strip().upper() != "NONE"]
        found = [source_sentences[candidate] for candidate in candidates if candidate in source_sentences]
        progress(phase, completed, total)
        return found

    selected: list[Sentence] = []
    for index, part in enumerate(source_chunks, 1):
        selected.extend(extract(part, "extract", index, len(source_chunks)))
    selected = sorted({item.start: item for item in selected}.values(), key=lambda item: item.start)
    if not selected:
        raise BackendError("context_exceeded", "No source sentence matched the question; nothing was transformed.")

    def render(items: list[Sentence]) -> str:
        segments = []
        if head:
            segments.append(payload[:head[-1].end])
        segments.append("[Derived middle: extractive, source-linked context]")
        segments.extend(item.text for item in items)
        if tail:
            segments.append(payload[tail[0].start:])
        segments.append(question)
        return "\n".join(segment for segment in segments if segment)

    changed_history = list(history)
    changed_history[-1] = (history[-1][0], {"role": "user", "content": render(selected)})
    depth = 1
    try:
        choose_window(changed_history, system_prompt, model, estimator, budget, retrieved)
    except ContextTooLarge as exc:
        if MAX_DEPTH < 2:
            raise BackendError("context_exceeded", "The derived prompt still exceeds the model context.") from exc
        depth = 2
        selected = sorted({item.start: item for item in extract(selected, "combine", 1, 1)}.values(),
                          key=lambda item: item.start)
        if not selected:
            raise BackendError("context_exceeded", "Combining extracted sentences produced no valid source text.")
        changed_history[-1] = (history[-1][0], {"role": "user", "content": render(selected)})
        try:
            choose_window(changed_history, system_prompt, model, estimator, budget, retrieved)
        except ContextTooLarge as second:
            raise BackendError("context_exceeded", "The derived prompt still exceeds the model context.") from second

    ranges = []
    if head:
        ranges.append([0, head[-1].end])
    ranges.extend([[item.start, item.end] for item in selected])
    if tail:
        ranges.append([tail[0].start, len(payload)])
    ranges.append([original.rfind("Question:"), len(original)])
    sources = [{"event_id": source_event_id, "char_range": span, "source_sha256": source_hash} for span in ranges]
    derived = {"method": "extractive_map_reduce", "version": 1, "depth": depth,
               "text": changed_history[-1][1]["content"], "sources": sources}
    return derived, changed_history
