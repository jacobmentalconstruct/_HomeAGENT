"""Pure checks that a derived-context record agrees with the original event it came from."""

from __future__ import annotations

import hashlib

DERIVED_MARKER = "[Derived middle: extractive, source-linked context]"
METHOD = "extractive_map_reduce"
VERSION = 2

# How the derived prompt is put together. `share` is the part of the prompt budget kept from each end of the
# document; `order` is where the derived block sits among the kept head and tail. The question is always last.
COMPOSITIONS = {
    "baseline": {"share": 0.10, "order": ("head", "derived", "tail")},
    "small_ends": {"share": 0.05, "order": ("head", "derived", "tail")},
    "block_by_question": {"share": 0.10, "order": ("head", "tail", "derived")},
}
DEFAULT_COMPOSITION = "small_ends"  # the winner of the T5 eval (docs/EVAL-RESULTS.md)
_ROLE_RANK = {"head": 0, "middle": 1, "tail": 2, "question": 3}


def compose(order, head: list[str], middle: list[str], tail: list[str], question: list[str]) -> str:
    """The derived prompt text: kept pieces and the marked derived block in `order`, then the question."""
    parts = {"head": head, "derived": [DERIVED_MARKER, *middle], "tail": tail}
    segments = [piece for role in order for piece in parts[role]] + question
    return "\n".join(segment for segment in segments if segment)


def _valid_ranges(original: str, sources: list) -> list[tuple[int, int]] | None:
    """Ordered, non-overlapping, non-empty half-open ranges inside the original, or None."""
    ranges, previous_end = [], 0
    for source in sources:
        span = source.get("char_range") if isinstance(source, dict) else None
        if (not isinstance(span, (list, tuple)) or len(span) != 2
                or any(isinstance(n, bool) or not isinstance(n, int) for n in span)):
            return None
        start, end = span
        if not (previous_end <= start < end <= len(original)):
            return None
        ranges.append((start, end))
        previous_end = end
    return ranges


def verify_derived(original_event_text: str, derived_record) -> list[str]:
    """Problem codes for a derived record; an empty list means ranges, hash and text all agree.

    malformed, unsupported_method, no_sources, hash_mismatch, range_invalid, text_mismatch."""
    if not isinstance(derived_record, dict) or not isinstance(original_event_text, str):
        return ["malformed"]
    problems = []
    if derived_record.get("method") != METHOD or derived_record.get("version") != VERSION:
        problems.append("unsupported_method")
    text, sources = derived_record.get("text"), derived_record.get("sources")
    if not isinstance(text, str) or not isinstance(sources, list):
        return problems + ["malformed"]
    if not sources:
        return problems + ["no_sources"]
    digest = hashlib.sha256(original_event_text.encode("utf-8")).hexdigest()
    if any(not isinstance(s, dict) or s.get("source_sha256") != digest for s in sources):
        problems.append("hash_mismatch")
    ranges = _valid_ranges(original_event_text, sources)
    if ranges is None:
        return problems + ["range_invalid"]
    pieces = [original_event_text[a:b] for a, b in ranges]
    roles = [s.get("role") for s in sources]
    if all(role is None for role in roles):
        # Older records: baseline order, the marker line standing where the omitted middle was.
        if not any("\n".join(pieces[:k] + [DERIVED_MARKER] + pieces[k:]) == text for k in range(len(pieces) + 1)):
            problems.append("text_mismatch")
        return problems
    if any(role not in _ROLE_RANK for role in roles) or roles != sorted(roles, key=_ROLE_RANK.get):
        return problems + ["malformed"]
    composition = COMPOSITIONS.get(derived_record.get("composition", "baseline"))
    if composition is None:
        return problems + ["unknown_composition"]
    by_role = {role: [p for p, r in zip(pieces, roles) if r == role] for role in _ROLE_RANK}
    if compose(composition["order"], by_role["head"], by_role["middle"], by_role["tail"],
               by_role["question"]) != text:
        problems.append("text_mismatch")
    return problems
