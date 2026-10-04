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
| `GET /api/conversations/{id}` | `{"id", "title", "open_generation", "window", "turns": [{"role", "text", "ts", "model", "failed", "truncated"}]}`. `window` describes what the latest reply was sent. |
| `POST /api/conversations/{id}/messages` | Send a message: `{"text": "...", "model": "backend:model"}`. `202 {"generation_id": "..."}`. |
| `GET /api/generations/{id}/stream` | Follow a reply as it is written (below). |
| `GET /api/status` | `{"uptime_seconds", "replies_in_progress", "conversations", "default_model", "loaded"}`; `loaded` lists the models each backend holds in memory. |
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
| `running` | `window` | Your turn has come. `window` is `{"start", "sent", "dropped", "estimated_tokens", "budget", "chars", "messages"}`. |
| `delta` | `text` | More of the reply. |
| `done` | `summary` | The reply is complete: `{"stop_reason": "complete" or "truncated", "prompt_tokens", "reply_tokens"}`. |
| `failed` | `error` | `{"reason", "message", "partial_text"}`. |
| `ping` | | Sent every 15 seconds while waiting, to keep the connection alive. |

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
