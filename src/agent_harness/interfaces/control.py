"""The control panel's logic, with no window code: run the server as a child process, watch it, ask it for status.

The panel is one more client of the application. It starts `harness.py serve` like a person would and talks to the
server over its own HTTP API, so a restart always runs the code on disk, and a server crash cannot take the panel down."""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _python() -> str:
    """python.exe rather than pythonw.exe, so the child has real pipes for its output."""
    candidate = Path(sys.executable).with_name("python.exe")
    return str(candidate) if candidate.exists() else sys.executable


def reach_host(host: str) -> str:
    """The address to use to reach a server on this computer: the loopback address when it listens everywhere."""
    return "127.0.0.1" if host in ("", "0.0.0.0") else host


def lan_addresses() -> list[str]:
    """This machine's addresses on the home network, the one used for ordinary traffic first."""
    try:
        found = {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        found = set()
    primary = None
    try:  # choosing a route sends nothing: it only asks which interface would be used to reach beyond this network
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            primary = probe.getsockname()[0]
    except OSError:
        pass
    first = [primary] if primary and not primary.startswith("127.") else []
    return first + sorted(a for a in found if not a.startswith("127.") and a != primary)


class ServerProcess:
    """Runs `harness.py serve` as a child process. Every start is a fresh process, so new code is picked up."""

    def __init__(self, root: Path, on_line: Callable[[str], None], command: list[str] | None = None):
        self.root, self.on_line = root, on_line
        self.command = command or [_python(), "-u", str(root / "harness.py"), "serve"]
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> bool:
        """Start the server. False if it is already running."""
        with self._lock:
            if self.running:
                return False
            self._proc = subprocess.Popen(
                self.command, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=_NO_WINDOW)
            threading.Thread(target=self._read, args=(self._proc,), daemon=True).start()
            return True

    def _read(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            self.on_line(line.rstrip("\r\n"))
        proc.stdout.close()
        self.on_line(f"[server exited with code {proc.wait()}]")

    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the server. False if it was not running."""
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return False
        proc.terminate()
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return True

    def restart(self) -> bool:
        self.stop()
        return self.start()


def _call(host: str, port: int, token: str, method: str, path: str, timeout: float = 3.0) -> dict | None:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request(method, path, b"{}" if method == "POST" else None,
                     {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        resp = conn.getresponse()
        body = json.loads(resp.read() or b"{}")
        if resp.status == 401:
            return {"unauthorized": True}
        return body if resp.status < 400 else {"error": body.get("error", f"HTTP {resp.status}")}
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def fetch_status(host: str, port: int, token: str) -> dict | None:
    """The server's own picture of itself, or None if nothing answers. {"unauthorized": True} for a wrong token."""
    return _call(host, port, token, "GET", "/api/status")


def free_gpu(host: str, port: int, token: str) -> dict | None:
    """Ask the running server to unload its models."""
    return _call(host, port, token, "POST", "/api/unload", timeout=30.0)


def run_cli(root: Path, *args: str, timeout: float = 60.0) -> str:
    """Run a harness.py command and return what it printed. For when the server itself is not running."""
    try:
        done = subprocess.run([_python(), str(root / "harness.py"), *args], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"could not run harness.py {' '.join(args)}: {exc}"
    return (done.stdout + done.stderr).strip()


def gpu_memory() -> tuple[int, int] | None:
    """(used, total) in MiB from nvidia-smi, or None if there is no NVIDIA GPU or the tool is missing."""
    try:
        done = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=3, creationflags=_NO_WINDOW)
        used, total = (int(part) for part in done.stdout.strip().splitlines()[0].split(","))
        return used, total
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


# A line of the server's access log: time, client, method, path, status, milliseconds.
_LOG_LINE = re.compile(r"^[0-9]{2}:[0-9]{2}:[0-9]{2} (\S+) (\S+) (\S+) ([0-9]{3}|-)")


class TrafficStats:
    """Counts requests from the server's access-log lines: recent volume, who is connecting, and what failed."""

    def __init__(self, minute: float = 60.0, window: float = 600.0):
        self.minute, self.window = minute, window
        self._seen: deque[tuple[float, str, int]] = deque()

    def add(self, line: str, now: float | None = None) -> bool:
        """Count one log line. False if it was not an access-log line."""
        match = _LOG_LINE.match(line)
        if not match:
            return False
        status = int(match.group(4)) if match.group(4).isdigit() else 0
        self._seen.append((time.monotonic() if now is None else now, match.group(1), status))
        return True

    def snapshot(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        while self._seen and now - self._seen[0][0] > self.window:
            self._seen.popleft()
        return {"last_minute": sum(1 for t, _, _ in self._seen if now - t <= self.minute),
                "clients": len({client for _, client, _ in self._seen}),
                "errors": sum(1 for _, _, status in self._seen if status >= 400)}


def human_bytes(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} GB"


def describe_loaded(status: dict | None) -> str:
    """Which models are in memory, for a one-line display."""
    if not status or "loaded" not in status:
        return "unknown"
    parts = []
    for backend_id, held in status["loaded"].items():
        if isinstance(held, str):
            parts.append(f"{backend_id}: {held}")
        elif held:
            parts.append(", ".join(f"{m['name']} ({human_bytes(m['size'])})" for m in held))
    return "; ".join(parts) or "nothing"


def describe_state(child_running: bool, status: dict | None) -> tuple[str, str]:
    """(short state, plain-words explanation) from whether this panel's server is running and whether one answers."""
    answering = bool(status) and not status.get("unauthorized") and "error" not in (status or {})
    if status and status.get("unauthorized"):
        return "token", "A server answers but rejects this panel's token. It is probably an older server using another token."
    if child_running and answering:
        return "running", "Running"
    if child_running:
        return "starting", "Starting..."
    if answering:
        return "outside", "A server is running that this panel did not start. Close its window to control it here."
    return "stopped", "Stopped"
