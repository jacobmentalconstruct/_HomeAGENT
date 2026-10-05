"""Pure checks that a derived-context record agrees with the original event it came from."""

from __future__ import annotations

import hashlib

DERIVED_MARKER = "[Derived middle: extractive, source-linked context]"
METHOD = "extractive_map_reduce"
VERSION = 2


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
    # The derived text is the source pieces in order, joined by newlines, with the marker line
    # standing where the omitted middle was.
    if not any("\n".join(pieces[:k] + [DERIVED_MARKER] + pieces[k:]) == text for k in range(len(pieces) + 1)):
        problems.append("text_mismatch")
    return problems
