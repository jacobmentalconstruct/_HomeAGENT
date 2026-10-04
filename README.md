# _HomeAGENT

A small, private chat server for local language models.

Run it on the PC that has your GPU, then chat with it from any device on your home network, such as a phone or a laptop, in a plain web page. Models run through [Ollama](https://ollama.com) (the tested path) or a [llama.cpp](https://github.com/ggml-org/llama.cpp) server (supported, but so far tested only against a scripted fake), on the same machine. The program itself never contacts the internet. It needs **only Python's standard library**, so there is nothing to install.

## What you get

- **A chat page that works well on a phone.** Streaming replies, a model dropdown, a list of past conversations, and a meter showing how much of the model's context is in use.
- **A control panel window** (tkinter) to start, stop and restart the server, open the page, copy a login link for your phone, free GPU memory, and watch live traffic.
- **A few controls on the page itself**, in the conversation list: **Free GPU memory** and **Make the selected model the default**.
- **Private by design.** One access token, no accounts, no telemetry, no cloud calls. Conversations stay in a local SQLite file.
- **Long conversations that keep working.** Each reply is sent the newest messages that fit the model's context. Older messages stay in the record and are marked in the page.
- **Shared-GPU friendly.** One reply runs at a time per model, with a visible queue position. A "Free GPU" button unloads models so you can use the GPU for something else.
- **Sturdy.** Every failure has a named reason, a reply carries on if your phone drops off, and conversations survive restarts.

## Requirements

- Python 3.10 or newer (developed on 3.13). No packages to install.
- [Ollama](https://ollama.com) running on the same machine, with at least one chat model pulled (for example `ollama pull qwen3.5:9b`). A llama.cpp server is also supported; see [Configuration](docs/CONFIGURATION.md).
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
- [Configuration](docs/CONFIGURATION.md): every setting
- [HTTP API](docs/API.md): the endpoints the page and panel use
- [Security](docs/SECURITY.md): what it protects, and what it does not

## Tests

```
python -B -m unittest discover -s tests
```

The suite uses scripted fake model servers, so it needs no GPU and no Ollama. It takes a couple of minutes because it exercises real timeouts and starts the real server as a child process.

## License

Released under the MIT License. See [LICENSE.md](LICENSE.md).

## Scope

This is a chat server, and deliberately nothing more. It has no tools, no accounts, and no memory beyond the conversation window. The llama.cpp adapter is covered by tests against a scripted fake server and has not yet been run against a real llama.cpp server. The data lives in `runtime/` next to the program (`config.json` and `harness.sqlite3`); both are created on first run and are ignored by git.
