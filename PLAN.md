# Project plan

## State in 10 lines

```text
1. Direction: context-scaling prototype complete (v0.2.0, then v0.2.1); product purpose: docs/PROJECT-CHARTER.md.
2. T1 accepted: bounded overflow extraction on RAG-SUM-GRAPH; 214 tests pass; charter stop conditions met.
3. v0.2.1 (T7 audit fixes) is on main via a join commit (b362368); epoch tags mark earlier history (docs/HISTORY.md).
4. Dependency policy approved: dynamic imports; stdlib backup; actionable status; absent+present tests.
5. Retrieval tiers: Chroma → SQLite vectors → FTS5 keyword; all "ready" unless every tier fails.
6. Branches: main is the only branch; each new tranche branches off main and merges back after USER acceptance.
7. docs/BACKLOG.md is the deferred and out-of-scope parking lot.
8. T0–T7 are parked and accepted; new work needs a declared tranche and USER approval first.
9. GitHub holds main and tags v0.2.0, v0.2.1, epoch-1-harness-0.1.0, epoch-2-rag-v1.0; RAG-SUM-GRAPH is deleted.
10. Never record an unrun check as passed; report exact commands and results at every park.
```

## Active direction: close-out to v0.2.0 (2026-10-05)

T1 is accepted; the prototype stop conditions in [`docs/PROJECT-CHARTER.md`](docs/PROJECT-CHARTER.md)
are met. The active direction is a five-tranche close-out (T2–T6) that ends with a tagged v0.2.0
release on `RAG-SUM-GRAPH` and a USER-performed merge to `main`. Former direction, RAG, and T1
history are preserved below as historical reference and are not the active roadmap.

### Current state details

The accepted T1 line was built from T0 commit `fae95c1` and is now fast-forwarded
to `RAG-SUM-GRAPH`. Earlier inspection occurred before Git metadata was attached;
the prior no-Git statements record that initial observation and are now
superseded. Historical RAG branch names, commit IDs, and merge status below
describe the source project. Detailed implementation and repair evidence is
recorded under `## Log`.

Existing harness behavior and the focused context/memory/architecture baseline
were reviewed; the original focused baseline was 38 tests, and the initial T1
full suite passed 203 tests. Current repair verification is in `## Log`.

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

## Definition of Done (close-out checklist)

Binary pass/fail items derived from tranche exit criteria. All must be checked before T6 is
complete. Full T3–T6 scopes, non-goals, and exit criteria are in
[`docs/CLOSEOUT-SCOPE.md`](docs/CLOSEOUT-SCOPE.md).

- [x] **T2** Full suite green with chromadb absent AND present; contract tests cover both stores;
  `sqlite` selection never imports chromadb (asserted); Chroma behavior unchanged; benchmark recorded;
  parked on `t2-store-seam`. (Accepted by USER 2026-10-05)
- [x] **T3** (accepted by USER 2026-10-05) Full suite green both ways; memory default-on for new configs; three-tier state machine
  (ready/degraded/disabled); FTS5 lexical tier maintained and tested; both modes verified:
  `python -B -m unittest tests.test_memory` → 31 OK (chromadb present);
  `AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest tests.test_memory` → 31 OK (absent);
  full suite after repair: 281 tests, 2 skipped, 0 failures in both modes (see T3 repair evidence); live three-condition check recorded; docs updated; parked on `t3-rag-default`.
- [x] **T4** (accepted by USER 2026-10-05) Full suite green; `verify_derived` pure function tested; overflow config switch tested;
  page shows derived block (textContent only); memory bounded re-probe tested; dependency table in
  ARCHITECTURE; parked on `t4-harden`.
- [x] **T5** (accepted by USER 2026-10-05; two thresholds missed and recorded as named limitations) Eight eval fixtures run against five models; results in `docs/`; prompt-composition
  winner chosen by numbers; page has Document + Question fields; exit thresholds met or recorded
  as named limitations; parked on `t5-measure`.
- [x] **T6** (done; the final merge to `main` is the USER's) Version 0.2.0 bumped; short CHANGELOG written; full suite from fresh clone with and
  without chromadb; live smoke matrix recorded; PLAN.md final park with "project complete" and
  deferred list; git tag `v0.2.0`; USER merges `RAG-SUM-GRAPH → main`.

## Guardrails

- One tranche at a time; declare in PLAN.md, wait for USER approval, commit per task as
  `T<n> wip: <task>`, park as `T<n>: <outcome>`.
- Any idea or out-of-scope defect goes to `docs/BACKLOG.md` with one line. Do not fix it.
- To add a task you must remove one or get USER approval. If a tranche outgrows its scope, stop
  and ask; do not widen it.
- New behavior needs a failing test or fixture first.
- After T5 parks, only release tasks and confirmed release-blockers are allowed. A
  release-blocker is a failing test, data loss, wrong provenance, a false privacy/security
  claim, or a crash.
- Never record an unrun check as passed. Report exact commands and results at every park.

## Approved policies (USER, 2026-10-05)

### Dependency policy

Third-party dependencies are welcome when each has: (1) a runtime dynamic import, never a
static one; (2) a stdlib or alternative backup path; (3) an actionable status reason and fix
text; (4) tests with the dependency both absent and present. The core chat path has no hard
third-party import. Conversation memory is ON by default for new configs, uses Chroma when
available, and degrades through backups, never to a dead feature unless every tier fails.

This policy replaces the charter line "optional-dependency behavior remains in force" and will
be added to `docs/PROJECT-CHARTER.md` and `docs/ARCHITECTURE.md` as part of T2 implementation.

### Charter invariant change

The charter invariant "The local privacy boundary and optional-dependency behavior remain in
force unless a specific future tranche changes them" will be updated to reference the dependency
policy above. Applied in T2.

## Parked: T7 Pre-merge audit fixes

Status: **parked as `T7:` and tagged `v0.2.1`; verified independently by the USER (371 tests, both modes, fuzz and
battery clean). Stopped. The epoch tags and the join onto `main` are the USER's.**
Approved as declared (2026-10-05), with three refinements.
USER-approved addition (2026-10-05): create `docs/HISTORY.md` (three epochs, E-numbering), link it from the README,
and test that every tag it names is listed (`HistoryDocTests` in `tests/test_t7_audit_fixes.py`). The epoch tags and
the join onto `main` happen after `v0.2.1` is pushed, on the USER's go. Correction to the draft: `dfcc9f1` is not an
exact snapshot of epoch 2 (seven files differ from `62be955`); HISTORY.md says so.
Refinements recorded: (1) the control-character status test first forces the vector tier down so the keyword tier is
serving; (2) the version test asserts `__version__` equals the newest CHANGELOG heading; (3) the atomic-write failure
tests also assert no temporary file is left behind. The USER independently confirmed the eval fixtures have no closing
quote or bracket after sentence ends (no eval re-run); the boundary comparison is still recorded in the parking entry.
Branch: `t7-audit-fixes` (off `RAG-SUM-GRAPH` at `fd7c60c`, the `v0.2.0` tag). Park as `T7:`; tag `v0.2.1`;
`v0.2.0` is not moved. The USER merges to `main`.

Scope (from the release audit; no other scope):
1. `overflow.sentences()`: the `SENTENCE` separator regex consumes closing quotes and brackets, so
   `He said "stop." Then left.` yields units `He said "stop.` and `Then left.` and the closing `"` (index 14) belongs to
   no unit (reproduced 2026-10-05). Split after the closing-quote run so every non-whitespace character belongs to
   exactly one unit.
2. `lexical_store._sanitize()`: strip control characters. Reproduced: `"\x00"` and `"a\x00b"` make FTS5 raise
   `OperationalError: unterminated string`, which sets a keyword-tier fault.
3. `config.load_config()`: write the config atomically, like `update_file` (temporary file, then `os.replace`).
4. Docs, README and ARCHITECTURE: after a fallback reply, follow-up questions do not see the document or anything older
   than it (the oversized turn ends the window run); retrieval may help; memory indexes whole turns, so a long turn is
   embedded from its first part only and cannot be injected when it does not fit. Document the `store_reason` status
   field in API.md and CONFIGURATION.md.
5. Add to `docs/BACKLOG.md`, one line each, not implemented: chunked indexing of long turns; reuse of derived context for
   follow-ups; a verify command or page mark for `verify_derived`; refactor `make_server` (complexity 53) and
   `derive_context` (complexity 40); log lines for swallowed memory exceptions.
6. Version 0.2.1, CHANGELOG entry, full suite in both modes, a fresh-clone run, tag `v0.2.1`, push `RAG-SUM-GRAPH` and
   the tag. Stop.

Non-goals: anything not listed; no re-run of the T5 eval (its fixtures contain no closing quotes or brackets after
sentence ends; the implementation will confirm their unit boundaries are unchanged and record it, and if any changed
it will stop and ask).

Acceptance bullet -> named test or artifact (tests in `tests/test_t7_audit_fixes.py`, written failing first):
- 1 sentence coverage: `SentenceCoverageTests.test_closing_quote_after_a_sentence_stays_with_its_sentence` (the repro,
  plus `)` and `'` variants), `.test_every_non_whitespace_character_belongs_to_exactly_one_unit` (seeded random text
  property test: sentences, quotes, brackets, newlines, long unpunctuated runs); evidence: eval fixture units
  unchanged.
- 2 control characters: `LexicalSanitizeTests.test_control_characters_are_stripped_from_queries` (`"\x00"`,
  `"a\x00b"`, and every other C0 control and DEL), `.test_a_query_with_control_characters_does_not_flip_the_memory_status`
  (state stays `ready`, no keyword-tier fault, `failed_retrievals` 0).
- 3 atomic config write: `AtomicConfigWriteTests.test_a_failed_write_leaves_the_old_config_intact` (simulated failure
  in the write and in `os.replace`), `.test_a_successful_write_leaves_no_temporary_file`.
- 4 docs: `T7DocsTests.test_readme_and_architecture_describe_follow_ups_after_a_fallback_reply`,
  `.test_store_reason_is_documented_in_api_and_configuration`; behavior behind the claim:
  `FollowUpWindowTests.test_a_follow_up_after_a_fallback_reply_sends_neither_the_document_nor_older_turns`.
- 5 backlog: `T7DocsTests.test_backlog_lists_the_five_audit_items`.
- 6 release: `ReleaseTests.test_version_is_0_2_1`, `.test_changelog_has_a_0_2_1_entry`; the T6 test
  `tests/test_t6_release.py::ReleaseTests.test_version_is_0_2_0` is changed to read the version from the latest
  CHANGELOG heading rather than a fixed string. Artifacts: both suite modes, a fresh-clone run (commands and results
  recorded here), the `v0.2.1` tag and push output in the final report.

Progress:
- [x] Declare T7; map every bullet
- [x] USER approval (with the three refinements above)
- [x] Failing tests written and shown red (commit `675e037`: 17 problems in 12 tests; the follow-up window test and the
  clean-write test passed at once because they describe existing behavior)
- [x] Items 1-5 (commit `c90dfe7`), plus the approved `docs/HISTORY.md` addition (commit `48e127b`)
- [x] Version, CHANGELOG, both suite modes, fresh clone
- [x] Park as `T7:`; push `t7-audit-fixes`; fast-forward and push `RAG-SUM-GRAPH`; tag and push `v0.2.1`; stop

Evidence (2026-10-05):
- Repro before the fix: `He said "stop." Then left.` gave units `He said "stop.` (0-14) and `Then left.` (16-26); the
  `"` at 14 was in no unit. A NUL in a keyword query raised `OperationalError: unterminated string`.
- Fix 1: `SENTENCE` is now `[.!?]["'”’)]*(\s+)` and the split uses group 1, so closing quotes and brackets stay with
  their sentence. The property test covers 3,000 seeded random documents (quotes, brackets, newlines, tabs, hard-split
  runs of 400-1,700 characters): every non-whitespace character is in exactly one unit.
- Boundary comparison (recorded before and after the fix): the 8 eval fixtures and the 4 T1 fixtures, 12 documents and
  1,802 units, have identical unit boundaries. The USER independently confirmed the eval fixtures have no closing quote
  or bracket after a sentence end, so the eval was not re-run.
- Fix 2: `_sanitize` drops `"`, every C0 control character and DEL. With the vector tier forced down, queries with NUL
  and other controls leave the status `ready` / `lexical` with no keyword-tier fault and `failed_retrievals` 0.
- Fix 3: `_write_atomic` (temporary file, `os.replace`, temporary file removed on any failure) is used by both
  `load_config` and `update_file`. A partial write and a failing `os.replace` both leave the old file byte-for-byte
  and no temporary file.
- Suites on `c90dfe7` (items 1-6, before the HISTORY addition): working tree with chromadb 369 OK (2 skipped),
  `AGENT_HARNESS_BLOCK_MODULES=chromadb` 369 OK (2 skipped); fresh clone with chromadb 369 OK (2 skipped), fresh clone
  in a new venv without chromadb 369 OK (4 skipped).
- Suites on `48e127b` (with HISTORY.md and its two tests): my working-tree run with chromadb 371 OK (2 skipped); my
  remaining runs were cut off (the blocked run's output is empty, and the fresh-clone runs did not start), so I do not
  claim them. The USER verified 371 tests in both modes independently.
- `docs/HISTORY.md`: from the USER's draft, with one correction (`dfcc9f1` is not an exact snapshot of epoch 2; seven
  files differ from `62be955`). `HistoryDocTests` checks it names exactly `epoch-1-harness-0.1.0`, `epoch-2-rag-v1.0`,
  `v0.2.0` and `v0.2.1`, that README links it, and that any of those tags that exists points at the commit it names.
- Not done by the builder, by instruction: the epoch tags, the join onto `main`, any change to `main`.

## Parked: T6 Release

Status: **complete; tagged `v0.2.0`.**
Branch: `t6-release` (off `RAG-SUM-GRAPH` at the T5 head `b6a32dd`, which was pushed to `origin/RAG-SUM-GRAPH`
at the start of T6: `71ebc12..b6a32dd`, a fast-forward through T3, T4 and T5).
USER instruction recorded: push `RAG-SUM-GRAPH` after each accepted tranche.

Scope: `docs/CLOSEOUT-SCOPE.md` T6 items 1-8, plus these USER additions (2026-10-05):
- A. README and ARCHITECTURE say plainly that small models can answer wrongly without any warning when extraction finds
  some passages but not the answer, cite the four silent-wrong cells in `docs/EVAL-RESULTS.md`, recommend 4B or larger,
  and link the eval results.
- B. Document the effective size ceilings: the 20,000-character message cap against the prompt budget at `num_ctx` 2048,
  4096, 8192 and 16384, and the chunk-cap limit.
- C. State that the `small_ends` default was chosen by the pre-declared rule on a near-tie.
- D. The live smoke matrix includes a real message sent through the Document + Question fields in the browser, the three
  memory conditions, `--backlog 800`, the overflow smoke and the eval summary.
- E. CHANGELOG, version 0.2.0, full suite from a fresh clone with and without chromadb, tag `v0.2.0`, delete merged
  branches, PLAN.md "project complete" with the deferred list.

Non-goals: new features; anything not listed. Code changes are limited to the version string and a "silent wrong
answers" section in the generated eval report (so the four cells are listed where they are cited).

Acceptance bullet -> named test or recorded artifact (tests in `tests/test_t6_release.py`):
- 1 final doc pass, derived text in the event log in plaintext, no graph: `ReleaseDocsTests.
  test_security_says_derived_text_is_stored_in_plaintext_in_the_event_log`, `.test_architecture_says_no_graph_is_built`;
  the doc pass findings are recorded in the parking entry.
- 2 version 0.2.0 and CHANGELOG: `ReleaseTests.test_version_is_0_2_0`, `.test_changelog_has_a_0_2_0_entry`
- 3 fresh clone, with and without chromadb: recorded artifact (commands and results in `docs/SMOKE-MATRIX.md` and below)
- 4 live smoke matrix: recorded artifact `docs/SMOKE-MATRIX.md`; `ReleaseDocsTests.test_smoke_matrix_lists_every_required_run`
- 5 PLAN.md final park: `ReleaseDocsTests.test_plan_says_project_complete_and_lists_the_deferred_items`
- 6 delete merged branches; 7 tag `v0.2.0`: recorded (commands and output in the final report; done after the last commit)
- A silent wrong answers: `ReleaseDocsTests.test_readme_and_architecture_warn_about_silent_wrong_answers`,
  `EvalReportTests.test_the_report_lists_silent_wrong_answers`, `.test_the_committed_report_lists_the_four_cells`
- B size ceilings: `ReleaseDocsTests.test_size_ceilings_match_the_code`, `.test_the_chunk_cap_ceiling_is_documented`
- C near-tie: `ReleaseDocsTests.test_docs_say_small_ends_was_chosen_by_the_rule_on_a_near_tie`
- D smoke matrix contents: `ReleaseDocsTests.test_smoke_matrix_lists_every_required_run`
- E covered by 2, 3, 5, 6, 7.

Progress:
- [x] Push RAG-SUM-GRAPH at the T5 head; branch; declare T6; map bullets
- [x] Failing tests written and shown red (commit `0019952`: 15 problems in 12 tests before implementation)
- [x] Version, CHANGELOG, report section, doc pass (A, B, C) (commit `906b644`)
- [x] Live smoke matrix (D) recorded in `docs/SMOKE-MATRIX.md`
- [x] Fresh clone suite, with and without chromadb
- [x] PLAN.md "project complete"; fast-forward and push RAG-SUM-GRAPH; tag and push `v0.2.0`; delete merged branches; stop

Evidence and findings (2026-10-05):
- Fresh clone (`git clone --branch t6-release` of `9981e0c` into a temporary directory): with chromadb (system Python,
  chromadb 1.3.5) `python -B -m unittest discover -s tests`: 357 tests, OK, 2 skipped, 172.2 s; without chromadb (a new
  venv with nothing installed) `<venv>\Scripts\python -B -m unittest discover -s tests`: 357 tests, OK, 4 skipped,
  170.8 s. An earlier clone of `906b644` failed only the two tests for artifacts not yet committed (smoke matrix, final
  plan), as expected; they were committed and the clone was repeated.
- Live smoke matrix: `docs/SMOKE-MATRIX.md`. Highlights: all three memory conditions (and the combination) behave as
  documented; `--backlog 800` retrieve 0.226 s during a 7.35 s catch-up; a real 10,871-character Document + Question
  message sent through the page in the browser to `qwen3.5:4b` was answered correctly with a `small_ends` derived
  record that `verify_derived` accepts; the overflow smoke passes with `qwen3.5:4b` and gives a silent wrong answer
  ("COBALT.") with `qwen2.5:0.5b`, which answered correctly in the T1 run under the old 10% ends. That is consistent
  with the eval and the "4B or larger" advice; it is recorded, not acted on.
- Doc pass findings fixed: README claimed the suite "runs in two modes automatically" (it does not; the second mode
  is the environment variable); ARCHITECTURE lacked `overflow.py` and `provenance.py` in the module table and still
  called memory "optional ... uses Chroma"; CONFIGURATION and API still said "T1"; SECURITY did not say derived text is
  stored in the event log. New: size limits table (computed from the code and checked by a test), silent-wrong warning
  in README and ARCHITECTURE, near-tie statement, CHANGELOG, a "Silent wrong answers" section in the generated eval
  report (regenerated from unchanged data: cells, scores and winner identical).
- Size finding worth knowing: at `num_ctx` 8,192 with a 256-token reply, and at 16,384, every message the server
  accepts (20,000 characters) already fits the estimated budget, so the fallback is reachable from the page only via
  Ollama's reactive retry. At the defaults (8,192 and 2,048) only about the last 1,400 characters below the cap reach it.
- Housekeeping: removed `unused/lexical.sqlite3` from the working tree (ignored by git; created by my own T3-repair
  test run before those tests moved to temporary directories). Logged one cosmetic item in BACKLOG (the conversation
  title for a Document + Question message).
- Release steps after the last commit: fast-forward `RAG-SUM-GRAPH` to the T6 head and push; tag `v0.2.0` there and
  push the tag; delete the merged tranche branches `t1-bounded-overflow-extraction`, `t2-store-seam`, `t3-rag-default`,
  `t4-harden`, `t5-measure` and `t6-release`, locally and on `origin`, after checking each is contained in
  `RAG-SUM-GRAPH`. `origin/rag-implementation` is not a tranche branch and is left alone. The commands and output are
  in the final report to the USER.

## Project complete (v0.2.0, 2026-10-05)

The context-scaling prototype described in `docs/PROJECT-CHARTER.md` is complete. T0 through T6 are parked and
accepted (T6 by these instructions; the final merge is the USER's): bounded overflow extraction with source-linked,
verifiable provenance; the memory store seam with SQLite and FTS5 tiers, on by default; hardening; measurement on five
local models; and this release. `RAG-SUM-GRAPH` carries every tranche and is tagged `v0.2.0`. The USER merges it into
`main`.

Named limitations carried forward: two T5 exit thresholds missed (answer passage found in 100% of fixtures for models
of 1.5B and up; 7/8 for 0.5B); small models can answer wrongly without any warning; the fallback is not reachable from
the page at large `num_ctx`; llama.cpp tested only against a scripted fake.

Deferred list (do not build without new evidence and a new, approved tranche):
- History-overflow condensing (summarizing old turns in place).
- Reuse cache table for extracted overflow spans.
- Graph construction and rehydration.
- Larger-model routing for the overflow fallback (for example: extract with a small model, answer with a larger one).
- Relevance-cutoff tuning or query-composition changes (T5 numbers did not show them hurting).
- Hybrid ranking (vector + lexical).
- Cross-conversation retrieval.
- New input formats for the overflow fallback, beyond the `Question:` shape.
- Automatic strategy learning; arbitrary plugin registries; multi-model fallback for overflow; cloud services or sync.
- Everything else in `docs/BACKLOG.md`, including: a real llama.cpp server smoke; WAL on the event store (only if a lock
  error is reproduced); a "dropped" stream marker for slow clients; bounding the estimator samples; the startup
  embedding-model check and per-reply reconcile threads; the Document + Question conversation title.

## Parked: T5 Measure and Compose

Status: **accepted by USER (2026-10-05).**
Branch: `t5-measure` (off the T4 head `b6d0a94`). Scope source: `docs/CLOSEOUT-SCOPE.md` T5 items 1-4.
Note: `origin/RAG-SUM-GRAPH` was still at the T2 head `71ebc12`; local `RAG-SUM-GRAPH` was fast-forwarded to
`t4-harden` (not pushed) so T5 branches off T4.

USER-approved amendment (2026-10-05), recorded: in the T5 fixture list, the "duplicated sentence" fixture is
replaced by **"document containing earlier `Question:` lines"**. CLOSEOUT-SCOPE item 1 is edited to match.

Non-goals: relevance-cutoff or query-composition changes unless the T5 numbers show them hurting, hybrid
ranking, cross-conversation retrieval, any backend parsing change, any new variant beyond three.

Exit thresholds (fixed before the first run, copied as written from CLOSEOUT-SCOPE):
- The answer sentence is in the derived text in 100% of fixtures for models >= 1.5B and >= 7/8 for 0.5B.
- Final-answer correctness >= 80% for models >= 4B (report, do not gate, for smaller).
- The absent-fact fixture fails visibly every time.
- Timings reported, not gated.
If a threshold is missed after the allowed variants, record it as a known limitation and stop. The tranche ends
either way.

Interpretation fixed before the first run (recorded so the numbers cannot move it):
- Models: `qwen2.5:0.5b`, `qwen2.5:1.5b`, `qwen3.5:2b`, `qwen3.5:4b`, `qwen3.5:9b`. "Models >= 1.5B" is 1.5b, 2b,
  4b and 9b; "models >= 4B" is 4b and 9b; "0.5B" is qwen2.5:0.5b.
- Denominator is all 8 fixtures. The absent-fact fixture has no answer sentence, so for the extraction check it
  counts as a pass when the reply fails visibly (nothing was wrongly extracted) and as a miss otherwise.
- "Answer sentence in the derived text" means every fixture fact string is found in the derived text after
  collapsing whitespace runs. "Correct" means the final answer contains every expected key, case-insensitively;
  for the absent-fact fixture, correct means it failed visibly (`context_exceeded`) and produced no answer.
- Correctness >= 80% of 8 means at least 7 of 8 (6.4 rounds up).
- "Fails visibly" means the reply state is `failed` with reason `context_exceeded` and no final answer.
- One run per cell at temperature 0 (Ollama is near-deterministic at 0, not guaranteed); `num_ctx` 2048, reply
  limit 256, the same system prompt as `tests/ollama_overflow_smoke.py`. Each cell uses a fresh runner and event
  store in a temporary directory, so token-estimator learning never carries over.

Composition variants (at most three, no others): `baseline` (head/tail share 10% of the prompt budget; order head,
derived block, tail, question); `small_ends` (share 5%; same order); `block_by_question` (share 10%; order head,
tail, derived block, question). Selected through `derive_context(..., composition=...)` and
`GenerationRunner(overflow_composition=...)`; not a config key.
Winner rule (fixed now; applied by `choose_winner`): over all 5 models x 8 fixtures per variant, pick the variant
with (1) the most exit-threshold checks met (four checks: extraction >= 1.5B, extraction 0.5B, correctness
>= 4B, absent fact), then (2) the most correct final answers, then (3) the most extraction passes, then (4) the
fewest total model calls, then (5) `baseline`. The winner becomes `DEFAULT_COMPOSITION`.
Additive record change needed to keep `verify_derived` valid for every variant: the derived record gains
`composition` and each source gains `role` (head, middle, tail, question). Records without them still verify as
`baseline`.

Acceptance bullet -> named test or recorded artifact (tests in `tests/test_t5_measure.py`):
- 1 fixture set (8, amended list): `EvalFixtureTests.test_there_are_eight_fixtures_with_the_declared_kinds`,
  `.test_the_duplicated_sentence_fixture_is_replaced_by_earlier_question_lines`,
  `.test_every_fixture_overflows_the_budget_and_ends_with_its_question`,
  `.test_every_answer_sentence_is_in_its_document_and_the_absent_fixture_has_none`,
  `.test_the_earlier_question_lines_fixture_parses_to_the_final_question`,
  `.test_the_boundary_fixture_puts_its_fact_first_after_the_protected_head`,
  `.test_the_long_question_fixture_has_a_long_question`, `.test_every_fixture_fits_the_extraction_chunk_cap`
- 2 runner records extraction, answer, correctness, calls, time; five models; results under `docs/`:
  `EvalRunnerTests.test_the_declared_models_and_variants`, `.test_a_cell_records_extraction_answer_correctness_calls_and_time`,
  `.test_an_absent_fact_cell_records_a_visible_failure`, `.test_results_are_saved_after_each_cell_and_resumed`,
  `.test_the_report_lists_every_cell_and_the_thresholds`; recorded artifacts `docs/eval-results.json` and
  `docs/EVAL-RESULTS.md`; `RecordedArtifactTests.test_the_results_cover_every_model_variant_and_fixture`
- 3 at most three variants, winner by the numbers: `CompositionTests.test_there_are_exactly_three_named_compositions`,
  `.test_baseline_output_is_unchanged`, `.test_small_ends_keeps_less_of_the_head_and_tail`,
  `.test_block_by_question_puts_the_derived_block_just_before_the_question`,
  `.test_every_composition_verifies_with_verify_derived`, `EvalRunnerTests.test_the_winner_rule_follows_the_declared_order`,
  `CompositionTests.test_the_default_composition_is_the_recorded_winner`
- 4 page Document + Question fields, composed in the browser, no backend parsing change:
  `DocumentQuestionPageTests.test_compose_joins_document_and_question_in_the_backend_shape`,
  `.test_the_composed_message_parses_with_the_backend_parser`, `.test_an_over_limit_message_is_refused_in_the_browser`,
  `.test_the_page_has_document_and_question_fields_and_uses_textcontent`, `.test_parse_question_is_unchanged`
- Exit thresholds: `ThresholdTests.test_extraction_threshold_by_model_size`,
  `.test_correctness_threshold_gates_only_models_4b_and_up`, `.test_absent_fact_must_fail_visibly_every_time`,
  `.test_timings_are_reported_not_gated`, `RecordedArtifactTests.test_threshold_constants_are_the_declared_ones`;
  the outcome per threshold (met, or a named limitation) is the recorded artifact `docs/EVAL-RESULTS.md` and
  the parking entry.

Progress:
- [x] Declare T5; record the amendment, thresholds, interpretation and winner rule before any run (commit `533ef38`)
- [x] Failing tests written and shown red (commit `b26b66b`; import errors before implementation)
- [x] Composition variants and `verify_derived` roles
- [x] Fixtures, runner, threshold and winner functions
- [x] Page Document + Question UI
- [x] Live eval run (5 models x 3 variants x 8 fixtures = 120 cells) and results in `docs/`
- [x] Winner set as default; thresholds met or named limitations recorded
- [x] Both suite modes green; park as `T5:`; push `t5-measure`

Evidence (2026-10-05, this machine, real local Ollama; run at commit `7e42dd9` plus the doc and test edits listed below):
- `python -B -m tests.eval.runner` (all defaults): 120 cells, 387 s of summed cell time. Artifacts: `docs/eval-results.json`
  (raw, per cell) and `docs/EVAL-RESULTS.md` (generated report with threshold tables and cell grids).
- Winner by the rule fixed before the run: `small_ends`. Scores (thresholds met of 4 / correct answers / extraction
  passes / model calls): baseline 2 / 32 / 33 / 213; small_ends 2 / 33 / 34 / 232; block_by_question 2 / 33 / 33 / 213.
  Every variant met the same two thresholds, so the decision came down to rules 2 and 3: small_ends beat baseline by one
  correct answer and one extraction pass out of 120 cells. That is a thin margin from a single run per cell; the
  winner is the declared rule's output, not a strong finding. `DEFAULT_COMPOSITION = "small_ends"`.
- Exit thresholds for the winning variant (small_ends):
  - Extraction, models >= 1.5B, 100%: MISSED. qwen2.5:1.5b 7/8, qwen3.5:2b 7/8, qwen3.5:4b 8/8, qwen3.5:9b 8/8.
  - Extraction, 0.5B, >= 7/8: MISSED. qwen2.5:0.5b 4/8 (3/8 under baseline and block_by_question).
  - Correctness >= 80%, models >= 4B: MET. qwen3.5:4b 8/8, qwen3.5:9b 8/8. Reported only: 0.5b 4/8, 1.5b 7/8, 2b 6/8.
  - Absent fact fails visibly every time: MET, all five models in every variant.
  - Timings reported, not gated: small_ends totals over 8 fixtures: 0.5b 11.7 s / 44 calls, 1.5b 9.8 s / 44, 2b 54.9 s / 54,
    4b 22.2 s / 45, 9b 27.0 s / 45.
- Named known limitations (the rule says record them and stop; no further variants were tried): (1) the answer
  sentence does not reach the derived text in 8/8 fixtures for qwen2.5:1.5b (head_tail_boundary, nothing matched, failed
  visibly) and qwen3.5:2b (unpunctuated_text, 16 model calls); (2) qwen2.5:0.5b reaches it in 4/8. They are written up in
  ARCHITECTURE "Known limits" and the README. No threshold, fixture or rule was changed after seeing results.
- Notes on individual cells, for the reviewer: qwen3.5:2b wrapped_text answered "04:30 sharp" (extraction passed; counted
  incorrect because the declared key is "third Thursday"); one qwen2.5:0.5b small_ends cell ended with a backend
  `incomplete` stream error (head_tail_boundary) and is recorded as it happened; the 0.5B model's absent-fact "pass" is a
  visible failure like the others.
- Pilot before the real run (not in the results): one cell each of qwen2.5:0.5b and qwen3.5:2b on middle_fact/baseline into a
  temp file, only to confirm the pipeline ran. No fixture, threshold or rule was changed afterwards.
- `python -B -m unittest discover -s tests` (Chroma present): 345 tests, OK, 2 skipped, 172.6 s.
  `AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest discover -s tests`: 345 tests, OK, 2 skipped, 172.4 s.
- Page, in the in-app browser against a throwaway server with a temp runtime (not your data): the Document button opens a
  Document box above the message box; Send with a document and no question shows "Add a question below the document." and
  keeps the text; `prepareMessage` composes `Doc line.\nQuestion: What?` and refuses 20,013 characters with the 20,000 limit;
  the 375 px mobile layout works. The T3 "memory is disabled in config" note was also seen there. The placeholder was
  shortened ("Your question") after that viewing and not re-viewed. No message was sent through the page to a model.
- Backend parsing unchanged: `parse_question` is pinned by `DocumentQuestionPageTests.test_parse_question_is_unchanged`; the
  page composes the message in the browser.
- Changes beyond the four listed items: the derived record gained `composition` and per-source `role` (needed so
  `verify_derived` stays valid for every variant; old records still verify as baseline), `keep_ends` takes an optional
  `share`, and `GenerationRunner` takes `overflow_composition`. `tests/overflow_fixtures.script_for` follows the default
  composition. CLOSEOUT-SCOPE item 1 was edited for the approved fixture amendment.
- Not run: repeat runs per cell (so no variance estimate), models above 9B or below 0.5B, llama.cpp, a real reply through the
  new page fields.

## Parked: T4 Harden (no new features)

Status: **accepted by USER (2026-10-05).**
Branch: `t4-harden` (off the T3 head `a9aeb65`). Scope source: `docs/CLOSEOUT-SCOPE.md` T4 items 1-9, plus
one small USER-added item (10).
Note: `origin/RAG-SUM-GRAPH` was still at the T2 head `71ebc12` when T4 began; local `RAG-SUM-GRAPH` was
fast-forwarded to `t3-rag-default` (not pushed) so T4 branches off T3.

Non-goals: new features, new retrieval strategies, anything not listed. Guardrail: failing test first.

Design decisions (T4-specific):
- `verify_derived(original_event_text, derived_record) -> list[str]` lives in `conversation/provenance.py`
  (overflow.py is at 373 of the 400-line limit). It returns problem codes; an empty list means verified.
- Overflow switch: top-level config key `overflow_fallback` (bool, default true). Off: the oversized message
  fails with today's visible `context_exceeded` message carrying the original numbers, and the reactive
  backend context error is not retried.
- Re-probe limits (named constants in `memory/cartridge.py`): first probe 5 s after a transient failure,
  doubling each failed probe, capped at 300 s; at most one probe in flight; one embedding call per probe;
  probes run on a background thread, so after the first failure a reply never waits on a failing embedder. While backing off the
  vector tier is skipped and the keyword tier serves. A successful probe clears the fault and reconciles.
- Absent-dependency pattern: `tests/support.blocked_modules(*names)` (in-process context manager that hides
  modules and restores them), reused by one test per dependency.

Acceptance bullet -> named test (all in `tests/test_t4_harden.py` unless noted):
- 1 derived context never outlives the reply's window record across a store reopen:
  `DerivedLifetimeTests.test_derived_context_does_not_outlive_its_reply_across_a_store_reopen`
- 2 `verify_derived`: `VerifyDerivedTests.test_a_hand_built_record_verifies`,
  `.test_a_real_derived_record_from_the_overflow_path_verifies`, `.test_wrong_hash_is_reported`,
  `.test_wrong_range_is_reported`, `.test_tampered_text_is_reported`, `.test_a_missing_or_unknown_record_is_reported`
- 3 overflow switch: `OverflowSwitchTests.test_default_is_on_and_is_written_to_a_new_config`,
  `.test_a_non_boolean_is_refused`, `.test_off_gives_todays_context_exceeded_with_the_original_numbers`,
  `.test_off_does_not_retry_a_backend_context_error`, `.test_build_app_passes_the_switch_to_the_runner`
- 4 page derived block: `PageDerivedTests.test_page_shows_a_collapsed_derived_block_with_source_ranges_using_textcontent`,
  `.test_the_page_script_parses` (needs node; skipped without it)
- 5 README fallback usage and limits: `DocsTests.test_readme_explains_the_question_shape_limits_and_failure_behavior`
- 6 memory bounded re-probe with backoff: `ReprobeTests.test_backoff_schedule_doubles_and_is_capped`,
  `.test_no_vector_attempts_while_backing_off`, `.test_a_due_probe_runs_in_the_background_and_recovers`,
  `.test_at_most_one_probe_runs_and_a_failed_probe_extends_the_backoff`,
  `.test_status_reports_when_the_next_probe_is_due`, `.test_a_reply_does_not_wait_for_a_hung_embedder_while_backing_off`,
  `.test_a_successful_probe_does_not_reset_the_backoff_while_the_store_keeps_failing` (added by the item-9 audit)
- 7 known limits documented: `DocsTests.test_known_limits_are_documented`
- 8 dependency table and absent-dependency pattern: `DocsTests.test_dependency_policy_table_lists_every_dependency_and_its_backup`,
  `AbsentDependencyTests.test_blocked_modules_hides_and_restores`, `.test_chroma_absent_falls_back_to_sqlite_vectors`,
  `.test_embeddings_absent_falls_back_to_keyword_search`, `.test_ollama_unreachable_llamacpp_backend_still_chats`,
  `.test_nvidia_smi_absent_shows_nothing`, `.test_tkinter_absent_cli_and_server_paths_still_work`
- 9 audit of files this tranche touched: no test; the findings and fixes are recorded in the parking entry
  and unfixed items in `docs/BACKLOG.md`.
- 10 (USER-added) `--backlog` probe query and seed share "home number" so `served_by` shows the tier:
  `ProbeScriptTests.test_backlog_query_and_seed_share_the_words_home_number`

Progress:
- [x] Declare T4; map every bullet to a named test
- [x] Failing tests written and shown red (commit `36ca63c`; import errors before implementation)
- [x] Items 1-3 (provenance, switch)
- [x] Item 4 (page) and items 5-7 (docs)
- [x] Item 6 (re-probe)
- [x] Item 8 (dependency table, absent pattern)
- [x] Item 9 (audit) and item 10 (probe)
- [x] Both suite modes green; park as `T4:`; push `t4-harden`

Evidence (2026-10-05, this machine):
- `python -B -m unittest discover -s tests` (Chroma present): 314 tests, OK, 2 skipped, 166.8 s.
- `AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest discover -s tests` (Chroma blocked): 314 tests, OK, 2 skipped, 167.2 s.
- Already-passing-at-first-run tests (hardening tests of existing behavior, not new behavior): bullet 1
  `DerivedLifetimeTests`, and the page and verify tests that exercise existing records. Everything that adds
  behavior (verify_derived, switch, derived block, re-probe, blocked_modules, gui message, probe constants,
  docs) was red first.
- `verify_derived` was also run against real overflow records produced by the fake-backend fixtures
  (middle-document and three-fact documents): both verify with no problems.
- Page derived block: exercised with `node` and a minimal fake DOM (collapsed `details`, text set as text,
  ranges listed, no block without a derived record) and `node --check` on the script. Not viewed in a real
  browser.
- Live, real Ollama (`nomic-embed-text:latest`): `python -B -m tests.live_memory_probe --backlog 400`:
  `retrieve()` 0.003 s, `served_by: ["lexical"]` with 0 of 400 vectors indexed at 0.5 s, 5.31 s catch-up,
  afterwards tier `vector`, methods `["vector"]`. The shared "home number" query/seed now makes the
  keyword tier answer, so `served_by` shows the tier (item 10).
  `python -B -m tests.live_memory_probe --model no-such-embed-model`: ready, tier lexical, reason
  `embedding_model_missing`, served by lexical (the first retrieve starts the background probe).
- Not run: no real-browser view of the derived block; no real llama.cpp server; the re-probe was tested with a
  fake clock and fake embedders, not by stopping and restarting a real Ollama.

Audit (item 9: files this tranche touched: cartridge.py, generation.py, config.py, app.py, cli.py, page.html,
provenance.py, overflow.py, support.py, live_memory_probe.py):
- Fixed, confirmed by a failing test first: a successful probe reset the backoff, so a vector store that kept
  failing while the embedder worked would have been re-probed every 5 s. The backoff now resets only on a real
  indexed batch or query.
- Fixed: the page's derived block would throw on a record without `char_range`; it now shows "range unknown".
- Logged in `docs/BACKLOG.md`, not fixed: synchronous embedding-model check at `serve` startup; one background
  reconcile thread per reply queuing on the lock during a long catch-up; the probe uses one throwaway text.
- Changed beyond the listed items, small and inside the dependency-policy rule (an actionable message): the `gui`
  command prints how to run `serve` when tkinter is missing, instead of a traceback.

## Parked: T3 repair (review round 1; accepted by USER 2026-10-05)

Status: **repair complete, parked as `T3 repair:`; awaiting USER acceptance. T4 not started.**
Branch: `t3-rag-default`. Parking commit message prefix: `T3 repair:`.

Approved reopen of T2 (carry-over, item 6 only): `SqliteStore.open()` creates
`idx_vectors_conversation` on `vectors(conversation_id)`; existing databases pick it up on reopen.

Design decisions taken in this repair (all follow from the review items):
- FTS5 is its own component, `memory/lexical_store.py`, in `runtime/memory/lexical.sqlite3`
  (replaces the FTS table in `vectors.sqlite3` named in CLOSEOUT-SCOPE item 7; review item 4).
  Opened and reconciled whenever memory is enabled, for every vector store.
- Tier model: vector tier unusable (sticky fault such as index mismatch, or transient embedding
  error) means `ready` + `tier: lexical` + reason + fix. `degraded` only when no tier works.
  Existing T2/T3 tests that expected `degraded` for a vector-tier fault are updated accordingly.
- Lexical result `distance` is converted to smaller-is-better (`1/(1+score)`); `score` (larger is
  better) is also returned. Documented in API.md.
- `build_app(with_memory=False)` by default; only `serve` passes True.
- New reason codes beyond the T3 list: `embedding_unavailable`, `embedding_backend_missing`,
  `vector_store_unavailable`, `lexical_unavailable`.

Acceptance bullet -> named test (all in `tests/test_t3_repair.py` unless noted):
- A1 tagged model names: `EmbeddingModelNameTests.test_has_model_treats_a_missing_tag_as_latest`,
  `.test_tagged_model_list_does_not_report_lexical_while_vectors_serve`,
  `.test_tier_follows_what_retrieval_actually_used`,
  `AppMemoryStateTests.test_a_tagged_ollama_model_list_reports_the_vector_tier`,
  `.test_a_missing_embedding_model_reports_lexical_with_the_pull_command`
- A2 reconcile embed error never degrades: `ReconcileEmbeddingFailureTests.
  test_embed_error_during_reconcile_keeps_memory_ready_on_both_store_kinds`,
  `.test_embed_error_during_reconcile_with_chromadb_blocked`,
  `.test_retrieve_uses_the_lexical_tier_after_a_reconcile_embed_error`,
  `.test_degraded_only_when_every_tier_fails`
- A3 both-tier failure surfaced: `BothTiersFailTests.test_a_reply_where_both_tiers_fail_is_reported_not_silent`
- B4 lexical independent of vector store: `IndependentLexicalIndexTests.
  test_default_chroma_configuration_serves_lexical_results_when_embeddings_fail`,
  `.test_lexical_index_is_opened_for_every_vector_store`, `.test_lexical_index_survives_a_failed_vector_store`,
  `LexicalStoreTests` (scoping, operators, idempotence, reopen)
- B5 distance semantics: `LexicalStoreTests.test_lexical_distance_is_smaller_is_better_and_score_is_larger_is_better`; documented in docs/API.md
- C6 index: `SqliteIndexTests.test_conversation_query_uses_an_index`,
  `.test_existing_database_without_the_index_gets_it_on_reopen`
- D7 server-owned memory: `ServerOwnsMemoryTests.test_building_the_app_for_a_non_serve_command_opens_no_store_and_starts_no_thread`,
  `.test_building_the_app_with_memory_opens_the_stores_and_catches_up_in_the_background`,
  `.test_only_serve_builds_the_app_with_memory`, `.test_the_smoke_command_builds_without_memory`,
  `.test_status_command_shows_the_memory_configuration_without_opening_it`
- E8 visibility: `VisibilityTests.test_describe_gives_info_for_fallbacks_a_warning_for_degraded_and_a_hint_for_disabled`,
  `.test_the_page_shows_a_memory_note_for_disabled_fallback_and_degraded`,
  `ServerOwnsMemoryTests.test_status_command_says_how_to_enable_a_disabled_memory`,
  `AppMemoryStateTests.test_a_missing_embedding_backend_is_an_explained_lexical_state_not_a_silent_stub`
- E9 requirements header: `VisibilityTests.test_requirements_file_says_recommended`
- F10 live three-condition check, F12 push, F13 backlog lines: not unit-testable; evidence is the
  commands and results recorded in the parking entry below.

Progress:
- [x] Declare T3 repair; record T2 reopen; map bullets to tests
- [x] Failing tests written and shown red (commit `eb222cf`; module import errors before implementation)
- [x] A, B, C, D, E implemented
- [x] Existing tests updated for the new tier semantics (tests/test_memory.py; tests/test_web.py disables memory explicitly)
- [x] Docs updated (README, ARCHITECTURE, CONFIGURATION, SECURITY, API, CLOSEOUT-SCOPE item 7)
- [x] BACKLOG lines added (item 13: five lines)
- [x] Live three-condition check recorded (item 10)
- [x] Both suite modes green; park as `T3 repair:`; push `t3-rag-default` and `RAG-SUM-GRAPH`

Evidence (2026-10-05, this machine, real Ollama with `nomic-embed-text:latest` installed, chromadb 1.3.5):
- `python -B -m unittest discover -s tests` (Chroma present): 281 tests, OK, 2 skipped, 156.6 s.
- `AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest discover -s tests` (Chroma blocked): 281 tests, OK, 2 skipped, 156.2 s.
- Live probe, `python -B -m tests.live_memory_probe [--model NAME]` (seeds 4 turns, retrieves "Where do I live?"):
  1. Chroma importable, model present (`nomic-embed-text`, a tagged list entry): state ready, store chroma, tier vector, reason "", methods all vector, top hit "Your home is in Cedar Rapids." (the live bug: tier no longer reports lexical while vectors serve).
  2. `AGENT_HARNESS_BLOCK_MODULES=chromadb`, model present: state ready, store sqlite (store_reason "chroma unavailable (ModuleNotFoundError); using sqlite fallback."), tier vector, methods vector, same top hit.
  3. Chroma importable, `--model no-such-embed-model`: state ready, store chroma, tier lexical, reason embedding_model_missing, fix "run: ollama pull no-such-embed-model", indexed 0, lexical_indexed 4, methods lexical, top hit "Where is my home?".
  4. Chroma blocked and `--model no-such-embed-model`: state ready, store sqlite, tier lexical, same reason and fix, lexical_indexed 4, methods lexical.
- Not run: no real browser check of the page's memory note (JS syntax checked with `node --check`; the note text is covered by a source-level test only); no live Ollama failure mid-reply (embedding error during a reply is covered by tests with a failing embedder).

Limitations recorded:
- A transient embedding failure is retried on every reply (and every background reconcile) with no backoff; bounded re-probe stays in T4 (BACKLOG, MEMORY_WATCHLIST item 3).
- The lexical `distance` is not comparable to a vector distance; documented in API.md.

### T3 repair 2 (review of T3 repair: accepted except one defect)

Defect: `reconcile()` held the lock across every embedding batch, so `retrieve()` queued behind the
startup background catch-up (reviewer measured 5.4 s with 400 turns at 0.4 s/batch).
Fix: `reconcile(..., wait=False)` acquires the lock non-blockingly; `retrieve()` uses it, skips its own
indexing when the catch-up holds the lock, and queries what is indexed (keyword index when the vector
index is empty). The background catch-up keeps the blocking acquire.
Test (written first, red at 2.81 s): `tests/test_t3_repair.py`
`RetrievalDoesNotWaitForCatchUpTests.test_retrieve_returns_within_about_one_batch_while_the_background_catch_up_runs`
(0.4 s/batch embedder, 6 batches; retrieve returns in under 2 batch times, serves `method: lexical`;
catch-up still finishes and indexes everything).
Evidence (2026-10-05): `python -B -m unittest discover -s tests` 282 tests OK (skipped 2), 158.3 s;
`AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest discover -s tests` 282 tests OK (skipped 2), 159.6 s.
Live timing (2026-10-05, this machine, real `nomic-embed-text:latest`, Chroma store, throwaway temp dir):
`python -B -m tests.live_memory_probe --backlog 800` (new mode: seeds 800 turns, starts the catch-up,
retrieves after 0.5 s, prints times). Result: `retrieve()` 0.221 s, served by `vector` from a partial
index (96 of 800 vectors, 800 of 800 keyword rows at that moment); whole catch-up 7.73 s; afterwards
tier `vector`, state `ready`. The reviewer's run on the same fix saw 0.00 s, keyword-served, 0 vectors at
0.5 s; the difference is timing of the first embedding batch, not a code difference. Evidence about this
machine, not pass or fail; nothing is gated on it. Added to the T6 live smoke matrix (CLOSEOUT-SCOPE item 4).
BACKLOG: partial-vector retrieval during catch-up (no blending) and late keyword indexing of turns that
finish during catch-up (cosmetic) added.
Reviewer's remaining manual step (not done by the builder): open the page once with memory in fallback mode
(`memory.store: "sqlite"` in a test config) to see the informational note, then fast-forward `RAG-SUM-GRAPH`.
T4 not started; not declared.

## Superseded parking entry: T3 (first pass, not accepted)

Status: **complete; awaiting USER acceptance.**
Branch: `t3-rag-default` (off `RAG-SUM-GRAPH`).

Evidence:
- Chromadb-present mode: `python -B -m unittest tests.test_memory` → 31/31 OK
- Chromadb-absent mode: `AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest tests.test_memory` → 31/31 OK
- Full suite: `python -B -m unittest discover -s tests` → 255 tests, 2 skipped, 0 failures (2026-10-05)
- Commits: `8adac0e` (failing tests), `2ccf646` (requirements rename, default-on), `cf74058` (FTS5, status machine, bounded reconcile, model_checker), `02af0ee` (validation fix, chroma close, docs)

Expected outcome: conversation memory is on by default for new configs; three-tier state machine
with machine-readable reasons; FTS5 lexical tier always maintained; full suite passes with chromadb
absent and present; live check under three conditions.

Scope:
1. New configs: `memory.enabled true`.
2. States `ready`/`degraded`/`disabled` with machine-readable reasons and human fix text.
3. Detect missing embedding model from backend model list; report pull command.
4. `enabled=false` → no memory store opened at all.
5. Rename `requirements-rag.txt` → `requirements.txt`; update all references.
6. Latency: index finished turns at reply completion; background startup catch-up; bounded batches
   per retrieval; tests prove no unbounded first-reply stall.
7. FTS5 lexical tier (REQUIRED): FTS5 table in `vectors.sqlite3`; scoped, ranked, sanitized;
   `method: "lexical"`; per-reply fallback when embed fails; FTS5-absent simulation tested.
8. Tests: both modes; tests not needing memory disable it explicitly; no static third-party imports.
9. Docs: README, ARCHITECTURE, CONFIGURATION, SECURITY, API, charter invariant.

Acceptance → named test (every bullet maps to at least one test):
- New config `enabled=True`: `test_memory_default_on_for_new_config`
- Reason `embedding_model_missing` + fix text: `test_status_reason_embedding_model_missing`
- Reason `index_incompatible`: `test_status_reason_index_incompatible`
- Reason `transient`: `test_status_reason_transient`
- Reason `all_tiers_failed`: `test_status_reason_all_tiers_failed`
- `tier` field in status: `test_status_tier_vector` / `test_status_tier_lexical`
- FTS idempotent reconcile: `test_fts_reconcile_idempotent`
- FTS conversation scoping: `test_fts_scoped_to_conversation`
- FTS ranking: `test_fts_ranking`
- FTS query sanitization: `test_fts_query_sanitizes_special_chars`
- FTS method field: `test_fts_method_field_is_lexical`
- FTS absent simulation: `test_fts_absent_degrades_only_when_no_vector_tier`
- Per-reply embed fail → FTS (no degrade): `test_per_reply_embed_fail_uses_fts_no_degrade`
- Bounded reconcile (no stall): `test_reconcile_bounded_per_retrieve`
- Post-reply background reconcile: `test_background_reconcile_after_reply`
- `enabled=false` → no store opened: already in `test_disabled_memory_does_no_index_work`

Progress:
- [x] Tick T2 DoD; fast-forward RAG-SUM-GRAPH; create branch; declare T3 in PLAN.md
- [x] Write all failing tests (guardrail: new behavior needs failing test first)
- [x] Scope 1: default-on (`DEFAULTS["memory"]["enabled"] = True`)
- [x] Scope 5: rename requirements-rag.txt → requirements.txt
- [x] Scope 2+3: machine-readable reasons, fix text, model_checker, tier field in status
- [x] Scope 7: FTS5 table in SqliteStore; reconcile and query; sanitize; method field
- [x] Scope 6: bounded reconcile per retrieve; post-reply background thread in generation.py
- [x] Scope 4: assert `enabled=false` opens nothing (extend existing disabled test)
- [x] Scope 8: run both modes; verify no static imports break
- [x] Scope 9: docs (README, ARCHITECTURE, CONFIGURATION, SECURITY, API, charter)
- [x] Park T3 with evidence

## Parked: T2 Store Seam + SQLite Fallback

Status: **accepted by USER (2026-10-05).**
Branch: `t2-store-seam` (off `RAG-SUM-GRAPH`).

Expected outcome: `memory/cartridge.py` is split into orchestration, Chroma store, and SQLite
vector store; a store contract is covered by the same test suite run against both; SQLite
vector fallback is functionally equivalent to Chroma for same-conversation retrieval;
`memory.store` selects the preferred store (`chroma` default | `sqlite`); `memory.strict`
(default false) enables fallback to the next tier on open failure; the full suite is green
with chromadb absent and present.

Scope:
1. Split `memory/cartridge.py`: orchestration (reconcile, retrieve, state) stays; Chroma moves
   to `memory/chroma_store.py`; add `memory/sqlite_store.py`. Store interface: `open`, `ids`,
   `dimensions`/`set_dimensions`, `upsert`, `query` by conversation, `close`.
2. SQLite store: `runtime/memory/vectors.sqlite3`; meta table (schema, embedding_identity,
   dimensions); rows keyed by event seq with conversation_id, role, text, and L2-normalized
   float32 blob (array module, little-endian regardless of host); index on conversation_id;
   score by dot product; distance = 1 − dot via heapq; thread-safe like EventStore.
3. Selection: `memory.store` accepts `chroma` (default) | `sqlite`; `memory.strict` (default
   false) disables fallback. With `strict: false`, if the preferred store fails to open the
   system tries the next tier: `chroma` falls back to `sqlite`. With `strict: true`, the
   preferred store is used exclusively; failure degrades memory without fallback. `sqlite`
   never imports chromadb (test asserts it). Existing configs with `"store": "chroma"` are
   fully fault-tolerant by default. Selection happens once at startup. Report `store` and
   `store_reason` in status.
   Amendment approved: USER (2026-10-05); drops `auto`; adds `memory.strict`.
4. Contract tests run the same suite against the SQLite store and the fake Chroma client:
   idempotent upsert, conversation scoping, distance ordering, reopen persistence, dimension
   and identity mismatch, missing-id detection. If chromadb is installed, also run against
   real Chroma and assert same top-k order for same vectors; otherwise skip.
5. Benchmark and record (do not gate) SQLite retrieval time at 1k, 5k, and 20k vectors; state
   the documented practical limit in CONFIGURATION.

Non-goals: default-on (T3), lexical tier (T3), banner or status-page changes (T3),
retrieval-quality changes.

Acceptance:
- Full suite passes with chromadb absent AND present.
- `sqlite` selection never imports chromadb (asserted by test).
- `memory.strict: false` (default) causes `chroma` to fall back to `sqlite` on open failure; tested.
- `memory.strict: true` degrades without fallback; tested.
- Contract tests assert same behavior from both stores.
- Benchmark results recorded in CONFIGURATION.
- Chroma behavior is unchanged from T1 (existing tests adapted and pass).
- Status reports `store` and `store_reason`.

Known risks: Chroma API surface requires exact match; dot-product scoring must rank identically
to cosine for L2-normalized vectors.

Progress: (approved — item 0 done as planning commit)
- [x] Apply dependency policy to PROJECT-CHARTER.md (invariant) and ARCHITECTURE.md (add Dependency policy section)
- [x] Write contract test suite (failing) for both stores
- [x] Split cartridge.py into orchestration, chroma_store.py, and sqlite_store.py
- [x] Implement SQLite store with meta table, little-endian blob rows, dot-product query
- [x] Implement store selection logic (`memory.store`, `memory.strict`) and status reporting
- [x] Update config.py validation for `memory.store` and `memory.strict`
- [x] Update CONFIGURATION.md for `memory.store` (chroma|sqlite) and `memory.strict` (bool)
- [x] Add contract test suite and run against both stores; benchmark and document practical limits
- [x] Run full suite with chromadb absent and present; park with evidence

## Log

- 2026-10-05 T2 repair 3 parked on `t2-store-seam`. Added 5 ConversationMemory-level
  tests to tests/test_memory.py: (1) chroma strict=False unavailable → ready/sqlite/
  store_reason set/retrieve works; (2) strict=True unavailable → degraded/_store=None;
  (3) store_kind=sqlite → chromadb not imported (verified via recording find_spec hook
  with sys.modules eviction/restore); (4) status() fields: store/store_reason present
  for ready, fallback, and degraded; absent for disabled; (5) identity mismatch →
  degraded/_store=None/store="chroma" (no fallback despite strict=False).
  Evidence (2026-10-05, chromadb 1.3.5, Python 3.13.6):
    present: python -B -m unittest discover -s tests → 239 OK (skipped=2) in 152 s
    absent:  AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest discover -s tests
             → 239 OK (skipped=2) in 152 s

- 2026-10-05 T2 repair 2 parked on `t2-store-seam`. The earlier absent-run figure (231/231,
  T2 repair: commit) was not a real absent run: support.py used the legacy find_module/
  load_module finder protocol, which Python 3.12+ ignores; on 3.13.6 chromadb still
  imported successfully and TestRealChromaOrdering ran and passed. Fixed by replacing
  with a PEP 451 find_spec finder that raises ModuleNotFoundError for blocked names.
  Added tests/test_support_blocker.py: three assertions — with env var set, importing
  a blocked module raises ImportError and _HAS_CHROMADB is False (so TestRealChromaOrdering
  skips); without env var, chromadb imports successfully when installed.
  Evidence (2026-10-05, chromadb 1.3.5, Python 3.13.6):
    present: python -B -m unittest discover -s tests → 234 OK (skipped=2) in 151 s
      skipping: TestBlockerActive (2 tests, AGENT_HARNESS_BLOCK_MODULES not set)
    absent:  AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m unittest discover -s tests
             → 234 OK (skipped=2) in 150 s
      skipping: TestRealChromaOrdering (chromadb absent) + TestBlockerInactive (var set)
      passing: TestBlockerActive confirming _HAS_CHROMADB=False and ImportError raised

- 2026-10-05 T2 repair parked on `t2-store-seam` (see T2 repair: commit). Full suite 231/231
  with chromadb 1.3.5 installed (152 s). NOTE: the concurrent "absent" run (231/231) used the
  broken legacy finder (find_module) that Python 3.13 ignores and was not a real absent run;
  superseded by T2 repair 2 entry above. Repairs from T2 repair: SqliteStore L2-normalises
  vectors at upsert and query (guard for zero vectors); query is locked like writes; fake Chroma
  client in contract tests normalises and uses true cosine; non-unit-vector contract test added
  (8th assertion, run against both stores); TestRealChromaOrdering includes a non-unit vector;
  test_memory.py was adapted not unmodified (patch path, _store.dimensions(), strict=True for
  degradation test); fallback: any non-ValueError exception falls back to sqlite unless
  strict=true; ValueError (identity/schema mismatch) is a config error and never falls back;
  CONFIGURATION.md prose corrected to match benchmark numbers and documents
  mismatch-no-fallback behaviour; _projectmapper/ added to .gitignore.

- 2026-10-05 close-out plan declared: T2 declared and scope recorded in PLAN.md; T3–T6 full
  scopes, non-goals, and exit criteria recorded in docs/CLOSEOUT-SCOPE.md; dependency policy
  and charter invariant change approved by USER (2026-10-05); docs/BACKLOG.md created; T2
  awaiting USER approval. Planning fixes: dependency policy applied to PROJECT-CHARTER.md and
  ARCHITECTURE.md; T1 heading renamed to Completed work; BACKLOG.md corrected.

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
  bounded-extraction tasks; the final initial-T1 commit closed the API/docs task.
  Verification: local `qwen2.5:0.5b` raw oversized request failed visibly,
  integrated fallback answered `COBALT, VIOLET, and MARIGOLD.` with
  `prompt_eval_count=256`; 203 automated tests passed. Known boundary: only the
  explicit final `Question:` input shape is supported, extraction is exact-
  sentence validated, and one local model run is not a general reliability
  claim. This is the initial-T1 checkpoint; its later repair and acceptance
  supersede its pending-review state.

- 2026-10-04 T1 task 1 evidence: `OllamaBackend.chat` sends `truncate=false`.
  Request-shape and near-budget runner tests passed (6 tests); the ordinary
  request remained byte-for-byte unchanged. The config guide documents that the
  harness owns truncation/fallback decisions.

- 2026-10-04 T1 task 2 evidence: focused backend, overflow, queue/deadline,
  chunk-cap, depth-cap, recovery, and architecture checks passed (11 tests).
  The local `qwen2.5:0.5b` smoke classified raw overflow as
  `context_exceeded`, returned `COBALT, VIOLET, and MARIGOLD.`, used
  `prompt_eval_count=256`, and recorded source event/ranges/hash.

- 2026-10-04 T1 task 3 close-out: `docs/API.md` documents `window.derived`,
  source-range semantics, depth, progress, and reactive reset. Configuration
  and architecture describe limits and visible failures. The initial full suite
  passed 203 tests; no cache, new event kind/table, larger-model route, or
  general document-format support was added.

- 2026-10-04 T1 repair verification: offset-preserving spans, 12% overlap,
  whitespace-normalized exact matching, outward snapping/merged ranges, depth-4
  reduction, strict shrinkage, total-call cap, and bounded retrieval/system
  prompt behavior were implemented and tested. Full suite: 211 tests. Local
  smoke returned `The hidden project marker is VIOLET.` at 315 prompt tokens.
  Commits `35714ed` and `ad57b6b` were pushed; repair parked pending acceptance.

- 2026-10-04 accepted T1 repair follow-up: fixed reduction sizing to use source
  offsets and restore oversized merged spans to units. The 1,540-character
  regression yields four chunks at 500 characters; multi-chunk reduction and
  non-shrinking fail-closed cases pass. Full suite: 214 tests in 152.203s.
  Local smoke: raw `context_exceeded`, 315 prompt tokens, derived depth 1, and
  final reply included the exact VIOLET fact plus one distractor excerpt.
  Commit `ea72022` was pushed. API/concept docs now state overlap counts toward
  each pass's 8-chunk cap and snapping uses line or sentence granularity.

- 2026-10-04 T1 accepted and fast-forwarded from
  `t1-bounded-overflow-extraction` to `RAG-SUM-GRAPH`; `main` remains unchanged.
  The exact merge and push state is the current Git state above.

- 2026-10-04 local model comparison: ran the same `num_ctx=2048`,
  `max_reply_tokens=256` overflow fixture through already-downloaded Ollama chat
  models using `python -B tests/ollama_overflow_smoke.py MODEL`. All seven runs
  completed fallback at depth 1, classified the raw request as
  `context_exceeded`, and reported all planted facts in derived source spans.
  Final response quality varied:

  | Model | Final response on hidden-marker question | Prompt tokens |
  |---|---|---:|
  | `qwen2.5:0.5b` | Correct VIOLET sentence with one distractor excerpt | 315 |
  | `qwen2.5:1.5b` | Correct VIOLET sentence | 316 |
  | `qwen2.5:3b` | Incorrect: `MARIGOLD.` | 268 |
  | `qwen2.5:7b` | Correct VIOLET sentence | 268 |
  | `phi3:mini-128k` | Noisy; includes VIOLET but also unsupported elaboration | 294 |
  | `qwen3.5:4b` | Correct VIOLET sentence | 288 |
  | `qwen3.5:9b` | Correct VIOLET sentence | 305 |

  Extraction/span validation establishes that included context is source text;
  it does not validate the model's final answer. In this small sample, 3b
  selected the wrong planted value, while Phi-3 added unsupported prose.
  Embedding-only models and the 14B/35B models were not run. The smoke runner
  now accepts an optional downloaded model name; this is a fixture comparison,
  not a general benchmark.

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

## Completed work: T1 bounded overflow extraction repair

Approved: T1 reopen (USER, 2026-10-04)

Status: accepted and fast-forwarded to `RAG-SUM-GRAPH`; `main` remains
unchanged. Prior T1 implementation and verification remain the baseline.

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
   park for USER review, and wait for acceptance before considering a merge.
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
- [x] USER acceptance received; fast-forward T1 into `RAG-SUM-GRAPH` only.
- [x] Keep `main` unchanged pending a separate USER decision.

T1 repair follow-up progress:
- [x] Record the accepted review defect and amended scope.
- [x] Size chunks by source offsets and restore oversized merged spans to
  line/sentence units before chunking.
- [x] Add the 1,540-character/20-span regression, multi-chunk reduce scenario,
  and a non-shrinking fail-closed scenario.
- [x] Document that overlap counts toward the eight-chunk per-pass cap and that
  snapping is to line or sentence granularity; rerun full suite and local smoke.
- [x] Park the follow-up as `T1 repair:` without merging.
- [x] USER acceptance received; repair merged to `RAG-SUM-GRAPH` only.
- [x] Keep `main` unchanged pending a separate USER decision.

Implementation, repair, and verification evidence is recorded in `## Log`.

Known risks: the 0.5B extractor may miss or miscopy relevant sentences despite
temperature zero; chunk boundaries and character-range mapping need to be
deterministic; Ollama error shapes can change by version. A single fixture proves
the mechanism for that shape, not general document understanding.

Fixture constants: `num_ctx=2048`, `max_reply_tokens=256`,
`CHUNK_SIZE_FRACTION=0.40` (a fraction of `num_ctx` for each source chunk), and
`MAX_EXTRACTION_CHUNKS=8`. These are T1 fixture/prototype constants, not new user
settings. The ordinary near-limit fixture is sized below
`budget_tokens(2048, 256)` and must be accepted unchanged.

Current implementation and acceptance status: see the concise state block at
the top; per-task evidence and decisions are in `## Log`.

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
