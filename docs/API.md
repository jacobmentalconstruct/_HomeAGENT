# HTTP API

The page and the control panel use this API, and you can use it from scripts. Replies are JSON unless noted.

## Authentication

Every `/api/...` request needs the access token:

```
Authorization: Bearer <token>
```

A missing or wrong token gets `401`. The page itself (`GET /`) needs no token. Requests also accept an optional `X-Client-Name` header (up to 40 characters), which is recorded as a label next to the client's address. It is a label, not an identity.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /` | The chat page. (`GET /favicon.ico` gets an empty `204`, so browsers stop asking for an icon.) |
| `GET /api/models` | Models from every backend: `{"models": [{"choice", "backend", "model", "available", "chat", "reason", "message"}], "default": "..."}`. `chat` is false for models that cannot chat (embedding models). A backend that is down appears with `available: false` and a `reason`. |
| `POST /api/default` | Set the default model: `{"model": "backend:model"}`. Saved in the config. `400` if it is unknown, unavailable or not a chat model. |
| `GET /api/conversations` | `{"conversations": [{"id", "title", "updated", "turns", "busy"}]}`, newest first. |
| `POST /api/conversations` | Create one: `201 {"id": "..."}`. |
| `GET /api/conversations/{id}` | `{"id", "title", "open_generation", "window", "turns": [{"role", "text", "ts", "model", "failed", "truncated"}]}`. `window` describes what the latest reply was sent, including any derived context and its provenance. |
| `POST /api/conversations/{id}/messages` | Send a message: `{"text": "...", "model": "backend:model"}`. `202 {"generation_id": "..."}`. |
| `GET /api/generations/{id}/stream` | Follow a reply as it is written (below). |
| `GET /api/status` | `{"uptime_seconds", "replies_in_progress", "conversations", "default_model", "loaded", "memory"}`; `memory` reports `enabled`, `state` (`disabled`, `ready`, or `degraded`), `store` (the vector store in use) and `store_reason` (why it is not the configured one, for example a Chroma fallback; empty otherwise), `tier` (`vector`, `lexical`, or `none` when degraded), `reason` (machine-readable cause, empty when healthy), `fix` (human text, empty when healthy), `indexed` (vector entries), `lexical_indexed` (keyword entries), `failed_retrievals` and `last_error` (replies where every tier failed), `retry_in_seconds` and `probe_failures` (the vector tier's backoff: seconds until the next background probe, and consecutive failed probes), and an error text while any tier has a fault. `state` is `degraded` only when no tier works. |
| `POST /api/unload` | Unload models from GPU memory: `{"unloaded": {"ollama": ["model", ...]}}`. `409` while a reply is running. |

Message text is limited to 20,000 characters and request bodies to 1 MB.

## Following a reply

`GET /api/generations/{id}/stream` returns newline-delimited JSON (`application/x-ndjson`) and stays open until the reply ends. The first line is always a snapshot, so a client that connects late, or reconnects, sees everything so far:

```
{"type": "snapshot", "generation_id": "...", "state": "queued|running|done|failed",
 "position": 0, "text": "...", "error": null, "summary": null, "window": {...}}
```

After that, one of these per line:

| `type` | Fields | Meaning |
|---|---|---|
| `position` | `position` | Replies ahead of yours on this model. |
| `running` | `window` | Your turn has come. `window` includes context counts, retrieved `sources`, and memory state (`enabled`, `state`, `store`, `store_reason`, `tier`, `reason`, `fix`, `indexed`, `error`, and the other status fields above). Sources list older turns retrieved from this conversation and included in the prompt; each source carries a `method` field (`vector` or `lexical`). For both methods `distance` means smaller is better, but the scales are different and must not be compared across methods: a vector distance is cosine distance; a lexical `distance` is `1 / (1 + score)` in (0, 1], where `score` (larger is better, also returned by the keyword index) is the clamped negated BM25 value. When overflow extraction is used, `window.derived` contains the method/version, transformed text, and source event IDs with character ranges and hashes. |
| `progress` | `phase`, `completed`, `total` | Overflow extraction progress while the reply holds its model queue ticket. `completed` counts finished source chunks; `total` is the bounded chunk count. |
| `reset` | | The first attempt hit a backend context error; discard any partial text before the single fallback retry. |
| `delta` | `text` | More of the reply. |
| `done` | `summary` | The reply is complete: `{"stop_reason": "complete" or "truncated", "prompt_tokens", "reply_tokens"}`. |
| `failed` | `error` | `{"reason", "message", "partial_text"}`. |
| `ping` | | Sent every 15 seconds while waiting, to keep the connection alive. |

When the overflow fallback is used, `window.derived` has this shape:

```json
{
  "method": "extractive_map_reduce",
  "version": 2,
  "depth": 1,
  "composition": "baseline",
  "text": "The source spans included with the reply...",
  "sources": [
    {"event_id": 51, "char_range": [120, 340], "source_sha256": "...", "role": "middle"}
  ]
}
```

`composition` names how the prompt was put together (`baseline`, `small_ends` or `block_by_question`; see ARCHITECTURE) and each source's `role` is `head`, `middle`, `tail` or `question`; records from before these fields existed verify as `baseline`. `depth` is 1 for initial extraction and increments for recursive reduction,
with a hard maximum of 4. `sources` includes half-open character ranges in the
original user event; the question range comes from the parsed `Question:`
offset. Version 2 validates whitespace-normalized exact source substrings,
snaps matches outward to the enclosing line or sentence granularity, and merges
overlapping ranges. The eight-chunk cap applies separately to each extraction
or reduction pass; each overlapped chunk counts toward that cap. Progress uses
phase `extract` for source chunks and `reduce-N` for later reduction levels. All
model calls share a total-call cap and generation deadline.

Character ranges are half-open offsets into the original event text. The source
event remains authoritative; this field describes derived text included in the
model prompt.

The prototype accepts only a single oversized user message containing a
document-like payload followed by a final explicit `Question:` section. It does
not infer instructions from arbitrary messages or support arbitrary file
formats. Preflight is the primary overflow trigger on supported backends; the
single reactive retry is Ollama-only. An oversized system prompt fails
immediately with `context_exceeded` because it is not a transformable user
payload. Retrieval for an oversized message uses only a bounded question query,
not the full document.

If the reply was already over when you connected, you get just the snapshot, with `state` set to `done` or `failed`. Disconnecting never stops a reply.

## Status codes

`200`/`201`/`202` success. `400` a bad request body, or a model choice naming an unknown backend (a model name that does not exist on a known backend is accepted, and the reply then fails with that backend's own error). `401` bad token. `404` unknown path, conversation or reply. `409` that conversation is still answering (or, for unload, a reply is running). `411` and `413` the body is missing a length or is too large. `500` the server could not save the setting. `501` an unsupported HTTP method. `502` `POST /api/default` could not reach the backend. `503` too many connections at once.

## Example

```bash
TOKEN=...   # from: python harness.py token
BASE=http://localhost:8765

CONV=$(curl -s -X POST $BASE/api/conversations -H "Authorization: Bearer $TOKEN" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
GEN=$(curl -s -X POST $BASE/api/conversations/$CONV/messages -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" -d '{"text":"Hello!","model":"ollama:qwen3.5:9b"}' \
      | python -c "import sys,json;print(json.load(sys.stdin)['generation_id'])")
curl -sN $BASE/api/generations/$GEN/stream -H "Authorization: Bearer $TOKEN"
```
