# Configuration

Settings live in `runtime/config.json`, created on first run with defaults and a random access token. Edit it with any text editor, then restart the server (the control panel's **Restart** button does this). Keys you leave out take their defaults, and keys the program does not know are kept untouched.

If a value is invalid, the server refuses to start and says which one. (`keep_alive` is passed to Ollama as written, so Ollama judges it.) The file is written with every setting the first time the program runs, so a later version's new defaults do not change an existing file; delete a key to get its default back.

Ollama chat requests set `truncate=false`, so Ollama rejects rather than silently dropping content if a request exceeds the model context. The harness selects recent context within its own prompt budget and applies the bounded T1 fallback to supported oversized newest messages. Other oversized message shapes fail visibly. A request that fits the harness budget is sent normally.

## Settings

| Key | Default | Meaning |
|---|---|---|
| `host` | `"0.0.0.0"` | Address to listen on. `0.0.0.0` means every network interface (your home network). `"127.0.0.1"` means this computer only. |
| `port` | `8765` | Port to listen on (1 to 65535). |
| `require_token` | `true` | Require the access token. Turning it off is only allowed when `host` is `127.0.0.1` or `localhost`; the server refuses to start otherwise. |
| `token` | generated | The shared access token: text of at least 16 characters. If the key is missing or blank, a new one is generated and saved. |
| `backends` | one Ollama entry | Model servers to use; see below. |
| `timeouts` | see below | How long to wait at each stage, in seconds. |
| `num_ctx` | `8192` | The context size, in tokens, sent to Ollama and used to size the window. Raise it for longer memory, at the cost of GPU memory. |
| `max_reply_tokens` | `2048` | The longest reply allowed. It must leave the prompt room: at most `num_ctx` x 0.9 - 256. Replies that hit it are marked as cut off. |
| `default_model` | `"ollama:qwen3.5:9b"` | The model new devices start on, as `backend_id:model`. You can also set it from the page. If it is not installed, the page uses the first chat model it finds. |
| `system_prompt` | a short, honest-assistant prompt | The instruction sent ahead of every conversation. |
| `keep_alive` | `"3m"` | How long Ollama keeps a model in GPU memory after its last reply. A shorter value, such as `"1m"`, frees the GPU sooner. |
| `overflow_fallback` | `true` | When one message is too big for the model, find the passages that answer its final `Question:` line and send those instead (see the README). `false`: the message fails with the plain `context_exceeded` message, and a backend context error is not retried. Restart after changing it. |
| `memory` | enabled | Local retrieval cartridge; enabled by default on new installs. See below. |

## Conversation memory

Memory is enabled by default on new installs. To use vector recall, pull an Ollama embedding model (`ollama pull nomic-embed-text`); the server detects it automatically. Without it, memory still works through the keyword (FTS5) tier, with weaker recall of reworded questions. To disable memory entirely, set `"enabled": false` and restart.

```json
"memory": {
  "enabled": true,
  "embedding_backend": "ollama",
  "embedding_model": "nomic-embed-text",
  "top_k": 4
}
```

**Tiers.** Memory uses two retrieval tiers in order of preference:

1. **Vector tier** (Chroma or SQLite dot-product): semantic similarity using Ollama embeddings. Requires the embedding model. Chroma is recommended (`python -m pip install -r requirements.txt`); without it the SQLite vector store is used instead.
2. **Lexical tier** (FTS5 BM25): keyword matching with SQLite's built-in full-text search and no extra packages. It is a separate index (`runtime/memory/lexical.sqlite3`), opened and kept up to date whenever memory is enabled, whichever vector store is in use. It serves when the vector tier cannot: embedding model missing, an embedding error, an incompatible index, or no embedding backend. Results carry `"method": "lexical"`.

Only the server process (`harness.py serve`) opens the memory stores or indexes anything. `status`, `models`, `token`, `link`, `unload` and `smoke` never touch them, and `harness.py status` reports the memory configuration from the config file alone.

A schema or identity mismatch never triggers the SQLite vector fallback: the vector tier is refused (reason `index_incompatible`), the keyword tier keeps serving, and removing `runtime/memory/` rebuilds the vector index.

| Memory key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Attach the conversation memory cartridge; restart after changing it. |
| `store` | `"chroma"` | Preferred vector store: `"chroma"` or `"sqlite"`. |
| `strict` | `false` | When `false`, a Chroma failure falls back to the SQLite vector store automatically. When `true`, there is no SQLite vector fallback: the vector tier is reported unavailable (`vector_store_unavailable`) and the keyword tier serves. |
| `embedding_backend` | `"ollama"` | ID of a configured Ollama backend used to make embeddings. If the default `ollama` is not configured, memory runs on the keyword tier and says why (`embedding_backend_missing`); a name you set that is not configured, or is not an Ollama backend, is a config error. |
| `embedding_model` | `"nomic-embed-text"` | Name of the Ollama embedding model to pull and use. |
| `top_k` | `4` | Number of older matches requested per reply, from 1 to 20. |

### Memory status

The `/api/status` endpoint and each reply's `window.memory` field report memory state:

| Field | Values | Meaning |
|---|---|---|
| `state` | `ready`, `degraded`, `disabled` | `ready`: at least one tier works, including when only the keyword tier does. `degraded`: no tier works. `disabled`: `memory.enabled` is `false` in config. |
| `tier` | `vector`, `lexical`, `none` | The tier retrieval is using now. `none` only when degraded. It follows what actually served the last retrieval, not a startup guess. |
| `reason` | `""`, `embedding_model_missing`, `embedding_unavailable`, `embedding_backend_missing`, `index_incompatible`, `vector_store_unavailable`, `lexical_unavailable`, `transient`, `all_tiers_failed` | Machine-readable cause when not fully healthy. |
| `fix` | human text or `""` | What to do, for example `run: ollama pull nomic-embed-text`. |
| `retry_in_seconds`, `probe_failures` | seconds, count | While the vector tier is backing off: seconds until the next probe (0 when due or healthy) and consecutive failed probes. |
| `failed_retrievals`, `last_error` | count, text | Replies where every tier failed and nothing could be retrieved. The page and `/api/status` show these instead of silently returning nothing. |

An embedding failure is never a degrade: it moves retrieval to the keyword tier, and memory recovers by itself once Ollama or the model is back. Recovery is a bounded re-probe: the vector tier is skipped while it backs off, then probed on a background thread after 5 s, 10 s, 20 s and so on, never more than 300 s apart, with one probe at a time and one embedding call per probe. `retry_in_seconds` and `probe_failures` in the status show where it stands. Replies never wait on a failing embedder after the first failure. Ollama model names are matched with a missing tag read as `:latest`, so `nomic-embed-text` finds `nomic-embed-text:latest`.

**SQLite store practical scale (768-dim vectors, this machine, 2026-10-05):**

| Indexed vectors | Query time |
|---|---|
| 1 000 | ~58 ms |
| 5 000 | ~290 ms |
| 20 000 | ~1 160 ms |

An index on `conversation_id` limits a query to the active conversation's vectors, and every one of those is scanned (no vector index); time scales linearly with count and dimension. At 5 000 vectors, query time is ~290 ms per reply; beyond that, Chroma is preferable for latency-sensitive use. The SQLite store is suitable as a fallback tier at home-assistant scale (up to a few thousand indexed turns).

Restart the server after changing this setting. The cartridge stores a persistent index in `runtime/memory/`; the conversation event log remains authoritative and missing entries are indexed from it before retrieval. Retrieval is limited to the active conversation. The status endpoint reports memory state, the active tier and store, and any reason and fix. If the embedding model changes, stop the server and remove `runtime/memory/` to rebuild vectors with a consistent model. The original conversation history remains in `runtime/harness.sqlite3`.

If a model is re-pulled or replaced under the same name, the cartridge detects the change only when its vector dimensions differ. Rebuild `runtime/memory/` manually if the model's embeddings changed without a name or dimension change.

Indexing adds local embedding work and disk use. Chroma's persistent local client and the SQLite store are both suitable for single-process prototype use; neither is a multi-process or networked store.

## Backends

```json
"backends": [
  {"id": "ollama", "kind": "ollama",   "url": "http://127.0.0.1:11434"},
  {"id": "cpp",    "kind": "llamacpp", "url": "http://127.0.0.1:8080"}
]
```

- `id` is a short name (lowercase letters, digits, `_` and `-`; unique). Models are shown as `id:model`, for example `ollama:qwen3.5:9b`.
- `kind` is `ollama` or `llamacpp`.
- `url` is the server's root address, with no path.
- Keep backends on `127.0.0.1`. Only this server should be reachable from your network.

A llama.cpp server hosts one model, fixed when you start it, so its context size is set on that server. `num_ctx` still sizes the window, so keep the two in agreement. Ollama's `keep_alive` and the Free GPU button apply to Ollama only.

## Timeouts

| Key | Default | Waiting for |
|---|---|---|
| `connect` | `5` | A connection to the model server. |
| `listing` | `10` | Short calls to a model server: listing models, checking what is loaded, and unloading (includes connecting). |
| `first_byte` | `180` | The first word of a reply. Large models can take a while to load. |
| `idle` | `60` | The next piece of a reply, once it has started. |
| `total` | `900` | The whole reply. |

## Changing the token

- `python harness.py token` shows it.
- `python harness.py token --words` replaces it with five easy words, such as `maple-river-lantern-quartz-ember`, which is far easier to type on a phone. Restart the server afterwards; every device then signs in again (`python harness.py link` prints login links).
- Or set `token` yourself in the file. It must be at least 16 characters.

## Where data lives

`runtime/config.json` holds the settings and token. `runtime/harness.sqlite3` holds every conversation. `runtime/memory/` holds the memory cartridge's derived indexes (the vector store and `lexical.sqlite3`), including a plaintext copy of indexed conversation turns. Runtime data is ignored by git; back up the event log and config if you need to preserve conversations and access settings. The memory index can be rebuilt from the event log.
