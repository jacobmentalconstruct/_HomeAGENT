# Project plan

## Active direction: context scaling (2026-10-04)

The active project purpose and prototype stop conditions are in
[`docs/PROJECT-CHARTER.md`](docs/PROJECT-CHARTER.md). That charter supersedes the
former _RAG_v1.0 target and its non-goals. The completed RAG work remains part of
the codebase and its record below is preserved as historical reference; it is
not the active roadmap.

### Current state

This is a Git checkout on branch `t1-bounded-overflow-extraction`, created from
T0 commit `fae95c1` on `RAG-SUM-GRAPH`; the T0 commit was pushed to
`origin/RAG-SUM-GRAPH`. Earlier inspection occurred before Git metadata was
attached; the prior no-Git statements record that initial observation and are
now superseded. Historical RAG branch names, commit IDs, and merge status below
describe the source project. T1 runtime work is checkpointed at `27ad048`;
the final parking commit on this branch records API/documentation and
verification evidence.
Existing harness behavior and the focused context/memory/architecture baseline
were reviewed; 38 tests passed with
`python -B -m unittest tests.test_architecture tests.test_memory tests.test_window -q`
on 2026-10-04. The T1 full suite passed 203 tests on 2026-10-04.

The local overflow probe is recorded in `docs/PROJECT-CHARTER.md`: on Ollama
0.18.3 with `qwen2.5:0.5b` and `num_ctx=2048`, default truncation accepted the
oversized request with HTTP 200 and `prompt_eval_count=2048`; `truncate=false`
produced HTTP 400, `the input length exceeds the context length`. This evidence
applies to that local configuration only.

### Previous tranche: T0 project re-baseline (parked)

Approved: T0 (USER, 2026-10-04)

Expected outcome: project purpose, stop conditions, workflow, active plan, and
public overview describe the context-scaling prototype; prior RAG history is
plainly historical and retained; the next implementation proof is bounded and
resumable.

Scope:

1. Add a project charter that defines desired prototype state, invariants,
   stop conditions, current constraints, and deferred directions.
2. Update the active plan and workflow to support explicit, crash-resumable
   checkpoints.
3. Align README and architecture overview with the new direction while keeping
   claims about implemented behavior accurate.
4. Record this baseline, evidence, and next step here without changing runtime
   behavior or user data.

Non-goals: implement overflow fallback; alter tests or source code; remove old
project history; add summary, graph, extraction, routing, or storage features;
publish or merge anything.

Acceptance:

- `docs/PROJECT-CHARTER.md` defines the prototype target and measurable stop
  conditions.
- `PLAN.md` makes the new direction active and labels the former RAG plan as
  historical without erasing its evidence.
- README and architecture descriptions distinguish implemented behavior from
  intended behavior.
- Workflow explains tranche approval and records explicit state and verification
  evidence.
- The T0 documentation commit is present before T1 work begins; changed docs are
  inspected and test evidence is represented accurately.

The original T0 environment observation that Git metadata was absent was
superseded when this managed checkout appeared. The current Git state is above.

The initial T0 documentation baseline is in commit `dfcc9f1`; the amended T0
follow-up was committed and pushed as `fae95c1` before T1 began.
Progress:
- [x] Add charter and recovery-oriented plan/workflow.
- [x] Align README and architecture overview.
- [x] Inspect resulting docs and park T0 with evidence and next step.

T0 verification and close-out (2026-10-04):

- Added `docs/PROJECT-CHARTER.md` with desired prototype state, proof target,
  stop conditions, invariants, limits, deferrals, and recovery rule.
- Updated README and architecture overview to label the context-scaling purpose
  as direction and describe current behavior accurately.
- Updated workflow for no-Git snapshots and resumable checkpoints.
- Preserved all prior RAG plan and log text below as historical reference.
- `rg -n "deliberately nothing more|Target: _RAG_v1.0|no tools|no automatic cross-conversation|T1|T2|Git checkout|context scaling|context-overflow" README.md PLAN.md docs` confirmed former scope claims are in the labeled historical plan or legacy notes; current README and charter state the new direction.
- Manual readback of the charter, active plan, README, architecture, and workflow found the active/implemented distinction consistent. No code or runtime data changed. No tests were run after these documentation-only edits; the previously recorded 38-test focused baseline predates T0 and is not a full-suite result.
- Historical limitation at initial inspection: Git metadata was not visible then. The managed checkout is now available; its branch and base commit are recorded above.
- T0 follow-up docs were committed as `fae95c1` and pushed before T1 began on
  `t1-bounded-overflow-extraction`.

## Log

- 2026-10-04 T0 parked: project documentation re-based to context scaling.
  Acceptance met. Changed files: `PLAN.md`, `README.md`,
  `docs/PROJECT-CHARTER.md`, `docs/WORKFLOW.md`, `docs/ARCHITECTURE.md`,
  `docs/MEMORY_WATCHLIST.md`, and `docs/CONTEXT-OVERFLOW-FALLBACK-ARCHITECTURE.md`.
  Prior RAG planning and verification history remains below, labeled historical.
  Evidence and limitation are recorded under T0 verification and close-out
  above. No source, tests, or runtime data changed in the initial T0 baseline.
  The follow-up alignment was committed as `fae95c1` and pushed before T1
  started; details and verification are recorded below.

- 2026-10-04 T1 parked on `t1-bounded-overflow-extraction`. Commits
  `3a3b3cb` and `27ad048` contain the user-approved truncate-control and
  bounded-extraction tasks; the final commit closes the API/docs task.
  Verification: local `qwen2.5:0.5b` raw oversized request failed visibly,
  integrated fallback answered `COBALT, VIOLET, and MARIGOLD.` with
  `prompt_eval_count=256`; 203 automated tests passed. Known boundary: only the
  explicit final `Question:` input shape is supported, extraction is exact-
  sentence validated, and one local model run is not a general reliability
  claim. Await USER acceptance; no merge to `main` yet.

## Completed work: T0 documentation alignment

Approved: T0 (USER, 2026-10-04)

Expected outcome: record the amended, approved T1 proof and operator/API
semantics in the project docs, clarify the active Git workflow, and preserve
the previous RAG plan as clearly historical material. Commit these docs before
beginning T1.

Scope:

1. Update T1 scope and acceptance criteria with normal near-limit behavior,
   queue/deadline/chunk/progress limits, named fixture parameters, second and
   negative fixtures, and API window metadata.
2. Move T1 parameters and Ollama probe evidence out of the charter and into the
   active T1 declaration.
3. Update `API.md`, configuration docs, README, workflow, and overflow concept
   paper; remove its obsolete builder instructions and unbounded self-loop.
4. Correct the stale Git state and demote headings in the preserved RAG plan.
5. Review doc consistency, then commit only in-scope documentation as `T0 wip:`.

Non-goals: source/test changes, starting T1 implementation before the T0 commit,
altering runtime user data, deleting historical RAG evidence, or publishing.

Acceptance:

- All USER-requested T1 additions below appear in the declaration and relevant
  API/config docs.
- The charter contains product purpose and general invariants, not T1 parameters.
- The overflow concept paper no longer contains the obsolete Builder
  Instructions or a self-referential flow edge.
- `WORKFLOW.md` restores the original approval-before-implementation steps.
- README links the charter; `PLAN.md` records the active Git state and marks the
  old RAG plan as historical by its heading hierarchy.
- The T0 documentation commit exists before any T1 implementation commit.

Progress:
- [x] Update charter, plan, overflow paper, workflow, README, API and config docs.
- [x] Inspect resulting docs and commit the T0 checkpoint.

T0 verification and close-out (2026-10-04):

- Read back the active charter, plan, workflow, README, API, configuration,
  and overflow concept paper. T1 acceptance language is consistent; prior RAG
  content remains under demoted historical headings.
- `git diff --check` passed. No tests were run because this checkpoint changes
  documentation only; the earlier 38-test focused baseline predates this
  checkpoint.
- Changed files: `PLAN.md`, `README.md`, `docs/API.md`,
  `docs/CONFIGURATION.md`, `docs/CONTEXT-OVERFLOW-FALLBACK-ARCHITECTURE.md`,
  `docs/PROJECT-CHARTER.md`, and `docs/WORKFLOW.md`. No source, tests, or
  runtime data changed.
- T0 checkpoint: commit `fae95c1` (`T0 wip: align context scaling plan`) was
  pushed to `origin/RAG-SUM-GRAPH` before T1 began.

## Current work: T1 bounded overflow extraction repair

Approved: T1 reopen (USER, 2026-10-04)

Status: review defect repaired and verified; parked pending USER acceptance.
Prior T1 implementation and verification remain the baseline. No merge is
authorized.

Approved: T1 repair follow-up (USER, 2026-10-04)

Accepted review defect: `chunks()` measured `len(item.text)`, but merged source
spans intentionally have empty text. As a result, reduction treated all spans
as zero-size and packed them into one chunk. The follow-up must size by source
offsets, restore oversized merged spans to their enclosing units before packing,
and prove both multi-chunk reduction and fail-closed non-shrinking behavior.

Amended repair scope:

1. Preserve the existing `ContextTooLarge` diagnostic verbatim and append a
   concise hint describing the supported explicit `Question:` input shape.
2. Replace sentence-set matching with source-span matching: character-size
   chunks with approximately 10–15% overlap, boundaries aligned to lines or
   sentences when available, whitespace-normalized exact-substring validation,
   outward snapping to enclosing source units, and merged source ranges. Add a
   hard-wrapped, unpunctuated fixture.
3. Replace the single combine pass with bounded recursive reduction. Each level
   must strictly shrink the selected source text; cap total model calls, enforce
   a depth backstop of four, and share the existing generation deadline.
4. Record the question's exact source range from its parse offset rather than
   searching for the marker again.
5. Bound retrieval input for oversized user messages; do not embed/retrieve the
   entire document payload.
6. Fail immediately with `context_exceeded` when the system prompt itself is
   too large; it is not an extractable user payload.
7. Document supported shape limits and that reactive overflow retry is
   Ollama-only; preflight remains the primary cross-backend trigger.
8. Add focused tests for these repairs, rerun the full suite and local smoke,
   then park the repair for USER acceptance without merging.
9. For the accepted review follow-up, use source offset lengths for chunk sizing,
   split oversized merged spans back to units, test multi-chunk reduction and
   non-shrinking failure, and clarify overlap accounting and snap granularity.

Expected outcome: when one oversized user message contains a document payload
followed by an explicit `Question:` section, the harness preserves the question
verbatim, replaces only a bounded portion of the payload with question-focused
source spans, and answers a fixed fact question within the configured
context. The reply window record shows the derived representation and its source
provenance. Other chat behavior and the original event history remain usable.

Scope:

1. Define and parse the T1 input shape: document payload followed by an explicit
   final `Question:` section. Preserve that question exactly; malformed or
   unsupported oversized messages fail visibly.
2. Keep preflight as the primary trigger at `ContextTooLarge`. Configure the
   Ollama chat request not to truncate server-side; recognize its specific
   context-overflow response as one reactive fallback trigger on Ollama only.
   Permit only one fallback attempt for a generation.
3. Reserve 10% of the prompt budget each for verbatim payload text from the
   beginning and end, ending at available line/sentence boundaries. Split the
   middle into size-based context-fitting chunks with 10–15% overlap. Ask the
   selected local model at temperature zero to copy relevant source spans.
   Mechanically validate each candidate as a whitespace-normalized exact source
   substring, snap outward to enclosing units, and merge overlapping ranges.
   If the final prompt remains too large, recursively reduce under strict
   shrinkage, total-call, shared-deadline, and depth-four bounds.
4. Keep extraction inside the existing per-model queue ticket and within one
   generation-wide total timeout, including extraction and final answer but
   excluding queue wait. Cap each pass at 8 chunks; overlapping chunks count
   individually toward that cap. Emit progress for completed work through the
   existing generation stream.
5. Fail with `context_exceeded` if the derived prompt still cannot fit, the
   system prompt is oversized, no relevant source span exists, or any fallback
   bound is reached. Do not loop or stream a partial first attempt as though it
   were the final answer. Reactive retry is Ollama-only; preflight is primary.
6. Add `window.derived` metadata to the assistant event: method, version,
   transformed text, source event IDs, character ranges, and a source hash. Add
   no Chroma documents, event kinds, or SQLite table in T1.
7. Add deterministic fake-backend tests and one local `qwen2.5:0.5b` smoke using
   the same fixture; document actual result, limits, and recovery.

Non-goals: general instruction/payload inference; arbitrary file/document
formats; multiple transformation types; cache table; graph or state tracking;
larger-context model routing; multiple fallback models; unbounded or deeper than
four-level reduction; Chroma changes; UI redesign; unrelated refactoring.

Acceptance:

- A fixed document fixture with three planted facts and a final explicit
  `Question:` exceeds a 2048-token prompt budget with no ordinary history; the
  fixture sets `max_reply_tokens=256` and a named `CHUNK_SIZE_FRACTION=0.40`;
  the ordinary `choose_window` path raises `ContextTooLarge`.
- The deterministic fallback result includes the verbatim question and all
  three required facts, fits the budget, and excludes enough filler to fit.
- No model-generated extraction text is accepted unless it matches source text;
  temperature zero alone is not treated as a correctness guarantee.
- Tests prove a non-overflowing request bypasses fallback, reduction depth
  never exceeds four, source event IDs/ranges/hash and derived text are recorded,
  and a failed fallback leaves transcript history intact and a later ordinary
  message usable.
- An ordinary near-limit conversation within the app's prompt budget succeeds
  with Ollama `truncate=false`; tests show bounded requests are not changed.
  Configuration documentation explains that the server no longer silently
  drops old context and that the harness owns truncation/fallback decisions.
- Extraction runs under the existing queue ticket and completes, including the
  final answer, within one `timeouts.total` deadline. No more than 8 chunks are
  processed per pass; overlapped chunks count individually toward the cap, and
  the stream emits progress events as chunks finish.
- A second fixture places a required fact mid-document among distractor lines;
  question-focused extraction retains that fact. A hard-wrapped, unpunctuated
  fixture exercises span offsets. A negative fixture with no relevant source
  span fails visibly instead of inventing one.
- A local Ollama request with `truncate=false` rejects the oversized raw fixture
  with a context error; the integrated fallback then answers the same fact
  question and records its provenance. Report the actual model answer and
  `prompt_eval_count`; do not infer semantic success from HTTP success alone.
- A reported backend context error causes at most one Ollama-only fallback
  attempt. Other backend errors are not mislabeled as overflow.
- `docs/API.md` documents `window.derived` and the extraction progress event.
- Focused tests and the full suite pass; documentation states supported input
  shape, transformation limits, failure behavior, and that no reuse cache exists.

Repair progress:
- [x] Reopen T1 and record the amended scope and approval above.
- [x] Replace sentence extraction with offset-preserving span matching and
  overlap-aware chunks; add the hard-wrapped/unpunctuated fixture.
- [x] Add bounded recursive reduction, total-call cap, depth-four backstop,
  strict shrink checks, and shared-deadline coverage.
- [x] Preserve overflow diagnostics, parse question offsets, bound retrieval,
  fail fast on oversized system prompts, and limit reactive retry to Ollama.
- [x] Update API/concept docs; full suite and local smoke pass; inspect and
  park as `T1 repair:` without merging.
- [ ] Await USER acceptance; do not merge unless separately authorized.

T1 repair follow-up progress:
- [x] Record the accepted review defect and amended scope.
- [x] Size chunks by source offsets and restore oversized merged spans to
  line/sentence units before chunking.
- [x] Add the 1,540-character/20-span regression, multi-chunk reduce scenario,
  and a non-shrinking fail-closed scenario.
- [x] Document that overlap counts toward the eight-chunk per-pass cap and that
  snapping is to line or sentence granularity; rerun full suite and local smoke.
- [x] Park the follow-up as `T1 repair:` without merging.
- [ ] Await USER acceptance; do not merge unless separately authorized.

T1 repair verification (2026-10-04):

- Replaced sentence-set matching with offset-preserving spans, size-based
  chunks with approximately 12% overlap, exact whitespace-normalized substring
  checks, outward line/sentence snapping, and merged ranges. Added an
  unpunctuated hard-wrapped fixture and tests for overlap, exact matching,
  provenance, and the question range from the parse offset.
- Added bounded recursive reduction with strict shrink checks per reduce level,
  maximum depth four, a 16-call extraction/reduction cap, and the same
  generation-wide deadline already shared with the final answer. Added
  fail-closed call-cap coverage.
- Preserved the original `ContextTooLarge` message and appends the supported
  `Question:` shape hint when that shape is unsupported. Oversized system
  prompts fail before retrieval; oversized-message retrieval uses only a
  bounded question query. The reactive retry is now Ollama-only.
- `python -B -m unittest discover -s tests -q` passed 211 tests in 148.665s.
- `python -B tests/ollama_overflow_smoke.py` passed with local
  `qwen2.5:0.5b`: raw request `context_exceeded`; integrated answer was
  `The hidden project marker is VIOLET.`; `prompt_eval_count=315`; derived depth
  1 and all planted fixture facts were present in source-backed prompt spans.
  This is one local fixture/model result, not a general accuracy claim.
- `git diff --check` passed. No event-log schema, cache, Chroma data, or history
  changes were made. The implementation checkpoint is followed by the parking
  documentation commit recorded in the log below. No merge was performed.

T1 repair review follow-up verification (2026-10-04):

- Corrected chunk sizing to use source offsets (`end - start`) rather than
  optional text. Oversized merged spans are expanded back into their enclosed
  source units before chunking.
- Tests prove that 20 empty-text spans totaling 1,540 characters form four
  chunks at a 500-character limit; a separate case proves an oversized merged
  span is restored to its line/sentence units. The full reducer fixture now
  exercises multiple reduction chunks, and a non-shrinking pass fails closed.
- Updated API and concept docs: snapping is at line or sentence granularity;
  each overlapped chunk counts toward the eight-chunk per-pass cap.
- `python -B -m unittest discover -s tests -q` passed 214 tests in 152.203s.
- `python -B tests/ollama_overflow_smoke.py` passed with local
  `qwen2.5:0.5b`: raw request `context_exceeded`; `prompt_eval_count=315`; the
  actual answer included an extra distractor excerpt but also the exact fact
  `The hidden project marker is VIOLET.`; derived depth 1 and all planted facts
  were present in source-backed prompt spans.
- `git diff --check` passed. No merge was performed; await USER acceptance.

Known risks: the 0.5B extractor may miss or miscopy relevant sentences despite
temperature zero; chunk boundaries and character-range mapping need to be
deterministic; Ollama error shapes can change by version. A single fixture proves
the mechanism for that shape, not general document understanding.

Fixture constants: `num_ctx=2048`, `max_reply_tokens=256`,
`CHUNK_SIZE_FRACTION=0.40` (a fraction of `num_ctx` for each source chunk), and
`MAX_EXTRACTION_CHUNKS=8`. These are T1 fixture/prototype constants, not new user
settings. The ordinary near-limit fixture is sized below
`budget_tokens(2048, 256)` and must be accepted unchanged.

Progress:
- [x] Implement and test Ollama truncate control and near-limit regression.
- [x] Implement bounded extraction, shared queue/deadline, and progress stream.
- [x] Implement provenance window record and API behavior.

T1 task 1 evidence (2026-10-04): `OllamaBackend.chat` now sends top-level
`truncate=false`. A request-shape test asserts that field; a near-budget runner
test proves a normal message is sent byte-for-byte unchanged and completes with
truncation disabled. `python -B -m unittest tests.test_models.RequestTests
tests.test_window.RunnerWindowTests.test_near_limit_chat_is_sent_unchanged_with_ollama_truncation_disabled
-q` passed (6 tests). The sandbox denied temporary SQLite creation on the first
run; the same command passed with test-process temporary-file access. The config
guide documents the behavior. No real-model call was needed for this bounded
request behavior check; the integrated local-model scenario remains in T1's
later acceptance work.

T1 task 1 checkpoint: commit `3a3b3cb` (`T1 wip: disable Ollama server truncation`)
was pushed to `origin/t1-bounded-overflow-extraction`.

T1 task 2 verification: focused backend, overflow, queue/deadline, chunk-cap,
depth-cap, recovery, and architecture checks passed (11 tests). The local smoke
script `python -B tests/ollama_overflow_smoke.py` passed on `qwen2.5:0.5b`: the
raw fixture request was classified `context_exceeded`; the integrated fallback
completed with answer `COBALT, VIOLET, and MARIGOLD.`, `prompt_eval_count=256`,
derived depth 1, all three planted facts present, and source event/ranges/hash
recorded. This is one successful run, not a general reliability claim for 0.5B
extraction.

T1 task 3 close-out (2026-10-04): `docs/API.md` documents `window.derived`,
source-range semantics, depth, progress, and the reactive reset event.
Configuration and architecture notes now describe the implemented limits and
visible failure behavior. The final `python -B -m unittest discover -s tests -q`
run passed all 203 tests; `git diff --check` passed. The real local smoke result
is recorded above. No Chroma table, cache, event kind, larger-model route, or
general document-format support was added.

T1 status: parked pending USER acceptance. Keep this branch isolated; do not
merge to `main` until the USER accepts the parked result.

Now: await USER acceptance or a newly approved tranche.

#### Superseded pre-implementation notes (historical)

The notes below document the initial probe and approval sequence; their
implementation-status statements are historical and do not describe the
current T1 state above.

First task completed before proposal: confirm real Ollama overflow behavior.
Evidence (Ollama 0.18.3, `qwen2.5:0.5b`, `num_ctx=2048`): with default
truncation, the oversized fixture returned HTTP 200, `prompt_eval_count=2048`,
and answer `FACT_END`; with `truncate=false`, the same fixture returned HTTP 400,
`the input length exceeds the context length`. The charter records this result.
Review integration (2026-10-04): the charter now protects the user's instruction
or question verbatim while allowing the payload to be transformed. T1 requires
an explicit final `Question:` marker so the prototype does not pretend to infer
arbitrary instruction/payload boundaries. Extraction candidates must be
mechanically matched to source sentences because temperature zero does not
guarantee faithful copying. The source-text hash and ranges remain in the
assistant window record; no cache table is proposed without measured reuse cost.
No code or tests changed. Approval is pending. Do not implement T1 until the
The supported test schema, fallback, provenance, and docs changes are USER-
approved. Exact constants above are in-scope defaults and may be adjusted only
if fixture evidence shows they prevent the declared proof.

## Historical plan: previous _RAG_v1.0 development

Everything from the former `Present`, `Target: _RAG_v1.0`, `Current work`,
`Decisions`, `Backlog`, and `Log` sections below is preserved as a record of the
prior project line. It is useful implementation history, not current authority.

### Historical present

Onboarded 2026-10-04. Repository started at `main`, commit `dc623ae`.
The append-only SQLite event log remains authoritative and rebuilds conversation
history at startup. Short-term context selects the newest messages that fit.
T1 adds optional local conversation retrieval using Ollama embeddings and a
persistent Chroma index. The implementation is on `rag-implementation`;
`main` remains the last accepted state pending the USER's merge decision.
T2 disables Chroma telemetry for the optional cartridge and aligns public
documentation with its dependency, storage, configuration, and reporting route.
`docs/WORKFLOW.md` was supplied by the USER and is included on the branch. The
architecture check disallows third-party imports.

Baseline: Python 3.13.6, `python -B -m unittest discover -s tests` passed
174 tests in 136.531 seconds. No live model or vector service was involved.

### Historical target: _RAG_v1.0

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

### Historical current work

T2: public-release polish (parked).
Approved:
Now:
Progress:
- [x] Disable Chroma telemetry at client creation and test the setting.
- [x] Repair architecture, configuration, security, and README documentation.
- [x] Run focused and full tests, inspect the diff, and park T2.

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

### Historical decisions

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

### Historical backlog

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

### Historical log

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
  `t1-local-rag` was the historical local branch
  at `d3f58b3` and was not the candidate branch. The untracked
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
- 2026-10-04 parked T2, public-release polish. Outcome: Chroma client creation
  explicitly disables anonymized telemetry, and the public architecture,
  configuration, security, and README docs describe the conversation memory
  cartridge consistently. GitHub private vulnerability reporting was disabled;
  `gh api --method PUT repos/jacobmentalconstruct/_HomeAGENT/private-vulnerability-reporting`
  enabled it, and a follow-up GET returned `{"enabled":true}`.
  Evidence: `python -B -m unittest tests.test_memory` passed 11 tests in 0.002
  seconds; `python -B -m unittest discover -s tests` passed 193 tests in
  139.102 seconds. `git diff --check origin/rag-implementation...HEAD` was
  clean, and a documentation search found only the qualified claim that
  ordinary chat uses the standard library. The reviewed diff contains only
  `PLAN.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md`,
  `docs/SECURITY.md`, `src/agent_harness/memory/cartridge.py`, and
  `tests/test_memory.py`. Limitations: the telemetry setting is asserted with
  a fake Chroma module; no real-Chroma smoke was required for T2. Deferrals:
  the three memory watchlist items and the v1 exclusions in Backlog are
  unchanged. Next provisional step: the USER reviews T2 and decides whether
  to merge `rag-implementation` into `main`; no merge was performed.
- 2026-10-04 T2 documentation follow-up: the USER noted that the conversation
  memory prose in `docs/CONFIGURATION.md` still used hard-wrapped lines. Its
  paragraphs were unwrapped to match the rest of that document, without changing
  the rendered content. The stale, local-only `t1-local-rag` branch at `d3f58b3`
  was confirmed merged into `rag-implementation` and deleted. This follow-up
  changes no code or tests; `git diff --check` was clean. The T2 review and merge
  decision remain with the USER.
