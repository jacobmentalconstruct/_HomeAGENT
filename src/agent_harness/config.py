"""Config file and access token. Created on first run, then left alone."""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .conversation.window import largest_reply
from .words import WORDS

MIN_TOKEN = 16  # shorter access tokens are refused; an empty or missing one is replaced
BACKEND_KINDS = ("ollama", "llamacpp")
_ID_PATTERN = re.compile(r"[a-z0-9_-]+")

DEFAULTS = {
    "host": "0.0.0.0",
    "port": 8765,
    "require_token": True,
    "backends": [{"id": "ollama", "kind": "ollama", "url": "http://127.0.0.1:11434"}],
    "timeouts": {"connect": 5, "listing": 10, "first_byte": 180, "idle": 60, "total": 900},
    "num_ctx": 8192,
    "max_reply_tokens": 2048,
    # A sensible default for a 16 GB GPU. If it is not installed, the page falls back to the first chat model it finds.
    "default_model": "ollama:qwen3.5:9b",
    "system_prompt": "You are a helpful assistant running privately on the user's home network. Be concise and honest.",
    # How long Ollama keeps a model in GPU memory after its last reply. Shorter frees the GPU sooner for other uses.
    "keep_alive": "3m",
    "memory": {"enabled": True, "store": "chroma", "strict": False,
               "embedding_backend": "ollama", "embedding_model": "nomic-embed-text", "top_k": 4},
}


class ConfigError(ValueError):
    """The config cannot be used. The message is written for the person running the server."""


@dataclass(frozen=True)
class BackendConfig:
    id: str
    kind: str
    url: str


@dataclass(frozen=True)
class Timeouts:
    connect: float
    listing: float
    first_byte: float
    idle: float
    total: float


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    require_token: bool
    token: str
    backends: tuple[BackendConfig, ...]
    timeouts: Timeouts
    num_ctx: int
    max_reply_tokens: int
    default_model: str
    system_prompt: str
    keep_alive: str
    memory: MemoryConfig


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool
    store: str
    strict: bool
    embedding_backend: str
    embedding_model: str
    top_k: int


def _positive(name: str, value: object, whole: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or value <= 0 or (whole and int(value) != value):
        kind = "whole number" if whole else "number"
        raise ConfigError(f"'{name}' must be a positive {kind}, got {value!r}.")
    return int(value) if whole else value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"'{name}' must be text, got {value!r}.")
    return value


def _token(value: object) -> str:
    if not isinstance(value, str) or len(value.strip()) < MIN_TOKEN:
        raise ConfigError(f"'token' must be text of at least {MIN_TOKEN} characters. "
                          "Delete the line to get a new one.")
    return value


def _backend(entry: object, seen: set[str]) -> BackendConfig:
    if not isinstance(entry, dict):
        raise ConfigError(f"Each backend must be an object with id, kind and url, got {entry!r}.")
    ident, kind, url = entry.get("id"), entry.get("kind"), entry.get("url")
    if not isinstance(ident, str) or not _ID_PATTERN.fullmatch(ident):
        raise ConfigError(f"Backend id {ident!r} must use only a-z, 0-9, '_' and '-' (no colon).")
    if ident in seen:
        raise ConfigError(f"Backend id '{ident}' is used twice.")
    if kind not in BACKEND_KINDS:
        raise ConfigError(f"Backend '{ident}' has unknown kind {kind!r}; use one of {BACKEND_KINDS}.")
    parsed = urlparse(url) if isinstance(url, str) else None
    try:  # reading .port raises ValueError for a non-numeric or out-of-range port
        usable = (parsed is not None and parsed.scheme in ("http", "https") and bool(parsed.hostname)
                  and " " not in parsed.netloc and parsed.port != 0)
    except ValueError:
        usable = False
    if not usable:
        raise ConfigError(f"Backend '{ident}' needs a url like http://127.0.0.1:11434, got {url!r}.")
    if parsed.path not in ("", "/"):
        raise ConfigError(f"Backend '{ident}' url must be the server root with no path, got {url!r}.")
    seen.add(ident)
    return BackendConfig(ident, kind, url.rstrip("/"))


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON ({exc.msg}, line {exc.lineno}).") from exc
    if not isinstance(stored, dict):
        raise ConfigError(f"{path} must hold a JSON object.")
    return stored


def word_token(count: int = 5) -> str:
    """A random token made of easy-to-type words (about 8 bits each), for phone keyboards."""
    return "-".join(secrets.choice(WORDS) for _ in range(count))


_WRITE_LOCK = threading.Lock()


def update_file(path: Path, **values: object) -> None:
    """Change keys in the config file and keep everything else. One writer at a time; written whole to a
    private scratch file, then swapped in, so a reader never sees half a file."""
    with _WRITE_LOCK:
        stored = _read(path)
        stored.update(values)
        path.parent.mkdir(parents=True, exist_ok=True)
        scratch = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        scratch.write_text(json.dumps(stored, indent=2), encoding="utf-8")
        os.replace(scratch, path)


def load_config(path: Path) -> Config:
    """Read the config, fill gaps from defaults, write it back if anything was added.

    Unknown keys are ignored and kept in the file."""
    stored = _read(path)
    merged = {**DEFAULTS, **stored}
    if isinstance(stored.get("timeouts"), dict):
        merged["timeouts"] = {**DEFAULTS["timeouts"], **stored["timeouts"]}
    if isinstance(stored.get("memory"), dict):
        merged["memory"] = {**DEFAULTS["memory"], **stored["memory"]}
    token = merged.get("token")
    if token is None or (isinstance(token, str) and not token.strip()):  # missing, null or blank: make a new one
        merged["token"] = secrets.token_urlsafe(24)
    config = _build(merged)
    if merged != stored:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return config


def _build(merged: dict) -> Config:
    backends_raw = merged["backends"]
    if not isinstance(backends_raw, list):
        raise ConfigError("'backends' must be a list.")
    seen: set[str] = set()
    backends = tuple(_backend(entry, seen) for entry in backends_raw)
    timeouts_raw = merged["timeouts"]
    if not isinstance(timeouts_raw, dict):
        raise ConfigError("'timeouts' must be an object.")
    timeouts = Timeouts(**{key: _positive(f"timeouts.{key}", timeouts_raw.get(key))
                           for key in DEFAULTS["timeouts"]})
    host = _text("host", merged["host"])
    if not host.strip():
        raise ConfigError("'host' must not be empty. Use \"0.0.0.0\" for your whole network or \"127.0.0.1\" for this computer only.")
    port = int(_positive("port", merged["port"], whole=True))
    if port > 65535:
        raise ConfigError(f"'port' must be between 1 and 65535, got {port}.")
    if not isinstance(merged["require_token"], bool):
        raise ConfigError(f"'require_token' must be true or false, got {merged['require_token']!r}.")
    num_ctx = int(_positive("num_ctx", merged["num_ctx"], whole=True))
    reply = int(_positive("max_reply_tokens", merged["max_reply_tokens"], whole=True))
    if reply > largest_reply(num_ctx):
        raise ConfigError(f"'max_reply_tokens' ({reply}) is too large for 'num_ctx' ({num_ctx}): it must be at most "
                          f"{largest_reply(num_ctx)} so the prompt keeps room.")
    memory_raw = merged["memory"]
    if not isinstance(memory_raw, dict):
        raise ConfigError("'memory' must be an object.")
    enabled = memory_raw.get("enabled")
    if not isinstance(enabled, bool):
        raise ConfigError("'memory.enabled' must be true or false.")
    store = memory_raw.get("store")
    if store not in ("chroma", "sqlite"):
        raise ConfigError("'memory.store' must be 'chroma' or 'sqlite'.")
    strict = memory_raw.get("strict")
    if not isinstance(strict, bool):
        raise ConfigError("'memory.strict' must be true or false.")
    embed_backend = _text("memory.embedding_backend", memory_raw.get("embedding_backend"))
    embed_model = _text("memory.embedding_model", memory_raw.get("embedding_model"))
    if not embed_backend.strip() or not embed_model.strip():
        raise ConfigError("'memory.embedding_backend' and 'memory.embedding_model' must not be empty.")
    top_k = int(_positive("memory.top_k", memory_raw.get("top_k"), whole=True))
    if top_k > 20:
        raise ConfigError("'memory.top_k' must be at most 20.")
    _default_embed_backend = DEFAULTS["memory"]["embedding_backend"]
    if enabled:
        if embed_backend in seen and not any(
                b.id == embed_backend and b.kind == "ollama" for b in backends):
            raise ConfigError("'memory.embedding_backend' must name a configured Ollama backend.")
        if embed_backend not in seen and embed_backend != _default_embed_backend:
            raise ConfigError("'memory.embedding_backend' must name a configured Ollama backend.")
    return Config(host, port, merged["require_token"], _token(merged["token"]), backends, timeouts, num_ctx, reply,
                  _text("default_model", merged["default_model"]), _text("system_prompt", merged["system_prompt"]),
                  _text("keep_alive", merged["keep_alive"]),
                  MemoryConfig(enabled, store, strict, embed_backend, embed_model, top_k))
