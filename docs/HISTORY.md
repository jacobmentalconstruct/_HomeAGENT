# Project history

The repository has had three epochs. Each tranche number (T1, T2, ...) is local to its epoch; cite them as E2-T1,
E3-T4, and so on. Epochs 1 and 2 are historical and kept as tags.

| Epoch | What it was | Commits |
|---|---|---|
| 1 | `_HomeAGENT` 0.1.0, the original standard-library chat harness | `dc623ae` |
| 2 | RAG v1.0, optional Chroma conversation memory (its T1 and T2) | `2dce07d` to `62be955` (14 commits after the root) |
| 3 | Context scaling, 0.2.x (T0 to T7) | `dfcc9f1` to `v0.2.1` |

## Epoch 1: _HomeAGENT 0.1.0 (historical)

tag: epoch-1-harness-0.1.0

2026-10-04, commit `dc623ae`. A private chat server for local models: standard library only, append-only SQLite event
log, Ollama and llama.cpp adapters, phone-friendly page, control panel. 174 tests.

## Epoch 2: RAG v1.0 (historical)

tag: epoch-2-rag-v1.0

2026-10-04, commits `2dce07d` to `62be955`. Optional conversation memory.

- E2-T1: local conversation RAG cartridge: Chroma persistent index of completed turns, Ollama embeddings,
  same-conversation retrieval inside the prompt budget, source references, graceful detach. Repaired after review
  (Chroma metadata update, per-conversation reconcile).
- E2-T2: public-release polish: Chroma telemetry disabled, docs aligned.

Evidence at the end: 193 tests; live smoke with `nomic-embed-text` and `qwen2.5:1.5b`. Its lasting lesson: acceptance
bullets need a named test, and a unit-test double can hide a real-library constraint.

## Epoch 3: context scaling, 0.2.x (current)

tags: v0.2.0, v0.2.1

Starts at `dfcc9f1`, committed as a new root: a copy of epoch 2's files plus the new project charter and planning
documents (seven files differ from `62be955`). Ends at `v0.2.1`.

- E3-T0 and E3-T1: bounded overflow extraction for one oversized message ending in `Question:`.
- E3-T2: store seam; SQLite vector fallback.
- E3-T3: memory on by default; keyword tier.
- E3-T4: hardening: provenance check, overflow switch, derived-context page block, re-probe.
- E3-T5: eval of 5 models x 3 compositions x 8 fixtures ([EVAL-RESULTS.md](EVAL-RESULTS.md)).
- E3-T6: release 0.2.0 (tagged at `fd7c60c`).
- E3-T7: audit fixes, 0.2.1.

357 tests at v0.2.0 and 371 at v0.2.1. The full tranche record is in [PLAN.md](../PLAN.md) and
[CHANGELOG.md](../CHANGELOG.md).

## Why the epochs join the way they do

Epoch 3 was started from a copy of epoch 2 without git metadata, so git cannot link them by itself. `main` joins them
with one merge commit whose tree is the `v0.2.1` tree and whose parents are the end of epoch 2 and `v0.2.1`. Check out
an epoch with its tag, for example `git checkout epoch-2-rag-v1.0`.
