# Configuration

Settings live in `runtime/config.json`, created on first run with defaults and a random access token. Edit it with any text editor, then restart the server (the control panel's **Restart** button does this). Keys you leave out take their defaults, and keys the program does not know are kept untouched.

If a value is invalid, the server refuses to start and says which one. (`keep_alive` is passed to Ollama as written, so Ollama judges it.) The file is written with every setting the first time the program runs, so a later version's new defaults do not change an existing file; delete a key to get its default back.

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

`runtime/config.json` holds the settings and token. `runtime/harness.sqlite3` holds every conversation. Both are created on first run and ignored by git. Back them up, or delete them, as you like.
