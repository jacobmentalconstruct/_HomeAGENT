"""Command-line interface: gui, serve, status, models, token, link, unload and smoke."""

from __future__ import annotations

import argparse

from ..app import App, build_app
from .. import __version__
from ..config import ConfigError, update_file, word_token
from ..models.errors import BackendError, UnknownModelChoice
from .control import lan_addresses
from .web import make_server


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a whole number of at least 1")
    return value


def _status(app: App, _args) -> int:
    print(f"version:  {__version__}")
    print(f"config:   {app.locations.config_file}")
    print(f"database: {app.locations.database}")
    print(f"listen:   {app.config.host}:{app.config.port} (token required: {app.config.require_token})")
    print(f"events:   {app.events.count()}")
    return 0


def _models(app: App, _args) -> int:
    entries = app.models.list_models()
    for entry in entries:
        if entry.available:
            print(entry.choice if entry.chat else f"{entry.choice}  (not a chat model)")
        else:
            print(f"{entry.backend_id}: UNAVAILABLE ({entry.reason}) {entry.message}")
    return 0 if any(entry.available for entry in entries) else 1


def _token(app: App, args) -> int:
    if args.words:
        new = word_token()
        update_file(app.locations.config_file, token=new)
        print("New token saved. Restart `serve` for it to apply; every device signs in again "
              "(`python harness.py link` makes this easy).")
        print(new)
        return 0
    print("Anyone with this token can use the agent. Enter it on each device once.")
    print(app.config.token)
    return 0


def _link(app: App, _args) -> int:
    host, port = app.config.host, app.config.port
    addresses = lan_addresses() if host == "0.0.0.0" else [host]
    print("These links contain the access token. Send them only to your own devices.")
    for address in addresses or ["127.0.0.1"]:
        print(f"http://{address}:{port}/#token={app.config.token}")
    return 0


def _serve(app: App, _args) -> int:
    host, port = app.config.host, app.config.port
    try:
        server = make_server(app, host, port, log=lambda line: print(line, flush=True))
    except ConfigError as exc:
        print(f"config error: {exc}")
        return 1
    except OSError as exc:
        print(f"cannot listen on {host}:{port}: {exc}")
        return 1
    addresses = lan_addresses() if host == "0.0.0.0" else []
    print(f"listening on {host}:{port}")
    for address in ["127.0.0.1", *addresses] if host == "0.0.0.0" else [host]:
        print(f"  open http://{address}:{port}/")
    print("token: run `python harness.py token` to show it. Stop with Ctrl+C. "
          "Requests are logged below (never the token or message text).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping")
    finally:
        server.server_close()
    return 0


def _unload(app: App, _args) -> int:
    for backend_id, result in app.models.unload_all().items():
        print(f"{backend_id}: " + (", ".join(result) if isinstance(result, list) and result else
                                   "nothing loaded" if isinstance(result, list) else f"failed ({result})"))
    return 0


def _smoke(app: App, args) -> int:
    try:
        backend, model = app.models.resolve(args.choice)
    except UnknownModelChoice as exc:
        print(f"smoke failed: {exc}")
        return 1
    options = {"max_reply_tokens": args.max_tokens} if args.max_tokens else None
    stream = backend.chat(model, [{"role": "user", "content": args.prompt}], options)
    try:
        for _chunk in stream:
            pass
    except BackendError as exc:
        print(f"smoke failed: {exc.reason}: {exc.message}")
        print(f"partial reply: {exc.partial_text!r}")
        return 1
    summary = stream.summary
    print(f"chunks:        {stream.chunks}")
    print(f"stop_reason:   {summary.stop_reason}")
    print(f"prompt_tokens: {summary.prompt_tokens}")
    print(f"reply_tokens:  {summary.reply_tokens}")
    print(f"reply:         {summary.text!r}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="harness.py")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show config and event log location")
    sub.add_parser("models", help="list models from the configured backends")
    sub.add_parser("serve", help="serve the page and API on the network")
    gui = sub.add_parser("gui", help="open the control panel window (start, stop, free GPU, watch traffic)")
    gui.add_argument("--no-start", action="store_true", help="do not start the server automatically")
    token = sub.add_parser("token", help="show the access token")
    token.add_argument("--words", action="store_true", help="replace it with a new, easy-to-type five-word token")
    sub.add_parser("link", help="show login links that sign a device in without typing the token")
    sub.add_parser("unload", help="free GPU memory by unloading models from the backends")
    smoke = sub.add_parser("smoke", help="diagnostic: stream one reply and print what came back")
    smoke.add_argument("choice", help="backend_id:model, for example ollama:qwen3.5:9b")
    smoke.add_argument("prompt")
    smoke.add_argument("--max-tokens", type=_positive_int, default=None)
    args = parser.parse_args(argv)
    if args.command == "gui":  # a window that runs the server as a child process; it never opens the database
        from .gui import run  # tkinter is only needed for this command

        return run(autostart=not args.no_start)
    try:
        app = build_app()
    except ConfigError as exc:
        print(f"config error: {exc}")
        return 1
    try:
        return {"status": _status, "models": _models, "smoke": _smoke, "serve": _serve,
                                "token": _token, "link": _link, "unload": _unload}[args.command](app, args)
    finally:
        app.close()
