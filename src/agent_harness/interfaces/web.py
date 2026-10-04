"""Browser adapter: a small JSON API and the page. It translates requests; it owns no domain logic."""

from __future__ import annotations

import hmac
import json
import queue
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..app import App
from ..config import MIN_TOKEN, ConfigError
from ..conversation.manager import Busy
from ..models.errors import BackendError, UnknownModelChoice

MAX_BODY = 1_000_000
DRAIN_LIMIT = 65_536  # a refused request's body is read and thrown away up to this size
MAX_TEXT = 20_000
PING_SECONDS = 15
SOCKET_TIMEOUT = 10  # also bounds how long an unauthenticated client can hold a handler
LOOPBACK = ("127.0.0.1", "localhost")
PAGE = Path(__file__).with_name("page.html")

# Every /api route, so a test can prove each one demands the token.
ROUTES = [  # (method, path pattern, handler name)
    ("GET", re.compile(r"/api/models"), "models"),
    ("GET", re.compile(r"/api/conversations"), "conversation_list"),
    ("POST", re.compile(r"/api/conversations"), "conversation_create"),
    ("GET", re.compile(r"/api/conversations/(?P<id>[0-9a-f]+)"), "conversation_get"),
    ("POST", re.compile(r"/api/conversations/(?P<id>[0-9a-f]+)/messages"), "message_send"),
    ("GET", re.compile(r"/api/generations/(?P<id>[0-9a-f]+)/stream"), "generation_stream"),
    ("POST", re.compile(r"/api/unload"), "unload"),
    ("POST", re.compile(r"/api/default"), "default_set"),
    ("GET", re.compile(r"/api/status"), "status"),
]


def log_text(text: str, limit: int) -> str:
    """Anything a client sent that may appear in the log: printable characters only, bounded length."""
    return re.sub(r"[^\x20-\x7e]", "?", text)[:limit]


def log_path(path: str) -> str:
    """The path as logged: no query string."""
    return log_text(path.split("?", 1)[0], 120)


def stream_messages(gen, snapshot: dict, q: queue.Queue, ping_seconds: float = PING_SECONDS, poll: float = 1.0):
    """Everything a client should see for one reply, ending when the reply ends.

    A client dropped for being too slow never gets the end marker, so once the reply has finished and
    its queue is empty it is sent the final state instead of being left waiting."""
    yield snapshot
    if snapshot["state"] not in ("queued", "running"):
        return
    quiet = 0.0
    while True:
        try:
            message = q.get(timeout=poll)
        except queue.Empty:
            if gen.finished.is_set():
                yield gen.snapshot()
                return
            quiet += poll
            if quiet >= ping_seconds:  # also notices a client that has gone away
                quiet = 0.0
                yield {"type": "ping"}
            continue
        if message is None:
            return
        quiet = 0.0
        yield message


def check_exposure(host: str, require_token: bool) -> None:
    """Refuse to serve an open API to the network."""
    if not require_token and host not in LOOPBACK:
        raise ConfigError(f"'require_token' is off but host is {host!r}. Turn the token on, or set host to 127.0.0.1.")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 32

    def handle_error(self, request, client_address):
        pass  # a client that vanishes mid-write is normal


def make_server(app: App, host: str, port: int, max_handlers: int = 64, log=None) -> ThreadingHTTPServer:
    """`log`, if given, receives one line per request: time, client, method, path, status, milliseconds.

    It never sees headers or bodies, so the token and message text cannot reach it."""
    check_exposure(host, app.config.require_token)
    if app.config.require_token and len(app.config.token) < MIN_TOKEN:  # fail closed, whatever loaded the config
        raise ConfigError(f"The access token is shorter than {MIN_TOKEN} characters; refusing to serve.")
    slots = threading.BoundedSemaphore(max_handlers)
    started = time.time()
    token = app.config.token.encode("utf-8")
    require_token = app.config.require_token

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # a streamed body simply ends when the connection closes
        timeout = SOCKET_TIMEOUT

        def log_message(self, *args):
            pass

        def log_request(self, code="-", size="-"):
            if log is not None:
                started = getattr(self, "_started", time.monotonic())
                # a request rejected before it was parsed has no command or path yet
                method = log_text(str(getattr(self, "command", None) or "-"), 16)
                log(f"{time.strftime('%H:%M:%S')} {self.client_address[0]} {method} "
                    f"{log_path(str(getattr(self, 'path', '-')))} {code} "
                    f"{int((time.monotonic() - started) * 1000)}ms")

        def handle(self):
            if not slots.acquire(blocking=False):
                self._busy()
                return
            try:
                super().handle()
            finally:
                slots.release()

        def _busy(self) -> None:
            """Too many connections: answer 503, then drain the request so closing does not reset it."""
            if log is not None:
                log(f"{time.strftime('%H:%M:%S')} {self.client_address[0]} - - 503 busy")
            try:
                self.wfile.write(b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_WR)
                self.connection.settimeout(0.5)
                self.connection.recv(65536)
            except OSError:
                pass

        # -- helpers --------------------------------------------------------

        def _json(self, code: int, body: object) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            if not require_token:
                return True
            header = self.headers.get("Authorization", "")
            given = header[7:] if header[:7].lower() == "bearer " else ""
            return hmac.compare_digest(given.encode("latin-1", "replace"), token)

        def _drain(self) -> None:
            """Read and discard the body of a request about to be refused. Closing a connection that still holds
            unread data can reset it under the answer on Windows, and the client then never sees the answer."""
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if 0 < length <= DRAIN_LIMIT:
                    self.rfile.read(length)
            except (ValueError, OSError):
                pass

        def _read_raw(self) -> bytes | None:
            """The request body, bounded and always read in full, so no handler can leave bytes unread.
            Answers 411 or 413 and returns None when it cannot be accepted."""
            header = self.headers.get("Content-Length")
            if header is None:
                return b""
            try:
                length = int(header)
            except ValueError:
                self._json(411, {"error": "Content-Length is required"})
                return None
            if length < 0 or length > MAX_BODY:
                self._json(413, {"error": "request body too large"})
                return None
            return self.rfile.read(length) if length else b""

        def _body(self) -> dict | None:
            """The body as a JSON object, or answer 400 or 411 and return None."""
            if self.headers.get("Content-Length") is None:
                self._json(411, {"error": "Content-Length is required"})
                return None
            try:
                body = json.loads(self._raw or b"null")
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(400, {"error": "body is not valid JSON"})
                return None
            if not isinstance(body, dict):
                self._json(400, {"error": "body must be a JSON object"})
                return None
            return body

        # -- dispatch -------------------------------------------------------

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            self._started = time.monotonic()
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if method == "GET" and path == "/":
                return self._page()
            if method == "GET" and path == "/favicon.ico":  # browsers always ask; there is no icon, so say so quietly
                return self._no_content()
            if not path.startswith("/api/"):
                self._drain()
                return self._json(404, {"error": "not found"})
            if not self._authorized():
                self._drain()
                return self._json(401, {"error": "unauthorized"})
            if method == "POST":
                self._raw = self._read_raw()
                if self._raw is None:
                    return
            for route_method, pattern, name in ROUTES:
                match = pattern.fullmatch(path)
                if match and route_method == method:
                    return getattr(self, "_route_" + name)(**match.groupdict())
            self._json(404, {"error": "not found"})

        def _no_content(self) -> None:
            self.send_response(204)
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()

        def _page(self) -> None:
            data = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        # -- routes ---------------------------------------------------------

        def _route_models(self):
            entries = [{"choice": e.choice, "backend": e.backend_id, "model": e.model, "available": e.available,
                        "chat": e.chat, "reason": e.reason, "message": e.message}
                       for e in app.models.list_models()]
            self._json(200, {"models": entries, "default": app.models.default})

        def _route_conversation_list(self):
            self._json(200, {"conversations": app.conversations.list()})

        def _route_conversation_create(self):
            self._json(201, {"id": app.conversations.create(self._client())})

        def _route_conversation_get(self, id):
            conv = app.conversations.get(id)
            self._json(200, conv) if conv else self._json(404, {"error": "no such conversation"})

        def _route_message_send(self, id):
            body = self._body()
            if body is None:
                return
            text, model = body.get("text"), body.get("model")
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                return self._json(400, {"error": f"'text' must be 1 to {MAX_TEXT} characters"})
            if not isinstance(model, str):
                return self._json(400, {"error": "'model' must be a backend_id:model choice"})
            try:
                gen = app.runner.send(id, text, model, self._client())
            except KeyError:
                return self._json(404, {"error": "no such conversation"})
            except Busy:
                return self._json(409, {"error": "this conversation is still answering"})
            except UnknownModelChoice as exc:
                return self._json(400, {"error": str(exc)})
            self._json(202, {"generation_id": gen.id})

        def _route_status(self):
            """What the control panel shows: uptime, replies in progress, and what is loaded in memory."""
            self._json(200, {"uptime_seconds": int(time.time() - started),
                             "replies_in_progress": app.runner.active_count(),
                             "conversations": app.conversations.count(),
                             "default_model": app.models.default, "loaded": app.models.loaded(),
                             "memory": app.memory.status()})

        def _route_default_set(self):
            """Set the model new devices start with. It is saved in the config, so it survives a restart."""
            body = self._body()
            if body is None:
                return
            if not isinstance(body.get("model"), str):
                return self._json(400, {"error": "'model' must be a backend_id:model choice"})
            try:
                choice = app.models.set_default(body["model"])
            except UnknownModelChoice as exc:
                return self._json(400, {"error": str(exc)})
            except BackendError as exc:
                return self._json(502, {"error": exc.message})
            except (OSError, ConfigError):  # the reason may name a local path, so it is not sent
                return self._json(500, {"error": "The default could not be saved on the server."})
            self._json(200, {"default": choice})

        def _route_unload(self):
            """Free model memory so the GPU can be used for something else."""
            if app.runner.active():
                return self._json(409, {"error": "a reply is in progress; try again when it finishes"})
            self._json(200, {"unloaded": app.models.unload_all()})

        def _route_generation_stream(self, id):
            gen = app.runner.get(id)
            if gen is None:
                return self._json(404, {"error": "no such reply"})
            snapshot, q = gen.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                for message in stream_messages(gen, snapshot, q):
                    self._line(message)
            except OSError:
                pass  # the client left; the reply carries on without it

        def _line(self, message: dict) -> None:
            self.wfile.write(json.dumps(message).encode("utf-8") + b"\n")
            self.wfile.flush()

        def _client(self) -> str:
            label = (self.headers.get("X-Client-Name") or "").strip()[:40]
            return f"{self.client_address[0]} {label}".strip()

    return _Server((host, port), Handler)
