# Close-out scope: T3–T6

Full scope, non-goals, and exit criteria for the T3–T6 tranches. T2 scope lives in PLAN.md.
These declarations are provisional until each tranche is reached; evidence from completed
work may refine the path. Each tranche becomes active only after explicit USER approval.

---

## T3 RAG Default, Graceful States, Lexical Tier

Branch: `t3-rag-default` (off `RAG-SUM-GRAPH`)

Expected outcome: conversation memory is on by default for new configs; the system reports
a three-tier state machine with machine-readable reasons; the FTS5 lexical tier is always
maintained so embeddings have an instant backup; the full suite passes with chromadb absent
and present; a live check on this machine passes under three conditions.

Scope:
1. New configs: `memory.enabled true`. Existing configs keep their value. `harness.py status`
   and the page say when memory is disabled in config and how to enable it.
2. States `ready` / `degraded` / `disabled` with machine-readable reasons
   (`embedding_model_missing`, `index_incompatible`, `transient`, `all_tiers_failed`) and
   human fix text. Chroma being absent is informational only because tier 2 takes over.
   Show in `/api/status`, the page (informational vs warning), and `harness.py status`.
   No tracebacks.
3. Detect a missing embedding model from the backend's model list and report the pull command.
4. `enabled=false` means disabled: neither chromadb nor any SQLite memory store is opened.
5. Rename `requirements-rag.txt` to `requirements.txt` (chromadb pinned range, labelled
   "recommended"); update every reference. README quick-start gets the install step and says
   chat and recall work without it through the SQLite fallback.
6. Latency: index finished turns at reply completion; background startup catch-up; cap
   indexing inside one retrieval (bounded batches and time). The event log stays
   authoritative; indexing stays idempotent. Fake-embedder tests prove no unbounded
   first-reply stall.
7. Lexical tier (FTS5), REQUIRED: maintain an FTS5 table in `runtime/memory/vectors.sqlite3`
   (columns: `text`, plus UNINDEXED `conversation_id`, `event_seq`, `role`), reconciled
   idempotently from the event log whenever memory is enabled. Sanitize queries (quote each
   term, OR them; no raw FTS syntax from user text), rank with bm25, scope to the
   conversation, and map to the existing source record with a documented distance transform
   and `method: "lexical"`. Use it when embeddings are unavailable at startup or an embedding
   call fails during a reply (per-reply fallback; do not mark memory degraded on one call
   failure). Check FTS5 support at runtime; if absent, report a clear reason and state
   degraded only if no other tier works. Status shows the active tier and a note that
   paraphrase recall is weaker. Tests: scoping, ranking, special characters and operators in
   queries (quotes, AND, NEAR, colons), FTS5 absent simulation, per-reply fallback, idempotent
   reconcile.
8. Tests: the suite passes with chromadb absent and present, and with memory default-on. Tests
   that do not need memory disable it explicitly. No test calls a real embedding service. Keep
   the architecture test's no-static-third-party-import rule.
9. Docs: README, ARCHITECTURE, CONFIGURATION, SECURITY (default-on means a plaintext copy of
   conversation text under `runtime/memory/` by default, and how to disable and delete it),
   API (status states, store, tier, reason, source `method`), charter invariant.

Non-goals: relevance-cutoff or query-composition changes, hybrid ranking, cross-conversation
retrieval.

Exit criteria:
- All done; full suite green with chromadb absent AND present.
- Live check on this machine: Chroma importable, with chromadb blocked, and with the
  embedding model unavailable; each produces a clear status and correct behavior.
- Parked with evidence.

---

## T4 Harden (no new features)

Branch: `t4-harden` (off `RAG-SUM-GRAPH`)

Expected outcome: provenance and invariants are verifiable; the overflow fallback has a config
switch; the page shows derived context; memory has bounded re-probe; the dependency policy
table is complete; known limits are documented; the suite is green.

Scope:
1. Test: derived context never outlives the reply's window record across a store reopen.
2. Pure function `verify_derived(original_event_text, derived_record)` that checks ranges,
   hash, and transformed text agree; tests for pass, wrong hash, wrong range, tampered text.
3. Config switch for the overflow fallback (default on) with tests: off gives today's visible
   `context_exceeded` with the original numbers.
4. Page shows the derived block and its source ranges (textContent only, never HTML),
   collapsed by default; no new framework or build step.
5. README: how to use the fallback (the `Question:` shape), its limits, failure behavior.
6. Memory: bounded re-probe with backoff after a transient failure (explicit limits, tested).
7. Document known limits: llama.cpp reactive path and real-server testing, snapping
   granularity, chunk and call caps (overlap counts toward the 8-chunk pass cap).
8. ARCHITECTURE "Dependency policy" table: every external dependency and its backup
   (Chroma → SQLite vectors; embeddings → FTS5; Ollama chat → llama.cpp adapter;
   nvidia-smi → panel shows nothing; tkinter → CLI and server). Add an absent-dependency
   test pattern (e.g. blocking a module in `sys.modules`) reused for each.
9. Audit only files touched by this tranche for defects; fix confirmed ones, log the rest
   in `docs/BACKLOG.md`.

Non-goals: new features, new retrieval strategies, anything not listed above.

Exit criteria:
- All done; full suite green; parked with evidence. Nothing else.

---

## T5 Measure and Compose

Branch: `t5-measure` (off `RAG-SUM-GRAPH`)

Expected outcome: an eval fixture set and runner report extraction and answer quality across
five models; a prompt-composition winner is chosen by the numbers; a Document + Question UI
exists on the page.

Scope:
1. `tests/eval` fixture set (~8): middle fact, wrapped text, unpunctuated text, absent fact,
   two facts, fact near head/tail boundary, duplicated sentence, long question.
2. Eval runner: for each model and fixture record extraction result (was the answer sentence
   in the derived text?), the final answer, correctness, model calls, wall time. Models:
   `qwen2.5:0.5b`, `1.5b`, `qwen3.5:2b`, `4b`, `9b`. Write results to a file under `docs/`.
3. Prompt-composition variants, at most 3: baseline; smaller head/tail; derived block placed
   adjacent to the question. Pick the winner by the numbers. No further variants.
4. Page: add Document and Question fields that compose the existing `...\nQuestion: ...`
   message shape in the browser. No backend parsing changes.

Non-goals: relevance-cutoff or query-composition changes unless T5 numbers show them hurting,
hybrid ranking, cross-conversation retrieval.

Exit thresholds (fixed before running):
- The answer sentence is in the derived text in 100% of fixtures for models ≥ 1.5B and ≥ 7/8
  for 0.5B.
- Final-answer correctness ≥ 80% for models ≥ 4B (report, do not gate, for smaller).
- The absent-fact fixture fails visibly every time.
- Timings reported, not gated.

If a threshold is missed after the allowed variants, record it as a known limitation and stop.
The tranche ends either way.

Exit criteria:
- Fixture set and runner complete; results in `docs/`; composition winner chosen; page UI done;
  thresholds met or recorded as named limitations; parked with evidence.

---

## T6 Release

Branch: `t6-release` (off `RAG-SUM-GRAPH`)

Expected outcome: the project is tagged v0.2.0, all docs are final and accurate, the suite
passes from a fresh clone, and a live smoke matrix is recorded. The USER merges to `main`.

Scope:
1. Final doc pass: README, ARCHITECTURE, CONFIGURATION, API, SECURITY. Note: derived text is
   stored in the event log in plaintext; no graph is built.
2. Version bump to 0.2.0 with a short CHANGELOG.
3. Full suite from a fresh clone with and without chromadb installed.
4. Live smoke matrix recorded.
5. PLAN.md final park: "project complete" with the deferred list.
6. Delete merged feature branches (tranche branches fast-forwarded into `RAG-SUM-GRAPH`).
7. Git tag `v0.2.0`.
8. Stop. The USER merges `RAG-SUM-GRAPH → main`.

Non-goals: new features; anything not in the list above.

Exit criteria:
- All items complete; suite green from fresh clone; smoke matrix recorded; tag pushed;
  PLAN.md says "project complete". USER performs the final merge.

---

## Deferred (do not build in any tranche)

History-overflow condensing, reuse cache table, graph construction, larger-model routing,
relevance-cutoff changes (unless T5 numbers show harm), hybrid ranking, cross-conversation
retrieval, new input formats, automatic strategy learning, plugin registries, multi-model
fallback for overflow, cloud services.
