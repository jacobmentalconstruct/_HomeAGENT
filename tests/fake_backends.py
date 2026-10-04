"""Scripted stand-ins for Ollama and llama.cpp on localhost, so tests never call a real model.

A chat script is a list of steps, played in order, then the body ends cleanly:
  ("raw", text)        write text as one chunk          ("line", text)    same, plus a newline
  ("hold", Event)      wait until the test sets the event
  ("sleep", seconds)   pause                            ("reset",)        drop the connection mid-body
  ("endless", text, interval)  write text until the client leaves
  ("status", code, body)       answer with that HTTP status instead of streaming
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass  # clients drop on purpose in these tests


class FakeBackend:
    def __init__(self, kind: str, models=("m:1",), scripts=(), list_delay: float = 0.0, list_body=None,
                 embedding_models=(), loaded=(), unload_fails=(), show_delay: float = 0.0):
        self.kind, self.models, self.scripts = kind, list(models), list(scripts)
        self.embedding_models = set(embedding_models)
        self.loaded, self.unloaded = list(loaded), []
        self.unload_fails = set(unload_fails)
        self.show_delay = show_delay
        self.list_delay, self.list_body = list_delay, list_body
        self.requests: list[dict] = []
        self.client_gone = threading.Event()
        self.request_seen = threading.Event()  # set when a chat request has arrived
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _plain(self, code, body: bytes, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if fake.list_delay:
                    time.sleep(fake.list_delay)
                if self.path == "/api/ps" and fake.kind == "ollama":
                    return self._plain(200, json.dumps({"models": [{"name": m, "size": 6_000_000_000, "size_vram": 5_000_000_000}
                                                       for m in fake.loaded]}).encode())
                tags = "/api/tags" if fake.kind == "ollama" else "/v1/models"
                if self.path != tags:
                    return self._plain(404, b"{}")
                body = fake.list_body
                if body is None:
                    body = ({"models": [{"name": m} for m in fake.models]} if fake.kind == "ollama"
                            else {"data": [{"id": m} for m in fake.models]})
                self._plain(200, body if isinstance(body, bytes) else json.dumps(body).encode())

            def _chunk(self, data: bytes):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                self.wfile.flush()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/generate":
                    if body.get("model") in fake.unload_fails:
                        return self._plain(400, b'{"error":"cannot unload"}')
                    fake.unloaded.append(body)
                    fake.loaded = [m for m in fake.loaded if m != body.get("model")]
                    return self._plain(200, b"{}")
                if self.path == "/api/show":
                    if fake.show_delay:
                        time.sleep(fake.show_delay)
                    caps = ["embedding"] if body.get("model") in fake.embedding_models else ["completion", "tools"]
                    return self._plain(200, json.dumps({"capabilities": caps}).encode())
                fake.requests.append({"path": self.path, "body": body})
                fake.request_seen.set()
                steps = fake.scripts.pop(0) if fake.scripts else []
                if steps and steps[0][0] == "status":
                    return self._plain(steps[0][1], steps[0][2].encode(), "text/plain")
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.flush()
                try:
                    for step in steps:
                        if step[0] == "raw":
                            self._chunk(step[1].encode())
                        elif step[0] == "line":
                            self._chunk((step[1] + "\n").encode())
                        elif step[0] == "sleep":
                            time.sleep(step[1])
                        elif step[0] == "hold":  # wait for the test to release it
                            step[1].wait(15)
                        elif step[0] == "reset":
                            self.close_connection = True
                            self.connection.shutdown(socket.SHUT_RDWR)
                            return
                        elif step[0] == "endless":
                            while True:
                                self._chunk(step[1].encode())
                                time.sleep(step[2])
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except OSError:
                    fake.client_gone.set()

        self._server = _Server(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# Script builders -------------------------------------------------------------

def ollama_chunk(text: str) -> tuple:
    return ("line", json.dumps({"message": {"role": "assistant", "content": text}, "done": False}))


def ollama_reply(chunks, *, done_reason="stop", prompt=7, evals=None) -> list:
    done = {"done": True, "done_reason": done_reason}
    if prompt is not None:
        done["prompt_eval_count"] = prompt
        done["eval_count"] = evals if evals is not None else len(chunks)
    return [ollama_chunk(c) for c in chunks] + [("line", json.dumps(done))]


def llamacpp_chunk(text: str) -> tuple:
    return ("raw", "data: " + json.dumps({"choices": [{"delta": {"content": text}, "finish_reason": None}]}) + "\n\n")


def llamacpp_reply(chunks, *, done_reason="stop", prompt=7, evals=None) -> list:
    steps = [llamacpp_chunk(c) for c in chunks]
    steps.append(("raw", "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": done_reason}]}) + "\n\n"))
    if prompt is not None:  # the documented usage-at-end shape: a chunk with empty choices
        usage = {"prompt_tokens": prompt, "completion_tokens": evals if evals is not None else len(chunks)}
        steps.append(("raw", "data: " + json.dumps({"choices": [], "usage": usage}) + "\n\n"))
    steps.append(("raw", "data: [DONE]\n\n"))
    return steps
