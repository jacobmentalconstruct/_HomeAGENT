# Project charter: context scaling

## Purpose

Evolve this local model harness so it can select and prepare the right representation of available information for each model request. The system should preserve useful meaning as conversation history grows, respond to context limits, and leave room for other preprocessing and routing choices when they solve a demonstrated problem.

The project is an experimental, local-first context-processing system built on a working chat harness. Summarization is one possible transformation. The long-term direction may include other useful representations or routes, chosen for reasons such as request type, information structure, model capability, or context budget.

## Desired product state

The project will have reached its intended prototype state when:

1. A model request can be assembled from recent raw turns and one or more derived context representations under a known token budget.
2. A context policy can choose a transformation or model route for a stated, testable reason, including context pressure.
3. Derived representations preserve links to their source material, identify their method/version, and can be refreshed or rebuilt from authoritative local data.
4. The system can demonstrate, with a deterministic test and a local-model scenario, that an oversized payload succeeds using transformed context where the untransformed request would not fit, while retaining the user's instruction verbatim and the information needed to answer a defined question.
5. The existing chat remains usable when an optional transformation or retrieval component is disabled or unavailable.
6. Operators can inspect what representation and source material went into a reply, and the project record explains the limits of that evidence.

This is a prototype end state, not a commitment to build a general knowledge platform, autonomous agent, or production multi-user service.

## First proof

The first proof is a context-overflow fallback integrated into the existing generation path. It addresses a concrete case the current bounded-window code does not solve: the newest user message itself is too large, even after ordinary recent-window selection.

Preserve the user's instruction or question when transforming an oversized payload. The prototype must use a declared, testable input shape and retain provenance for transformed material. It should demonstrate one bounded transformation through the existing generation path, then stop and assess evidence before adding other transformations or model routes. Tranche-level algorithms and parameters belong in `PLAN.md`, not in this charter.

## Stop conditions for the prototype

Stop expanding the prototype when all of these are demonstrated:

- The normal path still sends the newest user instruction or question verbatim and remains within the configured prompt budget.
- The fallback is entered only for a defined condition and cannot loop indefinitely.
- A fixed fixture with known facts cannot fit on the ordinary path, then succeeds through the fallback with the instruction verbatim and required facts intact.
- Each transformed segment can be traced to source event IDs; generated context is labeled as derived rather than original evidence.
- A restart or rebuild does not turn derived context into an independent source of truth.
- Fallback failure is visible and leaves ordinary chat and durable transcript history intact.
- Tests cover trigger, non-trigger, budget, source traceability, termination, and failure behavior; setup and limitations are documented.

If these conditions pass, park the proof and evaluate observed gaps before adding another transformation or route. Do not add a graph, multiple summarization levels, generic plugin framework, or a second model route solely to anticipate future work.

## Invariants

- The append-only SQLite event log remains authoritative for conversation evidence unless a later approved design explicitly replaces it.
- Summaries, embeddings, extracted facts, graphs, clusters, and other interpretations are derived artifacts. They carry provenance and must not silently rewrite source history.
- Recent context and the newest user's instruction or question are protected by prompt-budget rules. Oversized payload text may be transformed only while retaining provenance.
- Preprocessing and retrieval failures must not corrupt history or make the ordinary chat path unusable.
- The local privacy boundary and optional-dependency behavior remain in force unless a specific future tranche changes them.
- Every new abstraction must support a current acceptance criterion; extension points without a demonstrated use stay deferred.

## Current constraints

- Python harness with local Ollama as the exercised model path; llama.cpp adapter has scripted-fake coverage but no recorded real-server smoke.
- Append-only SQLite conversation events are the durable source. Chroma is an optional, derived, conversation-scoped retrieval index.
- The current prompt window already selects the newest messages that fit and rejects a newest message that is itself too large. A fallback must be inserted into this actual composition/generation path, not assumed to wrap an arbitrary string prompt.
- The architecture test currently forbids static third-party imports, import cycles, core-to-interface dependencies, and modules over 400 lines. Optional Chroma loading uses a dynamic import.
- This project is developed in Git with a separate tranche branch and commits. Record the active branch and commit state in `PLAN.md`; historical branch references describe the earlier RAG development line.

## Deferred until evidence supports them

Multiple transformation types, graph construction and rehydration, recursive summary trees, extraction of durable facts or decisions, cross-conversation knowledge, document ingestion, user editing/approval interfaces, automatic strategy learning, arbitrary plugin registries, multi-model fallback, cloud services, and unrelated harness redesign.

These are possible directions, not promises. Revisit them only after the first proof reveals a concrete need and a bounded acceptance test.

## Recovery rule

At every parked checkpoint, `PLAN.md` must state the current repository condition, active or parked tranche, exact next action, completed and open acceptance items, commands and observed results, limitations, and temporary/runtime artifacts. A new session should be able to resume from those files without relying on chat history. Never record an unrun check as passed or a proposed choice as an approved decision.
