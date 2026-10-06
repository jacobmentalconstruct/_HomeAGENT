# Architecture

_HomeAGENT is one Python process (plus an optional control-panel window). The normal chat path uses the standard library; the memory cartridge prefers Chroma and works without it. This page explains how the pieces fit and why. The Python package is called `agent_harness`, and `harness.py` is its entry point.

The project is developing toward context scaling. Today the generation path selects
recent messages that fit, may add retrieved same-conversation excerpts, and, for one
oversized final message of the shape *document, then `Question:`*, derives a bounded,
source-linked extract (switch: `overflow_fallback`). It does not summarize old
conversation history or route among preprocessing strategies, and no graph is built.
Version 0.2.0 closes this prototype; see the CHANGELOG. See [the project charter](PROJECT-CHARTER.md) for product stop conditions
and [the overflow architecture paper](CONTEXT-OVERFLOW-FALLBACK-ARCHITECTURE.md)
for the originating proposal.

```
 phone / laptop           this PC
┌────────────────┐       ┌──────────────────────────────────────────────────────┐
│ page / panel   │─HTTP─►│ interfaces/web.py: token check and routes            │
└────────────────┘       │ conversation/: turns, replies, window                │
                         │ models/: Ollama and llama.cpp adapters               │
                         │ store/: SQLite event log                             │
                         │ memory/: vector + FTS5 index ⇄ Ollama embeddings     │
                         │ models/ → local model servers                        │
                         └──────────────────────────────────────────────────────┘
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
| `conversation/overflow.py` | The overflow fallback: parse the `Question:` shape, extract source spans, reduce, compose the derived prompt. |
| `conversation/provenance.py` | The prompt compositions and `verify_derived`, a pure check of a derived record against its source. |
| `memory/cartridge.py` | Orchestrates the two memory tiers, reconciled from recorded turns and queried only within the active conversation; owns the status machine. |
| `memory/chroma_store.py`, `memory/sqlite_store.py` | The two interchangeable vector stores. |
| `memory/lexical_store.py` | The FTS5 keyword index: its own file, independent of the vector store. |
| `interfaces/web.py`, `page.html` | The HTTP server and the single-page chat. |
| `interfaces/cli.py` | The command line. |
| `interfaces/control.py`, `gui.py` | The control panel: its logic, and its window. |

The code is layered so that each part has one owner. Interfaces use the conversation and model layers; the conversation layer uses the model layer, which uses the transport. Nothing below an interface imports it. Optional Chroma is loaded by name only when memory is enabled. A test (`tests/test_architecture.py`) fails on an import cycle, on core code importing an interface, on any third-party import, and on any module over 400 lines.

## One source of truth: the event log

Everything that happens is appended to a SQLite table (`conversation.created`, `turn.user`, `turn.assistant`, `generation.failed`). Nothing is edited or deleted. Each event also records who caused it: `USER` (a person), `AGENT` (the model's reply) or `SYSTEM` (the server, for example when a reply fails). The set of conversations, their titles and turns, and the last context window are all **rebuilt from the log at startup**. That keeps state simple, makes restarts safe, and means the record of what was said is never lost, even when old messages stop being sent to a model. When the overflow fallback is used, the derived text and its source ranges are stored with the reply that used them (the `turn.assistant` event's window record), in plaintext; the original `turn.user` event is never changed.

The memory cartridge is enabled by default and indexes completed user and assistant turns as derived data. It has two retrieval tiers:

- **Vector tier**: uses Ollama embeddings and a Chroma (preferred) or SQLite dot-product store. Fast semantic similarity. Requires the embedding model to be available.
- **Lexical tier (FTS5)**: SQLite full-text search with BM25 ranking in its own file (`lexical.sqlite3`). No extra packages. It is opened and reconciled whenever memory is enabled, for every vector store, and serves whenever the vector tier cannot.

Only the server process opens the memory stores (`build_app(with_memory=True)`, used by `serve`); other commands build the app without them. Indexing happens in the background after each reply and at startup. A bounded batch prevents the first reply from stalling on a large backlog (`RECONCILE_BATCH` events per retrieve call). Before retrieval, missing turns are indexed from the event log so interrupted indexing is repaired. Queries are filtered by conversation ID.

The index records its schema and embedding model identity; vector dimensions are checked against stored vectors. A mismatch raises a hard error and asks the operator to rebuild the index. Memory failures do not stop chat.

**Status machine.** The cartridge reports `state` (`ready`, `degraded`, `disabled`), `tier` (`vector`, `lexical`, `none`), `reason` (machine-readable, see CONFIGURATION), and `fix` (human text). `ready` with a `lexical` tier means the vector tier cannot serve (missing model or backend, an embedding error, an incompatible index) but the keyword tier is. An embedding error never degrades memory: it is a tier fault. The vector tier is skipped while it backs off and is probed again on a background thread after 5 s, then 10 s, 20 s and so on up to 300 s, with at most one probe in flight and one embedding call per probe; a reply never waits on a failing embedder after the first failure. A successful probe clears the fault and catches up the index. `degraded` means no tier works; replies where every tier failed are counted in `failed_retrievals` and described in `last_error`.

Retrieved excerpts are added only when they fit. If necessary, older recent-context messages are dropped first; the newest user message is retained or the existing clear context-limit failure is returned. Excerpts are marked as quoted context and their source event references are recorded with the reply window. Disable memory in config to detach it; this takes effect after restart.

## Life of a message

1. The page posts the message. The server checks the token and reads the body (bounded) before routing.
2. The conversation manager records the user turn. A conversation can have one reply in flight at a time.
3. A worker thread takes a ticket for the chosen model's queue and waits its turn. Replies to one model run one at a time, first come first served, and waiting clients see their position.
4. The window logic picks the newest messages that fit the model's context (below). When the conversation memory cartridge is enabled, it retrieves older turns from that conversation and adds excerpts that fit. The backend adapter then streams the reply.
5. Text is pushed to every attached client as it arrives. When the reply ends, a `turn.assistant` event is recorded. If anything goes wrong, a `generation.failed` event is recorded with the reason and any partial text.

A reply does not depend on any client: if a phone drops off, the reply finishes and is stored, and a reconnecting client is sent a snapshot of the text so far followed by the rest. A slow client is dropped rather than allowed to slow the reply.

## The context window

A model reads a limited number of tokens. The budget for the prompt is `num_ctx` less a 10% margin, less room for the reply (`max_reply_tokens`). Each reply is sent the newest messages that fit, always including the newest user message. If that message alone cannot fit, the overflow fallback handles it when it has the supported shape; otherwise the reply fails with `context_exceeded` and the model is never called. How large a message can be at each `num_ctx` is in CONFIGURATION, "Size limits for one message".

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

- **Dependency policy.** Third-party dependencies are welcome when each has: (1) a runtime dynamic import, never a static one; (2) a stdlib or alternative backup path; (3) an actionable status reason and fix text; (4) tests with the dependency absent and present. The core chat path has no hard third-party import. Conversation memory degrades through backup tiers rather than failing completely; see *Dependency policy* below.
- **One process, threads for replies.** A home GPU serves a few people, so a simple threaded server is enough.
- **Plain JavaScript, no build step.** The page is one file, and renders all text as text, never as HTML.
- **Keep backends on localhost.** Only this server needs to be reachable from your network. _HomeAGENT does not change how Ollama or llama.cpp listen (both default to localhost).

## Dependency policy

Third-party dependencies are welcome when each meets all four conditions: a runtime dynamic
import (never a static import at module level), a stdlib or alternative backup path, an
actionable status reason with fix text shown to the operator, and tests that run with the
dependency both absent and present. The core chat path must have no hard third-party import.

Optional components degrade through backup tiers rather than to a dead feature. Using a backup
tier is state `ready` with a reported store and reason, not `degraded`. `degraded` means every
tier failed.

### External dependencies and their backups

| Dependency | Used for | Backup when absent or failing | Absent-case test |
|---|---|---|---|
| Chroma (`chromadb`) | preferred vector store | SQLite vectors (status says `chroma unavailable ... using sqlite fallback`); with `memory.strict`, no vector store and the keyword tier serves | `AbsentDependencyTests.test_chroma_absent_falls_back_to_sqlite_vectors` |
| Embeddings (Ollama embedding model) | the vector tier of memory | FTS5 keyword search, a separate index that is always kept; status says why and how to fix it | `AbsentDependencyTests.test_embeddings_absent_falls_back_to_keyword_search` |
| Ollama (chat) | answering | the llama.cpp adapter, when a llama.cpp backend is configured; an unreachable backend is listed with its reason and the others keep working | `AbsentDependencyTests.test_ollama_unreachable_llamacpp_backend_still_chats` |
| `nvidia-smi` | GPU memory figure in the control panel | the panel shows nothing ("not available"); nothing else changes | `AbsentDependencyTests.test_nvidia_smi_absent_shows_nothing` |
| tkinter | the control panel window | CLI and server: `python harness.py serve`; the `gui` command says so instead of failing | `AbsentDependencyTests.test_tkinter_absent_cli_and_server_paths_still_work` |

The absent-dependency pattern is one mechanism with two entry points, both in `tests/support.py`:
`with blocked_modules("name"):` for one test, and `AGENT_HARNESS_BLOCK_MODULES=name` for a whole run or
a subprocess. Both make the module raise a real `ModuleNotFoundError`. The full suite is run with
`chromadb` present and with `AGENT_HARNESS_BLOCK_MODULES=chromadb`.

## Prompt composition for oversized messages

The derived prompt is the kept start and end of the document, the marked derived block, and the question, which is always last. Three compositions exist (`conversation/provenance.py`): `baseline` (10% of the prompt budget kept from each end; head, derived block, tail, question), `small_ends` (5% from each end; same order) and `block_by_question` (10%; head, tail, derived block, question). They were measured on five local models and eight fixtures (`docs/EVAL-RESULTS.md`, raw data `docs/eval-results.json`, reproduce with `python -B -m tests.eval.runner`). `small_ends` is the default because the pre-declared winner rule (fixed in PLAN.md before the run) picked it on a near-tie: all three variants met the same two thresholds. The margin is thin: against `baseline` it had one more correct answer and one more extraction pass out of 120 cells, and made 19 more model calls, from one run per cell. The composition is a constant, not a config key, and the derived record names the one that was used (`composition`, and a `role` on each source) so `verify_derived` can check any of them.

## Known limits

- **llama.cpp.** The adapter is covered by tests against a scripted fake server and has not been run against a real llama.cpp server. The reactive context retry (re-running a request through the fallback after the backend rejects it as too long) is Ollama-only; with llama.cpp only the preflight size check can trigger the fallback.
- **Snapping granularity.** Kept source spans are widened to the enclosing line or sentence, so a kept span can be larger than the answer. Sentences are split by a simple pattern that does not understand abbreviations.
- **Chunk and call caps.** At most eight chunks per extraction or reduction pass. Chunks overlap by about 12%, and each overlapped chunk counts toward the eight, so a document only a little over the limit can still fail. All passes share one model-call cap (16) and the generation deadline; reduction recurses at most four times. Over any cap, the reply fails with `context_exceeded`.
- **Follow-ups after a fallback reply.** Follow-up questions do not see the document or anything older than it. Each reply is sent the newest messages that fit, as one unbroken run, and the oversized message never fits, so the run ends at it; the derived text is not reused either. Retrieval may help: with memory on, older turns can come back as excerpts. But memory indexes whole turns, so in the vector tier a long turn is embedded from its first part only (Ollama cuts the input to the embedding model's context; the keyword index keeps all of it), and a retrieved turn is only added whole, so the document itself cannot be injected when it does not fit. To ask more about the document, send it again with the new question.
- **Input shape.** Only a single oversized final user message that ends with a `Question:` section is supported. The fallback does not infer instructions from other messages or read file formats.
- **Small models in the extraction step.** In the T5 eval (one run per cell, temperature 0, `num_ctx` 2048) the answer sentence reached the derived text in every fixture only for the 4B and 9B models. Under the default composition qwen2.5:1.5b and qwen3.5:2b each missed one fixture of eight (1.5b: nothing matched near the head/tail boundary, so the reply failed visibly; 2b: the single unpunctuated paragraph, which took 16 model calls) and qwen2.5:0.5b reached it in four of eight. The exit thresholds "100% for models of 1.5B and up" and "7/8 for 0.5B" were therefore missed and are recorded as named limitations, not tuned away. Final-answer correctness met its threshold for the 4B and 9B models (8/8 each), and the absent-fact fixture failed visibly for every model.
- **Silent wrong answers from small models.** Small models can answer wrongly without any warning. When extraction finds some passages but not the answer, the reply still completes normally, and the model answers confidently from what it was given. In the eval this happened in four cells under the default composition: qwen2.5:0.5b on `unpunctuated_text` (answered "121.5 MHz"), qwen2.5:0.5b on `two_facts` (gave one of the two keys and said the other was not in the context), qwen3.5:2b on `unpunctuated_text` (answered "147.000") and qwen3.5:2b on `wrapped_text` (answered "04:30 sharp" when the asked-for day was "the third Thursday"; here extraction had found the answer, and the model answered only part of it). The `Derived context` block on the page shows what the model was given, which is the only signal. Use a model of 4B or larger for oversized messages; see [EVAL-RESULTS.md](EVAL-RESULTS.md), "Silent wrong answers".
- **Size ceilings.** The 20,000-character message cap, the prompt budget and the chunk cap together decide when the fallback can run; at `num_ctx` 8,192 with a 256-token reply, or 16,384, it is never reached from the page. See CONFIGURATION, "Size limits for one message".
- **Unpunctuated text and wrapped sentences.** One long paragraph with no punctuation is split at word boundaries, so a short fact can be cut across two chunks; a sentence hard-wrapped over two lines is two source units and both must be copied. These were the fixtures small models missed most.
- **Memory.** Retrieval is limited to the active conversation. While the startup catch-up is still indexing, retrieval uses what is indexed so far, and a turn finished during the catch-up may reach the keyword index only when it ends.
