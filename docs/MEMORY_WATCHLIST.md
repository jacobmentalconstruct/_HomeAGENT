# Memory watchlist

These are known observations from the first local RAG review. They are not
current defects or a commitment to expand T1. Keep them visible while using the
cartridge and open a new, explicitly scoped tranche only when evidence shows a
useful response is needed.

## Bounded query context

The retrieval query is the raw current user prompt. Short follow-ups such as
“and the other one?” may have too little semantic signal to find the intended
older turn.

Watch for: a follow-up that clearly refers to earlier material but returns no
useful source, or a source that is unrelated while the intended subject is in
the recent conversation.

When a symptom is repeatable, consider composing the query from the current
prompt plus a small bounded amount of recent context. Keep the query bounded so
it does not recreate the full-history cost that the cartridge is meant to avoid.

## Relevance filtering

The cartridge currently takes the configured top-k results and lets the prompt
budget decide which excerpts fit. There is no distance cutoff calibrated to the
embedding model.

Watch for: clearly unrelated excerpts being injected, especially when the
conversation has many indexed turns and the query is vague.

When a symptom is repeatable, measure the distance distribution for the active
embedding model before choosing a configurable cutoff. Do not add an arbitrary
threshold based on one smoke test.

## Recovery from transient degradation

An embedding or Chroma failure marks memory degraded for the rest of the
process. Chat continues, but memory does not automatically re-probe until the
server restarts.

Watch for: a temporary Ollama or local-index outage recovering while the server
remains up, followed by every later reply still reporting degraded memory.

When a symptom matters, design a bounded retry or re-probe policy with an
explicit latency limit and status semantics. Avoid retrying every reply without
backoff during a sustained outage.
