# Backlog

Deferred items and out-of-scope defects. Add one line per item; do not fix here.
Items promoted to a tranche are removed from this list when that tranche is declared.

## Deferred (outside current T2–T6 close-out scope)

- History-overflow condensing: multi-level summarization or condensing of old turns in place.
- Reuse cache table for extracted overflow spans.
- Graph construction and rehydration.
- Larger-model routing for overflow fallback.
- Relevance-cutoff tuning or query-composition changes (revisit only if T5 numbers show harm).
- Hybrid vector + lexical ranking.
- Cross-conversation retrieval.
- New input formats for overflow fallback (beyond the declared `Question:` shape).
- llama.cpp real-server smoke: only scripted-fake coverage; no recorded real-server run.
- Chroma reactive-path integration test against a real Chroma server (no recorded smoke for the overflow-retry path with a live Chroma index).
- Bounded query context improvement for retrieval (MEMORY_WATCHLIST.md item 1).
- Relevance filtering with calibrated distance cutoff (MEMORY_WATCHLIST.md item 2).
- Transient-degraded recovery with bounded re-probe and backoff (MEMORY_WATCHLIST.md item 3; covered by T4 item 6).
- Automatic strategy learning.
- Arbitrary plugin registries.
- Multi-model fallback for overflow extraction.
- Cloud services or remote sync.
- T6 cleanup: delete merged feature branches after tagging (tranche branches already fast-forwarded into `RAG-SUM-GRAPH`).
- EventStore WAL mode: only if a database lock error is actually reproduced.
- A "dropped" stream marker so a client dropped for being slow reconnects at once instead of waiting.
- Bound the token estimator's learned samples (use a deque).
- In-memory projection of the full event history at boot (v2): startup reads and replays everything.
- TLS and token rate limiting (already documented as not provided in SECURITY.md).
