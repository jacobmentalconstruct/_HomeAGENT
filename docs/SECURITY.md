# Security

_HomeAGENT is built for a home network you trust. This page says what it protects, what it does not, and how to run it safely.

## What it is designed to protect

- **Only people with the token can use it.** Every API request needs the token. It is compared in constant time, never written to the access log, and never placed in a URL that the server sees.
- **Your models stay off the network.** Ollama and llama.cpp listen on `127.0.0.1` by default, and _HomeAGENT never asks them to do otherwise, so the only thing reachable from your network is this server. If you change how they listen, keeping them private is up to you.
- **Your conversations stay on your machine.** They are stored in a local SQLite file. The memory cartridge (enabled by default) also stores indexed conversation text in plaintext in `runtime/memory/` — both in the vector store and in the FTS5 table. The program makes no calls to the internet; Chroma telemetry is explicitly disabled.
- **Model output cannot attack your browser.** The page shows all text as text and never as HTML.
- **A misbehaving client cannot easily hurt the server.** Request bodies are capped at 1 MB, connections are capped, slow or silent clients time out, and the server refuses to start with the token turned off while listening beyond your own computer.
- **The access log is safe to share.** It records time, client address, method, path, status and duration. It never records the token, headers or message text, and it strips control characters from anything a client sent.

## What it does not protect against

- **Eavesdropping on your network.** The connection is plain HTTP, not HTTPS. Anyone who can watch traffic on your Wi-Fi or router could read the token and the conversations. If you do not trust everyone on that network, do not use it, or put it behind a VPN.
- **A stolen token.** There are no accounts and no per-device tokens. Whoever holds the token can read every conversation, send messages using your GPU, change the default model and unload models. They cannot run code or read files, because the program has no such feature. If a token leaks, replace it: `python harness.py token --words`, then restart.
- **Anyone using a signed-in browser.** The page remembers the token in that browser's local storage. Clear the site's data to sign out; anyone who can use that browser profile can use the agent.
- **The internet.** Never forward its port on your router. It has no rate limiting, no lockout, and no encryption.

## Running it safely

1. Keep the token on (`require_token` is on by default).
2. Allow the port through your firewall only from your own network, for example (Windows, administrator PowerShell):

   ```powershell
   New-NetFirewallRule -DisplayName "_HomeAGENT (8765)" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Any -RemoteAddress LocalSubnet
   ```
3. Treat login links (`python harness.py link`) like passwords: they contain the token. Send them only to your own devices. The token sits after a `#`, which browsers never send to the server, and the page removes it from the address bar as soon as it loads.
4. Use `host: "127.0.0.1"` if you only need it on one computer.
5. Do not commit `runtime/` to a public repository: it holds your token and conversations. The included `.gitignore` already excludes it.

## Reporting a problem

If you find a security issue, please use this repository's private vulnerability reporting (the Security tab on GitHub) rather than a public issue. This route requires private vulnerability reporting to be enabled in GitHub repository settings; it was enabled and checked on 2026-10-04.
