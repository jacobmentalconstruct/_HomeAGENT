# Project plan

## Present

Onboarded 2026-10-04. Repository started at `main`, commit `dc623ae`.
The append-only SQLite event log remains authoritative and rebuilds conversation
history at startup. Short-term context selects the newest messages that fit.
T1 adds optional local conversation retrieval using Ollama embeddings and a
persistent Chroma index. The implementation is on `rag-implementation`;
`main` remains the last accepted state pending the USER's merge decision.
`docs/WORKFLOW.md` was supplied by the USER and is included on the branch. The
architecture check disallows third-party imports.

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

T2: public-release polish (active).
Approved: T2 (USER, 2026-10-04).
Now: Verify public documentation and complete the full suite.
Progress:
- [x] Disable Chroma telemetry at client creation and test the setting.
- [x] Repair architecture, configuration, security, and README documentation.
- [ ] Run focused and full tests, inspect the diff, and park T2.

Expected outcome: the optional conversation memory cartridge disables Chroma
telemetry, and public documentation accurately describes its dependency, data,
configuration, and limits.

Scope: the Chroma client setting and its focused test; the specified architecture,
configuration, security, and README edits; verification and a parking record.

Non-goals: retrieval changes, watchlist work, new memory adapters, and merge.

Acceptance: `python -B -m unittest tests.test_memory` and
`python -B -m unittest discover -s tests` pass; `git diff --check` is clean;
no document claims unqualified standard-library-only operation; the final diff
contains only T2 work.

Known risk: Chroma is optional in test environments, so its settings assertion
must use a fake module rather than requiring the package.

Previous parked work: T1 local conversation RAG cartridge.
T1 progress:
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

The following retrieval observations remain a watchlist. They are not current
defects or commitments; use the recorded symptoms to decide whether a later
tranche is warranted.

- **Bounded query context:** Retrieval currently uses only the raw current user
  prompt. Short follow-ups such as “and the other one?” may not find the intended
  turn. Watch for repeatable follow-ups that clearly refer to older material but
  return no useful source, or return an unrelated source while the subject is in
  recent conversation. If this occurs, consider combining the prompt with a
  small bounded amount of recent context.
- **Relevance filtering:** The configured top-k results have no distance cutoff,
  so weak matches may enter the prompt. Watch for clearly unrelated excerpts,
  especially with vague queries and large histories. If this occurs, measure
  distances for the active embedding model before choosing a calibrated cutoff.
- **Transient degraded recovery:** An Ollama or Chroma error leaves memory
  degraded until process restart, while chat continues. Watch for a service
  recovering while later replies continue to report degraded memory. If this
  occurs, consider bounded retries or re-probing with explicit latency limits
  and backoff during sustained outages.

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
  “The workshop remains violet.” The temporary runtime directory for this smoke
  was removed.
- Historical state before branch publication: on `t1-local-rag`; implementation
  and tidy complete; awaiting USER review before parking or merging. No live
  process remained.
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
  cosine. The temporary `smoke-rag-repair-20261004/` runtime and fixture files
  were removed. The earlier T1 live smoke recorded above predated the review
  repair pass and did not exercise this first-embedding metadata update; this
  smoke was run after the fix.
- 2026-10-04 independent review: `6219ac6` passed read-only review with no code
  defects found. `python -B -m unittest tests.test_memory` passed 10 tests;
  full-suite evidence remains the 192-test run above. `git status` is clean,
  `HEAD` at that review point was `6219ac6` on `origin/rag-implementation`, and
  `git diff --check origin/main...HEAD` was clean. At that review point T1
  remained unparked pending USER review and acceptance; no merge had been made.
- 2026-10-04 close-out: `40b7ef7` is the final reviewed T1 head and adds only a
  `PLAN.md` clarification of the completed review and current status on top of
  `6219ac6`; it changes no source or tests. The authoritative review/merge
  candidate is `rag-implementation`, tracking `origin/rag-implementation`.
  `t1-local-rag` is the historical local branch
  at `d3f58b3` and is not the candidate branch. The untracked
  `.tmp_chroma_modify_probe/` directory was a disposable Chroma reproduction
  index (one empty `probe` collection, zero embedding rows); it was removed
  after review. Smoke cleanup entries above refer to the temporary smoke runtime
  and its fixture files.
- 2026-10-04 parked T1, local conversation RAG cartridge. Outcome: the optional
  cartridge provides persistent same-conversation semantic recall from older
  completed transcript turns, includes source references in the actual prompt,
  survives a process restart, and leaves chat usable when detached or degraded.
  Scope and non-goals held; T1 is parked on `rag-implementation` and has not
  been merged.
  Evidence: `python -B -m unittest tests.test_memory tests.test_status tests.test_window tests.test_conversation`
  passed 52 tests in 16.714 seconds; `python -B -m unittest discover -s tests`
  passed 192 tests in 139.302 seconds. After the Chroma fix, a fresh runtime
  smoke harness ran `python -B smoke_rag_repair.py first` and then
  `python -B smoke_rag_repair.py reopen` in a separate process with Chroma 1.3.5,
  Ollama `nomic-embed-text`, and `qwen2.5:1.5b`. Both runs recalled “violet” with
  the same source reference in the actual model prompt; memory stayed ready and
  retained dimension 768, with cosine distance unchanged. The temporary harness
  and runtime were removed. `git diff --check`, the 10-test memory review run,
  and the independent review were clean. Limitations: retrieval remains local,
  conversation-scoped, and based on the raw prompt; quality depends on embeddings
  and top-k, and memory does not auto-recover from transient failure before
  restart. Deferrals: bounded query context, relevance filtering, and transient
  degraded recovery are recorded in Backlog above, alongside the existing v1
  exclusions. Next provisional step: the USER decides whether to merge
  `rag-implementation` into `main`; no merge was performed.
