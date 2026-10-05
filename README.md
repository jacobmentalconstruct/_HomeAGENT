# _HomeAGENT

A local chat harness for experimenting with context scaling around language models.

Run it on the PC that has your GPU, then chat with it from any device on your home network, such as a phone or a laptop, in a plain web page. Models run through [Ollama](https://ollama.com) (the tested path) or a [llama.cpp](https://github.com/ggml-org/llama.cpp) server (supported, but so far tested only against a scripted fake), on the same machine. The program itself never contacts the internet. Ordinary chat needs **only Python's standard library**. The optional conversation memory cartridge needs Chroma; see [Configuration](docs/CONFIGURATION.md).

## What you get

- **A chat page that works well on a phone.** Streaming replies, a model dropdown, a list of past conversations, and a meter showing how much of the model's context is in use.
- **A control panel window** (tkinter) to start, stop and restart the server, open the page, copy a login link for your phone, free GPU memory, and watch live traffic.
- **A few controls on the page itself**, in the conversation list: **Free GPU memory** and **Make the selected model the default**.
- **Private by design.** One access token, no accounts, no telemetry, no cloud calls. Conversations stay in a local SQLite file.
- **Long conversations that keep working.** Each reply is sent the newest messages that fit the model's context. Older messages stay in the record and are marked in the page.
- **Conversation recall, on by default.** The memory cartridge retrieves relevant older turns from the active conversation. It uses a two-tier index: a Chroma vector store (preferred) and an FTS5 lexical store as a no-install fallback. Pull an Ollama embedding model to activate it; see [Configuration](docs/CONFIGURATION.md).
- **Shared-GPU friendly.** One reply runs at a time per model, with a visible queue position. A "Free GPU" button unloads models so you can use the GPU for something else.
- **Sturdy.** Every failure has a named reason, a reply carries on if your phone drops off, and conversations survive restarts.

## Requirements

- Python 3.10 or newer (developed on 3.13). No packages to install for ordinary chat or for the FTS5 lexical memory tier.
- [Ollama](https://ollama.com) running on the same machine, with at least one chat model pulled (for example `ollama pull qwen3.5:9b`). A llama.cpp server is also supported; see [Configuration](docs/CONFIGURATION.md).
- For the full vector memory tier: `python -m pip install -r requirements.txt` installs Chroma (recommended). Without it memory uses a SQLite vector store, and without embeddings it uses keyword search.
- Developed and tested on Windows 10 with an NVIDIA GPU. The server and page use only portable standard-library code. The control panel needs tkinter, which the standard Python installer for Windows includes.

## Quick start

Download or clone this repository and open a terminal in its folder, then:

1. Make sure Ollama is running.
2. **Double-click `_HomeAGENT.pyw`** (or run `python harness.py gui`). The control panel opens and starts the server.
3. Click **Open page**. It opens the chat already signed in.

To use it from a phone on the same Wi-Fi:

1. In the panel, click **Copy phone link**, and send that link to your phone over a channel you trust (a note-to-self works). It contains your access token, so send it only to your own devices.
2. Open the link on the phone. It signs in and removes the token from the address bar.
3. If the phone cannot connect, your computer's firewall is probably blocking the port. On Windows, run this once in an administrator PowerShell. It allows port 8765 only from your own network:

```powershell
New-NetFirewallRule -DisplayName "_HomeAGENT (8765)" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Any -RemoteAddress LocalSubnet
```

No panel? Run the server directly with `python harness.py serve`, and read the address it prints.

## The control panel

| Button | What it does |
|---|---|
| Start / Stop / Restart | Runs the server as a child process. Restart loads the code on disk again. |
| Open page | Opens the chat in your browser, signed in. |
| Copy phone link | Copies a login link using your computer's network address. |
| Copy token | Copies the access token. |
| Free GPU | Unloads models from GPU memory. Works even when the server is stopped. |

The window also shows whether the server is running, which models are in GPU memory, GPU memory used (if `nvidia-smi` is available), replies in progress, requests in the last minute, how many devices are connecting, and a live traffic log with failures in red. Closing the window stops the server.

## Command line

```
python harness.py gui [--no-start]      open the control panel
python harness.py serve                 run the server in this console
python harness.py status                show where the config and data live
python harness.py models                list models from the configured backends
python harness.py token [--words]       show the access token, or replace it with an easy-to-type one
python harness.py link                  print login links for your devices
python harness.py unload                free GPU memory
python harness.py smoke <backend:model> "<prompt>" [--max-tokens N]
                                        stream one reply and print how it went (a diagnostic)
```

## How long conversations are handled

A model can only read so much at once (its context). Each reply is sent the newest messages that fit, using a token estimate that corrects itself from the counts the model reports back. A message that is too long to fit fails with a clear error instead of being silently cut. Nothing is ever deleted: older messages stay in the record, and the page marks where they stopped being sent. See [Architecture](docs/ARCHITECTURE.md).

## Security in short

The server uses plain HTTP with one shared token. That is reasonable on a home network you trust, and it is **not** meant to be exposed to the internet. Do not forward its port on your router. Read [Security](docs/SECURITY.md) before changing the defaults.

## Documentation

- [Architecture](docs/ARCHITECTURE.md): how it is built and why
- [Project charter](docs/PROJECT-CHARTER.md): context-scaling purpose, invariants, and prototype stop conditions
- [Configuration](docs/CONFIGURATION.md): every setting
- [HTTP API](docs/API.md): the endpoints the page and panel use
- [Security](docs/SECURITY.md): what it protects, and what it does not
- [Memory watchlist](docs/MEMORY_WATCHLIST.md): retrieval observations to revisit when symptoms appear

## Tests

```
python -B -m unittest discover -s tests
```

The suite uses scripted fake model servers and a fake memory store, so it needs no GPU, Ollama, or Chroma. It runs in two modes automatically: with and without Chroma installed. It takes a couple of minutes because it exercises real timeouts and starts the real server as a child process.

## License

Released under the MIT License. See [LICENSE.md](LICENSE.md).

## Current implementation and project direction

The current implementation provides authenticated local chat, a bounded recent-message window, and optional same-conversation retrieval from a Chroma index derived from recorded turns. It does not yet perform overflow summarization or choose among multiple preprocessing strategies. The project direction is to test a small, source-traceable context-overflow fallback in the existing generation path, then stop and assess evidence before adding other transformations or routes. See [Project charter](docs/PROJECT-CHARTER.md) and [Project plan](PLAN.md).

The llama.cpp adapter is covered by tests against a scripted fake server and has not yet been run against a real llama.cpp server. Runtime files live in `runtime/` next to the program (`config.json`, `harness.sqlite3`, and, when enabled, `memory/`); they contain local settings and conversation data and are ignored by Git.
