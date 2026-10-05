"""Conversation-scoped retrieval; orchestrates a pluggable vector store."""

from __future__ import annotations

import threading
from pathlib import Path

from ..models.errors import BackendError
from ..store.event_store import Event

BATCH_SIZE = 32


class ConversationMemory:
    """Optional adapter; the SQLite event log remains the source of truth."""

    def __init__(self, *, enabled: bool, path: Path, identity: str, top_k: int, embed,
                 store_kind: str = "chroma", strict: bool = False, client_factory=None):
        self.enabled, self.identity, self.top_k = enabled, identity, top_k
        self._embed = embed
        self._lock = threading.RLock()
        self._error = ""
        self._store = None
        self._store_name = store_kind
        self._store_reason = ""
        if not enabled:
            self._state = "disabled"
            return
        self._state = "ready"
        try:
            self._store, self._store_name, self._store_reason = self._open_store(
                path, identity, store_kind, strict, client_factory)
        except Exception as exc:
            self._degrade(exc)

    def _open_store(self, path, identity, store_kind, strict, client_factory):
        from .chroma_store import ChromaStore
        from .sqlite_store import SqliteStore

        if store_kind == "sqlite":
            s = SqliteStore(path / "vectors.sqlite3", identity)
            s.open()
            return s, "sqlite", ""

        # store_kind == "chroma": fall back to sqlite only for non-config errors (ImportError, etc.)
        try:
            s = ChromaStore(path, identity, client_factory=client_factory)
            s.open()
            return s, "chroma", ""
        except ValueError:
            raise  # schema / identity mismatch — config error, no fallback
        except Exception as chroma_exc:
            if strict:
                raise
            reason = f"chroma unavailable ({type(chroma_exc).__name__}); using sqlite fallback."
            try:
                s = SqliteStore(path / "vectors.sqlite3", identity)
                s.open()
                return s, "sqlite", reason
            except Exception as sqlite_exc:
                raise sqlite_exc from chroma_exc

    def _degrade(self, exc: Exception) -> None:
        self._state = "degraded"
        detail = str(exc)
        if isinstance(exc, ImportError):
            self._error = "Chroma is unavailable; install requirements.txt."
        elif isinstance(exc, ValueError) and detail.startswith(("Memory index uses", "Embedding dimensions")):
            self._error = detail[:240]
        elif isinstance(exc, BackendError):
            self._error = f"Embedding service {exc.reason}."
        else:
            self._error = f"Local memory operation failed ({type(exc).__name__}); check Chroma and Ollama."

    def status(self) -> dict:
        indexed = len(self._store.ids()) if self._store is not None else 0
        result = {"enabled": self.enabled, "state": self._state,
                  "indexed": indexed, "error": self._error}
        if self.enabled and self._state != "disabled":
            result["store"] = self._store_name
            result["store_reason"] = self._store_reason
        return result

    def _completed_turn_events(self, events: list[Event]) -> list[Event]:
        completed = {e.payload.get("generation_id") for e in events
                     if e.kind == "turn.assistant" and e.payload.get("generation_id")}
        return [e for e in events if e.kind in ("turn.user", "turn.assistant")
                and e.payload.get("generation_id") in completed
                and isinstance(e.payload.get("text"), str) and e.payload["text"].strip()]

    def reconcile(self, events: list[Event]) -> None:
        """Idempotently upsert completed turn events absent from the derived index."""
        if not self.enabled or self._state != "ready":
            return
        with self._lock:
            missing = [e for e in self._completed_turn_events(events)
                       if f"event-{e.seq}" not in self._store.ids()]
            try:
                for offset in range(0, len(missing), BATCH_SIZE):
                    batch = missing[offset:offset + BATCH_SIZE]
                    documents = [e.payload["text"] for e in batch]
                    vectors = self._embed(documents)
                    dimensions = len(vectors[0]) if vectors else 0
                    if not dimensions or any(len(v) != dimensions for v in vectors):
                        raise ValueError("Embedding dimensions are inconsistent.")
                    self._store.set_dimensions(dimensions)
                    ids = [f"event-{e.seq}" for e in batch]
                    self._store.upsert(
                        ids, vectors, documents,
                        [{"conversation_id": e.conversation_id, "seq": e.seq,
                          "role": "user" if e.kind == "turn.user" else "assistant"}
                         for e in batch])
            except Exception as exc:
                self._degrade(exc)
                raise

    def retrieve(self, query: str, conversation_id: str, events: list[Event]) -> list[dict]:
        if not self.enabled or self._state != "ready":
            return []
        try:
            self.reconcile(events)
            if self._state != "ready" or not self._store.ids():
                return []
            vector = self._embed([query])[0]
            if self._store.dimensions() != len(vector):
                raise ValueError("Embedding dimensions changed; rebuild runtime/memory.")
            return self._store.query(
                vector, min(self.top_k, len(self._store.ids())), conversation_id)
        except Exception as exc:
            self._degrade(exc)
            return []


def disabled_memory() -> ConversationMemory:
    """A no-dependency implementation for the normal chat configuration."""
    return ConversationMemory(enabled=False, path=Path(), identity="", top_k=0, embed=lambda _texts: [])
