# Architecture

_HomeAGENT is one Python process (plus an optional control-panel window). The normal chat path uses the standard library; the optional persistent memory cartridge uses Chroma. This page explains how the pieces fit and why. The Python package is called `agent_harness`, and `harness.py` is its entry point.

```
 phone / laptop                      this PC
┌──────────────┐   HTTP   ┌────────────────────────────────────────────┐
│ page (HTML)  │ ───────► │ interfaces/web.py   token check, routes    │
└──────────────┘          │        │                                    │
┌──────────────┐   HTTP   │        ▼                                    │
│ control      │ ───────► │ conversation/       turns, replies, window  │
│ panel (Tk)   │          │        │                                    │
└──────────────┘          │        ▼                                    │
   starts the server      │ models/             Ollama, llama.cpp       │ ──► local model servers
   as a child process     │        │                                    │     (on this PC, keep on localhost)
                          │ store/  SQLite event log  ◄─────────────────┘
                          │ memory/ optional Chroma index ⇄ Ollama embeddings
                          └────────────────────────────────────────────┘
```

## Modules

| Folder / file | Owns |
|---|---|
| `harness.py`, `_HomeAGENT.pyw` | Thin entry points. |
| `app.py` | Assembles everything and holds no behaviour of its own. |
| `config.py`, `locations.py`, `words.py` | Settings, where files live, and the word list for easy-to-type tokens. |
| `store/event_store.py` | The append-only SQLite log. |
| `models/` | Talking to model servers: one HTTP `transport`, a shared `backend` base, one adapter per protocol (`ollama`, `llamacpp`), a `registry` of configured backends, and `errors` (the named failures). |
| `conversation/manager.py` | Conversations and their turns, rebuilt from the log. |
| `conversation/generation.py` | One reply per worker thread, and the first-come queue per model. |
| `conversation/window.py` | Which messages fit in the model's context. |
| `memory/cartridge.py` | Optional Chroma index, reconciled from recorded turns and queried only within the active conversation. |
| `interfaces/web.py`, `page.html` | The HTTP server and the single-page chat. |
| `interfaces/cli.py` | The command line. |
| `interfaces/control.py`, `gui.py` | The control panel: its logic, and its window. |

The code is layered so that each part has one owner. Interfaces use the conversation and model layers; the conversation layer uses the model layer, which uses the transport. Nothing below an interface imports it. Optional Chroma is loaded by name only when memory is enabled. A test (`tests/test_architecture.py`) fails on an import cycle, on core code importing an interface, on any third-party import, and on any module over 400 lines.

## One source of truth: the event log

Everything that happens is appended to a SQLite table (`conversation.created`, `turn.user`, `turn.assistant`, `generation.failed`). Nothing is edited or deleted. Each event also records who caused it: `USER` (a person), `AGENT` (the model's reply) or `SYSTEM` (the server, for example when a reply fails). The set of conversations, their titles and turns, and the last context window are all **rebuilt from the log at startup**. That keeps state simple, makes restarts safe, and means the record of what was said is never lost, even when old messages stop being sent to a model.

When enabled, the memory cartridge indexes completed user and assistant turns as derived data. It uses Ollama's embedding endpoint and a persistent local Chroma collection. Before retrieval, it compares the event log with indexed event IDs and upserts missing turns, so interrupted indexing is repaired. A query is filtered by conversation ID. The index records its schema and embedding model identity; vector dimensions are checked against stored vectors. A mismatch degrades memory and asks the operator to rebuild the index from the event log. Memory failures do not stop chat.

Retrieved excerpts are added only when they fit. If necessary, older recent-context messages are dropped first; the newest user message is retained or the existing clear context-limit failure is returned. Excerpts are marked as quoted context and their source event references are recorded with the reply window. Disable memory in config to detach it; this takes effect after restart.

## Life of a message

1. The page posts the message. The server checks the token and reads the body (bounded) before routing.
2. The conversation manager records the user turn. A conversation can have one reply in flight at a time.
3. A worker thread takes a ticket for the chosen model's queue and waits its turn. Replies to one model run one at a time, first come first served, and waiting clients see their position.
4. The window logic picks the newest messages that fit the model's context (below), and the backend adapter streams the reply.
5. Text is pushed to every attached client as it arrives. When the reply ends, a `turn.assistant` event is recorded. If anything goes wrong, a `generation.failed` event is recorded with the reason and any partial text.

A reply does not depend on any client: if a phone drops off, the reply finishes and is stored, and a reconnecting client is sent a snapshot of the text so far followed by the rest. A slow client is dropped rather than allowed to slow the reply.

## The context window

A model reads a limited number of tokens. The budget for the prompt is `num_ctx` less a 10% margin, less room for the reply (`max_reply_tokens`). Each reply is sent the newest messages that fit, always including the newest user message. If that message alone cannot fit, the reply fails with `context_exceeded` and the model is never called.

Token counts are estimated from characters, then corrected: every reply returns the prompt size the model actually saw, and the estimator moves toward that ratio for that model. A higher characters-per-token ratio (fewer tokens) is believed slowly, so one odd report cannot make later estimates dangerously low. What each reply was sent is stored with it, so the estimator also relearns after a restart. The page shows a meter, and a marker where older messages stopped being sent.

## Failures have names

| Reason | Meaning |
|---|---|
| `unreachable`, `timeout_connect`, `timeout_listing` | The model server could not be reached, or did not answer a short question, in time. |
| `timeout_first_byte`, `timeout_idle`, `deadline` | The model took too long to start, went silent, or ran past its total allowance. |
| `connection_reset`, `incomplete`, `protocol_error` | The stream broke, ended without its final marker, or contained something unexpected. |
| `http_error`, `context_exceeded` | The model server refused the request, or the conversation does not fit its context. |
| `internal_error` | A bug in this server: the reply is ended and recorded as failed instead of being left hanging. |

A reply that ends without the model's final marker is never stored as complete, and a reply stopped by the token cap is marked as cut off.

## The control panel is just another client

The panel starts `harness.py serve` as a child process and talks to it over the server's own HTTP API (`/api/status`, `/api/unload`). It never opens the database. That is why Restart always runs the code on disk, and why a server crash cannot take the panel down.

## Choices worth knowing

- **Standard library only.** Nothing to install, and nothing to keep patched.
- **One process, threads for replies.** A home GPU serves a few people, so a simple threaded server is enough.
- **Plain JavaScript, no build step.** The page is one file, and renders all text as text, never as HTML.
- **Keep backends on localhost.** Only this server needs to be reachable from your network. _HomeAGENT does not change how Ollama or llama.cpp listen (both default to localhost).
