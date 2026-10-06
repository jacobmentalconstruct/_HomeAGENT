# Changelog

## 0.2.1 (2026-10-05)

Pre-merge fixes from the release audit. No new features.

### Fixed

- Sentence splitting no longer drops a closing quote or bracket after the end of a sentence (`He said "stop." Then
  left.` kept the closing quote with no unit). Every non-whitespace character now belongs to exactly one source unit;
  a property test checks this over 3,000 random documents. The eval fixtures' units are unchanged.
- Keyword (FTS5) queries drop control characters. A NUL in a question used to make the query fail and mark the keyword
  tier faulted.
- `runtime/config.json` is written atomically on first run and when defaults are filled in (a temporary file, then a
  swap), like the other config writes, so a failed write leaves the old file intact and no temporary file behind.

### Documented

- What a follow-up question sees after a fallback reply (not the document, nor anything older), and how memory treats
  long turns.
- The `store_reason` status field in the API and configuration docs.
- Five audit items in `docs/BACKLOG.md`, not implemented.
- `docs/HISTORY.md`: the repository's three epochs (0.1.0, RAG v1.0, context scaling) and how they join on `main`.

## 0.2.0 (2026-10-05)

Closes the context-scaling prototype described in [docs/PROJECT-CHARTER.md](docs/PROJECT-CHARTER.md).

### Added

- **Overflow fallback** for one message too large for the model: a document followed by a final `Question:` line. The
  model copies the passages that bear on the question; the harness sends those with the kept start and end of the
  document and the question. The original message is never changed. Switch: `overflow_fallback` (default on).
- **Provenance you can check.** Each derived record lists the source character ranges, the source hash, the
  composition and each piece's role. `verify_derived` recomputes them from the original message. The page shows a
  collapsed **Derived context** block with the text the model was sent and the ranges it came from.
- **Document + Question fields** on the page. They join a pasted document and a question into the shape above; the
  server sees an ordinary message (still limited to 20,000 characters).
- **Measured results**: eight fixtures, five local models, three prompt compositions, in
  [docs/EVAL-RESULTS.md](docs/EVAL-RESULTS.md). Reproduce with `python -B -m tests.eval.runner`.
- **Conversation memory works out of the box**: on by default, with an FTS5 keyword index that needs no extra packages
  next to the vector tier (Chroma, or SQLite vectors without Chroma). Status reports `ready`, `degraded` or `disabled`
  with the tier in use, a machine-readable reason and fix text, shown on the page and by `harness.py status`.
- Memory recovers by itself after an embedding failure: a bounded background re-probe (5 s doubling to 300 s).
- Size limits for one message documented against `num_ctx` (CONFIGURATION, "Size limits for one message").
- Live checks: `tests/live_memory_probe.py` (with `--backlog N`), and the release smoke matrix in
  [docs/SMOKE-MATRIX.md](docs/SMOKE-MATRIX.md).

### Changed

- The default prompt composition is `small_ends` (5% of the budget kept from each end of the document). It was chosen
  by the pre-declared winner rule on a near-tie: all three compositions met the same two thresholds, and `small_ends`
  led `baseline` by one correct answer and one extraction pass out of 120 runs.
- `requirements-rag.txt` is now `requirements.txt` (Chroma, recommended, not required).
- Only `harness.py serve` opens the memory stores; the other commands never touch them.
- The SQLite vector store indexes `conversation_id`.
- The `gui` command explains how to run `serve` when tkinter is missing instead of failing with a traceback.

### Known limitations

- Small models can answer wrongly without any warning when extraction finds some passages but not the answer: four of
  40 runs under the default composition, all with the 0.5B and 2B models. Use a model of 4B or larger for oversized
  messages. Two eval thresholds (answer passage found in 100% of fixtures for models of 1.5B and up, 7/8 for 0.5B) were
  missed and are recorded, not tuned away.
- At `num_ctx` 8,192 with a 256-token reply, or at 16,384, the fallback is never reached from the page, because every
  message the server accepts already fits.
- The llama.cpp adapter has only been tested against a scripted fake server.

## 0.1.0

The local chat harness: the phone-friendly page, the control panel, the append-only event log, the bounded
recent-message window with a self-correcting token estimate, the Ollama and llama.cpp adapters, and optional Chroma
conversation memory.
