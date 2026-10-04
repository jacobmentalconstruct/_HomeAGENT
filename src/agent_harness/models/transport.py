"""The one HTTP helper for model backends. It owns connections, timeouts and nothing else."""

from __future__ import annotations

import http.client
import json
import time
from collections.abc import Iterator
from urllib.parse import urlparse

from ..config import Timeouts
from .errors import BackendError

_BODY_LIMIT = 2000


class Transport:
    def __init__(self, timeouts: Timeouts):
        self.timeouts = timeouts

    def _connect(self, url: str, connect_timeout: float) -> tuple[http.client.HTTPConnection, str]:
        parts = urlparse(url)
        cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        try:  # config rejects bad urls; this keeps one that slipped through a failed backend, not a crash
            conn = cls(parts.hostname, parts.port, timeout=connect_timeout)
        except (ValueError, http.client.InvalidURL) as exc:
            raise BackendError("unreachable", f"{url} is not a usable address.") from exc
        try:
            conn.connect()
        except TimeoutError as exc:
            raise BackendError("timeout_connect", f"Connecting to {url} took longer than "
                               f"{connect_timeout:g}s.") from exc
        except OSError as exc:
            raise BackendError("unreachable", f"Cannot reach {url}. Is the backend running?") from exc
        return conn, parts.path.rstrip("/")

    @staticmethod
    def _http_error(resp: http.client.HTTPResponse) -> BackendError:
        detail = resp.read(_BODY_LIMIT).decode("utf-8", errors="replace").strip()
        return BackendError("http_error", f"The backend answered HTTP {resp.status}: {detail[:300]}",
                            status=resp.status, detail=detail)

    def get_json(self, url: str, path: str) -> dict:
        return self._json(url, path, None)

    def post_json(self, url: str, path: str, payload: dict, timeout: float | None = None) -> dict:
        return self._json(url, path, payload, timeout)

    def _json(self, url: str, path: str, payload: dict | None, timeout: float | None = None) -> dict:
        """One short JSON call. The listing timeout covers connecting and waiting together."""
        limit = timeout or self.timeouts.listing
        deadline = time.monotonic() + limit
        conn, base = self._connect(url, min(self.timeouts.connect, limit))
        try:
            conn.sock.settimeout(max(0.01, deadline - time.monotonic()))
            if payload is None:
                conn.request("GET", base + path)
            else:
                conn.request("POST", base + path, json.dumps(payload).encode("utf-8"),
                             {"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status >= 400:
                raise self._http_error(resp)
            return json.loads(resp.read())
        except TimeoutError as exc:
            raise BackendError("timeout_listing", f"{url} did not answer within {limit:g}s.") from exc
        except json.JSONDecodeError as exc:
            raise BackendError("protocol_error", f"{url} sent a reply that is not JSON.") from exc
        except (http.client.HTTPException, OSError) as exc:
            raise BackendError("connection_reset", f"The connection to {url} broke: {exc}.") from exc
        finally:
            conn.close()

    def stream_lines(self, url: str, path: str, payload: dict) -> Iterator[str]:
        """POST JSON and yield the reply line by line, bounded by first-byte, idle and total waits."""
        t = self.timeouts
        deadline = time.monotonic() + t.total
        conn, base = self._connect(url, t.connect)
        first = True
        try:
            conn.sock.settimeout(min(t.first_byte, t.total))
            conn.request("POST", base + path, json.dumps(payload).encode("utf-8"),
                         {"Content-Type": "application/json", "Accept": "application/json"})
            resp = conn.getresponse()
            if resp.status >= 400:
                raise self._http_error(resp)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BackendError("deadline", f"The reply was still running after {t.total:g}s.")
                conn.sock.settimeout(min(t.first_byte if first else t.idle, remaining))
                raw = resp.readline()
                if not raw:
                    # http.client's readline reports a connection cut mid-body as a plain end of data.
                    # After a proper chunked terminator it sets chunk_left to None; after a cut it
                    # leaves 0. Internal detail: tests/test_models.py fails if a Python upgrade changes it.
                    if resp.chunked and resp.chunk_left is not None:
                        raise BackendError("connection_reset", f"The connection to {url} ended mid-reply.")
                    return
                first = False
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    yield line
        except TimeoutError as exc:
            if time.monotonic() >= deadline - 0.01:
                raise BackendError("deadline", f"The reply was still running after {t.total:g}s.") from exc
            reason, wait = ("timeout_first_byte", t.first_byte) if first else ("timeout_idle", t.idle)
            raise BackendError(reason, f"The backend sent nothing for {wait:g}s.") from exc
        except (http.client.HTTPException, OSError) as exc:
            raise BackendError("connection_reset", f"The connection to {url} broke: "
                               f"{type(exc).__name__}.") from exc
        finally:
            conn.close()
