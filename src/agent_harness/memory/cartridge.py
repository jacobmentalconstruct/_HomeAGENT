"""Conversation-scoped retrieval; orchestrates a pluggable vector store."""

from __future__ import annotations

import threading
from pathlib import Path

from ..models.errors import BackendError
from ..store.event_store import Event

BATCH_SIZE = 32
RECONCILE_BATCH = 32


class ConversationMemory:
    """Optional adapter; the SQLite event log remains the source of truth."""

    def __init__(self, *, enabled: bool, path: Path, identity: str, top_k: int, embed,
                 store_kind: str = "chroma", strict: bool = False, client_factory=None,
                 model_checker=None):
        self.enabled, self.identity, self.top_k = enabled, identity, top_k
        self._embed = embed
        self._lock = threading.RLock()
        self._error = ""
        self._reason = ""
        self._fix = ""
        self._tier = "vector"
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
            return
        # Check embedding model availability (optional, for proactive reporting)
        if model_checker is not None:
            try:
                if not model_checker():
                    model_name = identity.split(":", 1)[-1] if ":" in identity else identity
                    self._reason = "embedding_model_missing"
                    self._fix = f"run: ollama pull {model_name}"
                    self._tier = "lexical"
            except Exception:
                pass  # checker failure is non-fatal; assume model available

    def _open_store(self, path, identity, store_kind, strict, client_factory):
        from .chroma_store import ChromaStore
        from .sqlite_store import SqliteStore

        if store_kind == "sqlite":
            s = SqliteStore(path / "vectors.sqlite3", identity)
            s.open()
            return s, "sqlite", ""

        # store_kind == "chroma": fall back to sqlite only for non-config errors
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

    def _degrade(self, exc: Exception, reason: str | None = None) -> None:
        self._state = "degraded"
        detail = str(exc)
        if reason is not None:
            self._reason = reason
        elif isinstance(exc, ValueError) and detail.startswith(("Memory index uses", "Embedding dimensions")):
            self._reason = "index_incompatible"
        elif isinstance(exc, BackendError):
            self._reason = "transient"
        else:
            self._reason = "transient"
        if isinstance(exc, ImportError):
            self._error = "Chroma is unavailable; install requirements.txt."
        elif isinstance(exc, ValueError) and detail.startswith(("Memory index uses", "Embedding dimensions")):
            self._error = detail[:240]
        elif isinstance(exc, BackendError):
            self._error = f"Embedding service {exc.reason}."
        else:
            self._error = f"Local memory operation failed ({type(exc).__name__}); check Chroma and Ollama."
        if not self._fix and self._reason == "index_incompatible":
            self._fix = "remove runtime/memory/ to rebuild"
        if not self._fix and self._reason == "transient":
            self._fix = "check that Ollama and Chroma are running"

    def status(self) -> dict:
        indexed = len(self._store.ids()) if self._store is not None else 0
        result = {"enabled": self.enabled, "state": self._state,
                  "indexed": indexed, "error": self._error}
        if self.enabled and self._state != "disabled":
            result["store"] = self._store_name
            result["store_reason"] = self._store_reason
            result["tier"] = self._tier
            result["reason"] = self._reason
            result["fix"] = self._fix
        return result

    def _completed_turn_events(self, events: list[Event]) -> list[Event]:
        completed = {e.payload.get("generation_id") for e in events
                     if e.kind == "turn.assistant" and e.payload.get("generation_id")}
        return [e for e in events if e.kind in ("turn.user", "turn.assistant")
                and e.payload.get("generation_id") in completed
                and isinstance(e.payload.get("text"), str) and e.payload["text"].strip()]

    def reconcile(self, events: list[Event], max_events: int | None = None) -> None:
        """Idempotently upsert completed turn events absent from the derived index."""
        if not self.enabled or self._state != "ready":
            return
        with self._lock:
            completed = self._completed_turn_events(events)
            # FTS reconcile (text-only; no embeddings needed)
            if self._store is not None and self._store.fts_available():
                fts_missing = [e for e in completed
                               if f"event-{e.seq}" not in self._store.fts_ids()]
                if fts_missing:
                    self._store.fts_upsert(
                        ids=[f"event-{e.seq}" for e in fts_missing],
                        texts=[e.payload["text"] for e in fts_missing],
                        conversation_ids=[e.conversation_id for e in fts_missing],
                        seqs=[e.seq for e in fts_missing],
                        roles=["user" if e.kind == "turn.user" else "assistant"
                               for e in fts_missing])
            # Vector reconcile (needs embeddings)
            missing = [e for e in completed
                       if f"event-{e.seq}" not in self._store.ids()]
            if max_events is not None:
                missing = missing[:max_events]
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

    def reconcile_in_background(self, events: list[Event]) -> threading.Thread:
        """Start a daemon thread that calls reconcile(events) with no batch limit."""
        t = threading.Thread(target=self._background_reconcile,
                             args=(events,), daemon=True)
        t.start()
        return t

    def _background_reconcile(self, events: list[Event]) -> None:
        try:
            self.reconcile(events)
        except Exception:
            pass  # already handled inside reconcile via _degrade

    def _fts_fallback(self, query: str, conversation_id: str) -> list[dict] | None:
        """Return FTS5 results for query, or None if FTS is unavailable."""
        if self._store is None or not self._store.fts_available():
            return None
        results = self._store.fts_query(query, self.top_k, conversation_id)
        return results  # already include method="lexical"

    def retrieve(self, query: str, conversation_id: str, events: list[Event]) -> list[dict]:
        if not self.enabled or self._state != "ready":
            return []
        # Bounded reconcile (FTS + capped vector indexing)
        try:
            self.reconcile(events, max_events=RECONCILE_BATCH)
        except Exception:
            pass  # reconcile called _degrade if fatal; check state below

        if self._state != "ready":
            # Memory was degraded during reconcile; try FTS as a last effort
            fts = self._fts_fallback(query, conversation_id)
            return fts if fts is not None else []

        # Per-reply vector retrieval — failures fall back to FTS, NOT a permanent degrade
        try:
            if not self._store.ids():
                fts = self._fts_fallback(query, conversation_id)
                return fts if fts is not None else []
            vector = self._embed([query])[0]
            if self._store.dimensions() != len(vector):
                raise ValueError("Embedding dimensions changed; rebuild runtime/memory.")
            results = self._store.query(
                vector, min(self.top_k, len(self._store.ids())), conversation_id)
            for r in results:
                r.setdefault("method", "vector")
            return results
        except ValueError as exc:
            # Config error (dimension mismatch) — always degrade
            self._degrade(exc)
            return []
        except Exception:
            # Per-reply transient failure — try FTS without degrading
            fts = self._fts_fallback(query, conversation_id)
            if fts is not None:
                self._tier = "lexical"
                return fts
            # Both tiers failed this reply — do not permanently degrade
            return []


def disabled_memory() -> ConversationMemory:
    """A no-dependency implementation for the normal chat configuration."""
    return ConversationMemory(enabled=False, path=Path(), identity="", top_k=0, embed=lambda _texts: [])
