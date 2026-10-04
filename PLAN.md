# Project plan

## Present

Onboarded 2026-10-04. Repository started at `main`, commit `dc623ae`.
The append-only SQLite event log rebuilds conversation history at startup.
Short-term context selects the newest messages that fit. Semantic retrieval,
embedding calls, and a vector index were absent. `docs/WORKFLOW.md` was supplied
by the USER and is untracked. The architecture check disallows third-party imports.

Baseline: Python 3.13.6, `python -B -m unittest discover -s tests` passed
174 tests in 136.531 seconds. No live model or vector service was involved.

## Target: _RAG_v1.0

Resume a persisted conversation and retrieve relevant older turns from that
conversation through a real persistent vector database. Include retrieved source
material in the bounded model prompt. Restarting preserves recall. Detaching the
optional memory cartridge leaves ordinary chat and transcript persistence usable.

Hard stops:

- A paraphrased query retrieves older material outside recent context into the
  actual model request and records source references.
- History and vector-backed recall survive a server restart.
- Indexing is idempotent and catches up from the authoritative event log.
- Retrieved material fits the context budget without displacing the newest user
  message or duplicating recent context.
- Detached or unavailable memory leaves chat usable and status visible.
- Embedding identity and vector dimensions are checked; incompatible indexes
  require an explicit rebuild.
- One real local embedding/vector store path is demonstrated; relevant checks
  pass and setup, limits, and recovery are documented.

## Current work

T1: local conversation RAG cartridge.
Approved: T1 (USER, 2026-10-04), including transcript indexing as derived memory.
Now: implementation and tidy are complete. Paused for USER review before parking.
Progress:
- [x] Add validated optional memory config and separate RAG requirements.
- [x] Add one Chroma adapter and Ollama embedding call, loaded only when enabled.
- [x] Reconcile the derived index from events and recover missing entries.
- [x] Retrieve within one conversation, enforce prompt budget, and record sources.
- [x] Expose memory status and keep failures from breaking chat.
- [x] Add focused tests and update operator, API, architecture, and README docs.
- [x] Run full verification, inspect the final diff, and tidy.
- [x] Repair pass: scope reconciliation to the active conversation and persist embedding dimensions.
- [x] Repair Chroma metadata update so dimensions persist without attempting to modify its immutable distance setting.
- [x] Record retrieval watchlist for bounded query context, relevance filtering, and transient recovery.

Expected outcome: optional persistent same-conversation retrieval, with the event
log as authority and normal chat functioning when memory is detached.

Scope:

1. Add validated optional memory config and a separate RAG requirements file.
2. Add one Chroma persistent adapter and an Ollama embedding call, lazily loaded.
3. Reconcile the derived index from authoritative events before retrieval and
   recover missing entries after restart.
4. Retrieve only from the active conversation; budget sources with recent context
   and record source references.
5. Expose attached, disabled, or degraded status; memory failures do not break chat.
6. Add focused checks for recall, scope, budget, recovery, compatibility, and
   graceful detach. Update operator and architecture docs.
7. Tidy and review against the hard stops. Pause for USER review before parking.

Non-goals: a second cartridge, other embedding providers, Graph RAG, live
attach/detach, UI redesign, broad refactoring, autonomous summaries or facts,
document import, and cross-conversation retrieval.

Acceptance: tests show older paraphrased recall in the actual prompt, source
references, same-conversation filtering, budget safety, restart reconciliation,
embedding metadata validation, and detached operation. Existing tests pass. Run
a real Ollama and Chroma smoke if local prerequisites are available; otherwise
record the missing prerequisites precisely.

Known risks: Chroma wheel compatibility; embedding resource use alongside chat;
models replaced under an unchanged name; retrieval quality; first reconciliation
latency.

Review repair pass: the two inexpensive hygiene items are closed without changing
the RAG target. The remaining retrieval-policy observations are tracked in
`docs/MEMORY_WATCHLIST.md` and remain provisional until symptoms justify a new
tranche.

## Decisions

- SQLite event history remains authoritative; the vector index is derived data.
- Retrieval scope is the resumed conversation only.
- Cartridge attach/detach is configuration-driven and takes effect on restart.
- Ship one vector implementation, Chroma, plus a disabled mode.
- Use Ollama's local `/api/embed` endpoint. No cloud service is required.
- Keep the dependency optional and lazy so ordinary chat still works without it.
- Chroma PersistentClient documentation identifies this as suited to local
  development and testing, which is appropriate for this prototype.

References: [Ollama embedding API](https://ollama.com/blog/embedding-models);
[Chroma Python client](https://docs.trychroma.com/reference/python).

## Backlog

Deferred beyond v1: Graph RAG, further database adapters, document ingestion,
autonomous fact extraction, summaries, knowledge editing or approval UI,
cross-conversation retrieval, accounts, cloud sync, rerankers, hybrid retrieval,
live cartridge switching, and unrelated cleanup.

## Log

- 2026-10-04 onboarding: reviewed workflow, architecture, composition, history,
  context selection, generation, and restart tests. Baseline above.
- 2026-10-04 USER approved T1 and derived transcript indexing. Ollama embedding
  and Chroma persistent client verified from primary docs.
- 2026-10-04 final verification: `python -B -m unittest discover -s tests`
  passed 189 tests in 139.494 seconds. `git diff --check` reported no whitespace
  errors.
- 2026-10-04 live smoke: with Chroma 1.3.5, Ollama `nomic-embed-text`, and
  `qwen2.5:1.5b`, a temporary local conversation dropped three recent-context
  messages, retrieved the older workshop color from Chroma, and answered
  “Violet.” After reopening the app, it retrieved the same sources and answered
  “The workshop remains violet.” Temporary runtime files were removed.
- Current state: on `t1-local-rag`; implementation and tidy complete; awaiting
  USER review before parking or merging. No live process remains.
- 2026-10-04 review repair pass: reconciliation now reads only the active
  conversation's events, and the first successful embedding persists
  `embedding_dimensions` in collection metadata. Focused tests passed; full
  verification and independent review remain before parking.
- 2026-10-04 repair verification: `python -B -m unittest discover -s tests`
  passed 190 tests in 141.155 seconds; `git diff --check` reported no
  whitespace errors. At that point a delegated second review and Git commit
  were waiting because the approval service reported the account usage limit;
  this was resolved in the later review repair below.
- 2026-10-04 review repair: review identified that Chroma 1.3.5 rejects
  `Collection.modify()` when copied metadata includes `hnsw:space`. Reproduced
  the rejection against real Chroma with a disposable index. The cartridge now
  drops only `hnsw:space` from the metadata update; real Chroma persisted the
  768 dimension while its collection configuration remained cosine. A metadata
  write failure alone is non-fatal because the dimension remains in memory and
  reopen can recover it by sampling a stored vector. The test fake now rejects
  attempts to modify `hnsw:space`; fresh-index retrieval, reopen, dimension
  mismatch, and non-fatal metadata-write behavior are covered.
- 2026-10-04 repair verification: focused command
  `python -B -m unittest tests.test_memory tests.test_status tests.test_window tests.test_conversation`
  passed 52 tests in 16.714 seconds. Full command
  `python -B -m unittest discover -s tests` passed 192 tests in 139.302
  seconds. A fresh runtime with Chroma 1.3.5, Ollama `nomic-embed-text`, and
  `qwen2.5:1.5b` retrieved the older workshop-color turn into the actual model
  prompt with source `conversation:2`, answered “violet”, and reported memory
  ready with dimension 768. After a separate process restart, it recovered the
  stored dimension, returned the same source reference in the actual prompt,
  answered “violet”, and remained ready. Collection configuration stayed
  cosine. All repair smoke runtime files were removed. The earlier T1 live
  smoke recorded above predated the review repair pass and did not exercise this
  first-embedding metadata update; this smoke was run after the fix.
- 2026-10-04 independent review: `6219ac6` passed read-only review with no code
  defects found. `python -B -m unittest tests.test_memory` passed 10 tests;
  full-suite evidence remains the 192-test run above. `git status` is clean,
  `HEAD` matches `origin/rag-implementation`, and
  `git diff --check origin/main...HEAD` is clean. T1 remains unparked pending
  USER review and acceptance; no merge has been made.
