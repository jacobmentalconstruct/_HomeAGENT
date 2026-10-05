"""Small, bounded extractive fallback for one oversized final user message."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass

from ..models.errors import BackendError
from .provenance import COMPOSITIONS, DEFAULT_COMPOSITION, compose
from .window import ContextTooLarge, choose_window

QUESTION = re.compile(r"(?m)^Question:\s*")
SENTENCE = re.compile(r"(?<=[.!?])(?:[\"'”’)]*)\s+")
CHUNK_SIZE_FRACTION = 0.40
CHUNK_OVERLAP_FRACTION = 0.12
HEAD_TAIL_BUDGET_SHARE = 0.10
MAX_EXTRACTION_CHUNKS = 8
MAX_MODEL_CALLS = 16
MAX_DEPTH = 4


class UnsupportedOverflow(ValueError):
    """The oversized message does not match the prototype's explicit input shape."""


@dataclass(frozen=True)
class Sentence:
    """A source unit/span with half-open offsets into the original user event."""
    start: int
    end: int
    text: str


def parse_question(text: str) -> tuple[str, str, tuple[int, int]]:
    """Return payload, exact Question section, and its exact source range."""
    matches = list(QUESTION.finditer(text))
    if not matches:
        raise UnsupportedOverflow("The oversized message must end with an explicit Question: section.")
    marker = matches[-1]
    question_range = (marker.start(), len(text))
    question = text[marker.start():]
    if not question[len("Question:"):].strip():
        raise UnsupportedOverflow("The final Question: section is empty.")
    payload = text[:marker.start()].rstrip()
    if not payload:
        raise UnsupportedOverflow("The Question: section must follow a document payload.")
    return payload, question, question_range


def sentences(text: str, offset: int = 0) -> list[Sentence]:
    """Split into line/sentence units, with bounded hard splits for long unbroken lines."""
    result: list[Sentence] = []
    # Hard-wrapped documents use lines as units. For a single paragraph, sentences
    # are the useful enclosing units; unpunctuated text falls back to word-safe spans.
    line_parts = []
    line_start = 0
    for match in re.finditer(r"\n+", text):
        if text[line_start:match.start()].strip():
            line_parts.append((line_start, match.start()))
        line_start = match.end()
    if text[line_start:].strip():
        line_parts.append((line_start, len(text)))
    for start, end in line_parts:
        raw = text[start:end]
        if SENTENCE.search(raw):
            local = 0
            for match in SENTENCE.finditer(raw):
                a, b = local, match.start()
                if raw[a:b].strip():
                    left = a + len(raw[a:b]) - len(raw[a:b].lstrip())
                    right = a + len(raw[a:b].rstrip())
                    result.append(Sentence(offset + start + left, offset + start + right,
                                           raw[left:right]))
                local = match.end()
            if raw[local:].strip():
                left = local + len(raw[local:]) - len(raw[local:].lstrip())
                right = len(raw.rstrip())
                result.append(Sentence(offset + start + left, offset + start + right, raw[left:right]))
        else:
            left = len(raw) - len(raw.lstrip())
            right = len(raw.rstrip())
            if left < right:
                result.append(Sentence(offset + start + left, offset + start + right, raw[left:right]))
    # Very long lines are cut at a nearby whitespace boundary to keep a unit usable.
    bounded: list[Sentence] = []
    for unit in result:
        if len(unit.text) <= 800:
            bounded.append(unit)
            continue
        cursor = 0
        while cursor < len(unit.text):
            end = min(len(unit.text), cursor + 800)
            if end < len(unit.text):
                boundary = unit.text.rfind(" ", cursor + 400, end)
                if boundary > cursor:
                    end = boundary
            bounded.append(Sentence(unit.start + cursor, unit.start + end,
                                    unit.text[cursor:end].strip()))
            cursor = end
    return bounded


def normalize_sentence(text: str) -> str:
    return " ".join(text.split())


def _normalized_offsets(text: str) -> tuple[str, list[int], list[int]]:
    """Whitespace-collapse text while tracking source start/end for each normalized char."""
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            if out:
                out.append(" "); starts.append(i); ends.append(j)
            i = j
        else:
            out.append(text[i]); starts.append(i); ends.append(i + 1); i += 1
    if out and out[-1] == " ":
        out.pop(); starts.pop(); ends.pop()
    return "".join(out), starts, ends


def find_exact_span(source: str, candidate: str) -> tuple[int, int] | None:
    """Find a whitespace-normalized exact substring and map it back to source offsets."""
    haystack, starts, ends = _normalized_offsets(source)
    needle = normalize_sentence(candidate)
    if not needle:
        return None
    found = haystack.find(needle)
    if found < 0:
        return None
    return starts[found], ends[found + len(needle) - 1]


def snap_and_merge(ranges: list[tuple[int, int]], units: list[Sentence]) -> list[Sentence]:
    snapped: list[tuple[int, int]] = []
    for start, end in ranges:
        overlapping = [u for u in units if u.start < end and u.end > start]
        if overlapping:
            snapped.append((overlapping[0].start, overlapping[-1].end))
        else:
            snapped.append((start, end))
    merged: list[list[int]] = []
    for start, end in sorted(snapped):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [Sentence(a, b, "") for a, b in merged]


def keep_ends(payload: str, model: str, estimator, budget: int,
              share: float = HEAD_TAIL_BUDGET_SHARE) -> tuple[list[Sentence], list[Sentence]]:
    """Keep source units from each end within a prompt-budget share apiece (10% unless a composition says so)."""
    all_units = sentences(payload)
    allowance = max(0, int(budget * share))

    def cost(items):
        if not items:
            return 0
        return estimator.messages(model, [{"role": "user", "content": " ".join(x.text for x in items)}])

    head = []
    for item in all_units:
        if cost(head + [item]) > allowance:
            break
        head.append(item)
    tail = []
    for item in reversed(all_units[len(head):]):
        if cost(tail + [item]) > allowance:
            break
        tail.insert(0, item)
    return head, tail


def _split_unit(item: Sentence, max_chars: int) -> list[Sentence]:
    """Hard-split one oversized unit at whitespace where practical, preserving offsets."""
    size = item.end - item.start
    if size <= max_chars:
        return [item]
    result = []
    cursor = 0
    while cursor < size:
        end = min(size, cursor + max_chars)
        if end < size and item.text and len(item.text) == size:
            boundary = item.text.rfind(" ", cursor + max(1, max_chars // 2), end)
            if boundary > cursor:
                end = boundary + 1
        text = item.text[cursor:end] if item.text and len(item.text) == size else ""
        result.append(Sentence(item.start + cursor, item.start + end, text))
        cursor = end
    return result


def chunks(items: list[Sentence], max_chars: int,
           overlap_fraction: float = CHUNK_OVERLAP_FRACTION,
           units: list[Sentence] | None = None) -> list[list[Sentence]]:
    """Pack by source-span size and repeat ~12% at boundaries.

    `units` restores line/sentence granularity when an item is a merged range
    with no text of its own. Overlap chunks are separate chunks for cap purposes.
    """
    if not items or max_chars < 1:
        return []
    normalized: list[Sentence] = []
    seen: set[tuple[int, int]] = set()
    for item in items:
        size = item.end - item.start
        if size > max_chars and units:
            restored = [unit for unit in units if unit.start >= item.start and unit.end <= item.end]
            if restored:
                for unit in restored:
                    key = (unit.start, unit.end)
                    if key not in seen:
                        normalized.extend(_split_unit(unit, max_chars))
                        seen.add(key)
                continue
        normalized.extend(_split_unit(item, max_chars))
    items = normalized
    overlap = max(1, int(max_chars * overlap_fraction))
    output: list[list[Sentence]] = []
    i = 0
    while i < len(items):
        current: list[Sentence] = []
        size = 0
        j = i
        while j < len(items) and (not current or size + items[j].end - items[j].start <= max_chars):
            current.append(items[j]); size += items[j].end - items[j].start; j += 1
        output.append(current)
        if j >= len(items):
            break
        # Back up to units whose overlap approximates the requested character share.
        next_i, overlap_size = j, 0
        while next_i > i + 1:
            candidate_size = items[next_i - 1].end - items[next_i - 1].start
            if overlap_size and abs(overlap_size - overlap) <= abs(overlap_size + candidate_size - overlap):
                break
            next_i -= 1
            overlap_size += candidate_size
        i = max(i + 1, next_i)
    return output


def bounded_question(text: str, max_chars: int) -> str:
    """Return only a bounded question/query, never the oversized document payload."""
    try:
        _, question, _ = parse_question(text)
    except UnsupportedOverflow:
        question = text[-max_chars:]
    return question[:max_chars]


def derive_context(original: str, history: list[tuple[int, dict]], source_event_id: int, model: str,
                   backend, estimator, budget: int, num_ctx: int, system_prompt: str,
                   retrieved: list[dict], options: dict | None, deadline: float,
                   progress, overflow_message: str = "",
                   composition: str = DEFAULT_COMPOSITION) -> tuple[dict, list[tuple[int, dict]]]:
    """Derive bounded source spans. Calls share the caller's ticket, deadline and total-call cap."""
    try:
        payload, question, question_range = parse_question(original)
    except UnsupportedOverflow as exc:
        suffix = "Supported fallback shape: a document payload followed by a final explicit Question: section."
        message = f"{overflow_message} {suffix}".strip() if overflow_message else f"{exc} {suffix}"
        raise BackendError("context_exceeded", message) from exc
    layout = COMPOSITIONS[composition]
    head, tail = keep_ends(payload, model, estimator, budget, layout["share"])
    protected = [(x.start, x.end) for x in head + tail]
    middle = [u for u in sentences(payload) if not any(u.start >= a and u.end <= b for a, b in protected)]
    max_chars = max(1, int(num_ctx * CHUNK_SIZE_FRACTION * estimator.ratio(model)))
    source_chunks = chunks(middle, max_chars)
    if not source_chunks or len(source_chunks) > MAX_EXTRACTION_CHUNKS:
        raise BackendError("context_exceeded", "The document exceeds the extraction chunk limit.")
    units = sentences(payload)
    source_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
    calls = 0

    def extract(parts: list[list[Sentence]], phase: str) -> list[Sentence]:
        nonlocal calls
        found_ranges: list[tuple[int, int]] = []
        for index, part in enumerate(parts, 1):
            if time.monotonic() >= deadline:
                raise BackendError("deadline", "The generation-wide model deadline expired.")
            calls += 1
            if calls > MAX_MODEL_CALLS:
                raise BackendError("context_exceeded", "The bounded extraction model-call limit was reached.")
            source = "\n".join(payload[u.start:u.end] for u in part)
            messages = [
                {"role": "system", "content": "You are a copying tool. Output only exact source text directly relevant to the question. Never paraphrase, answer in your own words, change labels, or invent text. If no source text directly matches, output exactly NONE."},
                {"role": "user", "content": question + "\n\nSource:\n" + source + "\n\nCopy exact matching source span(s) only; no labels or explanation."},
            ]
            call_options = dict(options or {}); call_options["temperature"] = 0
            stream = backend.chat(model, messages, call_options, deadline=deadline)
            try:
                for _part in stream:
                    pass
            except BackendError as exc:
                raise BackendError(exc.reason, exc.message, status=exc.status, detail=exc.detail) from exc
            # Support either one contiguous excerpt or one exact excerpt per output line.
            candidates = [line.strip() for line in stream.text.splitlines()
                          if line.strip() and line.strip().upper() != "NONE"]
            for candidate in candidates:
                local = find_exact_span(source, candidate)
                if local is None:
                    continue
                # Map through the newline-separated source units in this chunk.
                cursor = 0
                for unit_index, unit in enumerate(part):
                    unit_text = payload[unit.start:unit.end]
                    a, b = cursor, cursor + len(unit_text)
                    if local[0] < b and local[1] > a:
                        found_ranges.append((unit.start + max(0, local[0] - a),
                                             unit.start + min(len(unit_text), local[1] - a)))
                    cursor = b + (1 if unit_index < len(part) - 1 else 0)
            progress(phase, index, len(parts))
        return snap_and_merge(found_ranges, units)

    def selected_size(items: list[Sentence]) -> int:
        return sum(x.end - x.start for x in items)

    selected = extract(source_chunks, "extract")
    if not selected:
        raise BackendError("context_exceeded", "No source span matched the question; nothing was transformed.")

    def render(items: list[Sentence]) -> str:
        return compose(layout["order"], [payload[:head[-1].end]] if head else [],
                       [payload[x.start:x.end] for x in items],
                       [payload[tail[0].start:]] if tail else [], [question])

    changed_history = list(history)
    changed_history[-1] = (history[-1][0], {"role": "user", "content": render(selected)})
    depth = 1
    while True:
        try:
            choose_window(changed_history, system_prompt, model, estimator, budget, retrieved)
            break
        except ContextTooLarge as exc:
            if depth >= MAX_DEPTH:
                raise BackendError("context_exceeded", "The derived prompt still exceeds the model context.") from exc
            before = selected_size(selected)
            # A level partitions only retained spans; overlap remains bounded and
            # mapping stays in original-event coordinates.
            reduce_parts = chunks(selected, max_chars, units=units)
            if not reduce_parts or len(reduce_parts) > MAX_EXTRACTION_CHUNKS:
                raise BackendError("context_exceeded", "The derived context exceeds the bounded reduce limit.") from exc
            reduced = extract(reduce_parts, f"reduce-{depth}")
            after = selected_size(reduced)
            if not reduced or after >= before:
                raise BackendError("context_exceeded", "The reduce pass did not strictly shrink source text.") from exc
            selected = reduced
            depth += 1
            changed_history[-1] = (history[-1][0], {"role": "user", "content": render(selected)})

    ranges = []
    if head:
        ranges.append(("head", [0, head[-1].end]))
    ranges.extend(("middle", [item.start, item.end]) for item in selected)
    if tail:
        ranges.append(("tail", [tail[0].start, len(payload)]))
    ranges.append(("question", [question_range[0], question_range[1]]))
    sources = [{"event_id": source_event_id, "char_range": span, "source_sha256": source_hash, "role": role}
               for role, span in ranges]
    derived = {"method": "extractive_map_reduce", "version": 2, "depth": depth, "composition": composition,
               "text": changed_history[-1][1]["content"], "sources": sources}
    return derived, changed_history
