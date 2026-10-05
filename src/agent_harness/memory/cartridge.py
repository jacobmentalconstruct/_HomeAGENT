"""Conversation-scoped retrieval: a vector tier and an independent lexical (FTS5) tier.

The vector tier needs embeddings; the lexical tier does not. If the vector tier cannot serve (missing
model, embedding error, incompatible index) memory stays `ready` on the lexical tier with a reason and
fix text. It is `degraded` only when no tier can serve.
"""

from __future__ import annotations

import threading
from pathlib import Path

from ..models.errors import BackendError
from ..store.event_store import Event
from .lexical_store import LexicalStore

BATCH_SIZE = 32
RECONCILE_BATCH = 32
_INDEX_FAULTS = ("Memory index uses", "Embedding dimensions changed")

Fault = tuple[str, str, str]  # (machine-readable reason, human fix, error text)


class ConversationMemory:
    """Derived index; the SQLite event log remains the source of truth."""

    def __init__(self, *, enabled: bool, path: Path, identity: str, top_k: int, embed,
                 store_kind: str = "chroma", strict: bool = False, client_factory=None,
                 model_checker=None, embed_fault: Fault | None = None):
        self.enabled, self.identity, self.top_k = enabled, identity, top_k
        self._embed = embed
        self._lock = threading.RLock()
        self._store = None
        self._lexical: LexicalStore | None = None
        self._store_name, self._store_reason = store_kind, ""
        self._model = identity.split(":", 1)[-1]
        self._vector_fault: Fault | None = None  # lasting: needs an operator action or a restart
        self._transient: Fault | None = None  # clears when embedding and the store work again
        self._lexical_fault: Fault | None = None
        self._lexical_transient: Fault | None = None
        self._failed_retrievals = 0
        self._last_error = ""
        self._threads: list[threading.Thread] = []
        if not enabled:
            return
        self._open_lexical(path)
        if embed_fault is not None:
            self._vector_fault = embed_fault
            return
        try:
            self._store, self._store_name, self._store_reason = self._open_store(
                path, identity, store_kind, strict, client_factory)
        except Exception as exc:
            self._vector_fault = self._classify(exc, embedding=False, opening=True)[0]
            return
        if model_checker is not None:
            try:
                if not model_checker():
                    self._transient = ("embedding_model_missing", f"run: ollama pull {self._model}",
                                       f"Embedding model '{self._model}' is not installed.")
            except Exception:
                pass  # a checker failure is not a finding; the first embedding call will say

    def _open_lexical(self, path: Path) -> None:
        try:
            lexical = LexicalStore(path / "lexical.sqlite3")
            lexical.open()
            self._lexical = lexical
        except Exception as exc:
            self._lexical_fault = (
                "lexical_unavailable",
                "this Python's SQLite may lack FTS5, or runtime/memory/lexical.sqlite3 is unusable; remove it to rebuild",
                f"Keyword index unavailable ({type(exc).__name__}).")

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
            raise  # schema / identity mismatch: config error, no fallback
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

    def _classify(self, exc: Exception, *, embedding: bool, opening: bool = False) -> tuple[Fault, bool]:
        """(fault, lasting). Lasting faults need an operator action; the rest are retried."""
        detail = str(exc)
        if isinstance(exc, ValueError) and detail.startswith(_INDEX_FAULTS):
            return ("index_incompatible", "remove runtime/memory/ to rebuild the index", detail[:240]), True
        if opening:
            if isinstance(exc, ImportError):
                return ("vector_store_unavailable",
                        "install requirements.txt (python -m pip install -r requirements.txt) or set memory.store to sqlite",
                        "Chroma is unavailable; install requirements.txt."), True
            return ("vector_store_unavailable", "check runtime/memory/, or remove it to rebuild",
                    f"Local memory operation failed ({type(exc).__name__}); check Chroma and Ollama."), True
        if embedding:
            error = (f"Embedding service {exc.reason}." if isinstance(exc, BackendError)
                     else f"Embedding failed ({type(exc).__name__}).")
            return ("embedding_unavailable",
                    f"check that Ollama is running and has the embedding model (ollama pull {self._model})",
                    error), False
        return ("transient", "check Chroma and runtime/memory/",
                f"Local memory operation failed ({type(exc).__name__}); check Chroma and Ollama."), False

    def _fail(self, exc: Exception, *, embedding: bool) -> None:
        fault, lasting = self._classify(exc, embedding=embedding)
        if lasting:
            self._vector_fault = fault
        elif not (self._transient and self._transient[0] == "embedding_model_missing"
                  and fault[0] == "embedding_unavailable"):
            self._transient = fault  # the more specific "model missing" finding is kept

    def _vector_usable(self) -> bool:
        return self._store is not None and self._vector_fault is None

    def _vector_down(self) -> bool:
        return not self._vector_usable() or self._transient is not None

    def _lexical_usable(self) -> bool:
        return self._lexical is not None and self._lexical_fault is None and self._lexical_transient is None

    def status(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "state": "disabled", "indexed": 0, "error": ""}
        if not self._vector_down():
            state, tier = "ready", "vector"
        elif self._lexical_usable():
            state, tier = "ready", "lexical"
        else:
            state, tier = "degraded", "none"
        faults = [f for f in (self._vector_fault, self._transient, self._lexical_fault,
                              self._lexical_transient) if f]
        first = faults[0] if faults else ("", "", "")
        reason = "all_tiers_failed" if state == "degraded" else first[0]
        error = " ".join(dict.fromkeys(f[2] for f in faults))
        fix = " ".join(dict.fromkeys(f[1] for f in faults)) if state == "degraded" else first[1]
        return {"enabled": True, "state": state, "indexed": len(self._store.ids()) if self._store else 0,
                "lexical_indexed": len(self._lexical.seqs()) if self._lexical else 0,
                "error": error, "store": self._store_name, "store_reason": self._store_reason,
                "tier": tier, "reason": reason, "fix": fix,
                "failed_retrievals": self._failed_retrievals, "last_error": self._last_error}

    def _completed_turn_events(self, events: list[Event]) -> list[Event]:
        completed = {e.payload.get("generation_id") for e in events
                     if e.kind == "turn.assistant" and e.payload.get("generation_id")}
        return [e for e in events if e.kind in ("turn.user", "turn.assistant")
                and e.payload.get("generation_id") in completed
                and isinstance(e.payload.get("text"), str) and e.payload["text"].strip()]

    def reconcile(self, events: list[Event], max_events: int | None = None, wait: bool = True) -> None:
        """Idempotently index completed turns missing from either tier. An embedding failure is recorded
        as a tier fault, never raised, and never stops the lexical index. With wait=False, indexing is
        skipped when another reconcile (the background catch-up) is already running."""
        if not self.enabled or not self._lock.acquire(blocking=wait):
            return
        try:
            completed = self._completed_turn_events(events)
            self._reconcile_lexical(completed)
            self._reconcile_vector(completed, max_events)
        finally:
            self._lock.release()

    def _reconcile_lexical(self, completed: list[Event]) -> None:
        if self._lexical is None or self._lexical_fault is not None:
            return
        missing = [e for e in completed if e.seq not in self._lexical.seqs()]
        if not missing:
            return
        try:
            self._lexical.upsert([e.seq for e in missing], [e.payload["text"] for e in missing],
                                 [e.conversation_id for e in missing],
                                 ["user" if e.kind == "turn.user" else "assistant" for e in missing])
        except Exception as exc:
            self._lexical_transient = ("transient", "check runtime/memory/lexical.sqlite3",
                                       f"Keyword index write failed ({type(exc).__name__}).")
        else:
            self._lexical_transient = None

    def _reconcile_vector(self, completed: list[Event], max_events: int | None) -> None:
        if not self._vector_usable():
            return
        missing = [e for e in completed if f"event-{e.seq}" not in self._store.ids()]
        if max_events is not None:
            missing = missing[:max_events]
        for offset in range(0, len(missing), BATCH_SIZE):
            batch = missing[offset:offset + BATCH_SIZE]
            documents = [e.payload["text"] for e in batch]
            try:
                vectors = self._embed(documents)
                dimensions = len(vectors[0]) if vectors else 0
                if not dimensions or any(len(v) != dimensions for v in vectors):
                    raise ValueError("Embedding dimensions are inconsistent.")
            except Exception as exc:
                self._fail(exc, embedding=True)
                return
            try:
                self._store.set_dimensions(dimensions)
                self._store.upsert(
                    [f"event-{e.seq}" for e in batch], vectors, documents,
                    [{"conversation_id": e.conversation_id, "seq": e.seq,
                      "role": "user" if e.kind == "turn.user" else "assistant"} for e in batch])
            except Exception as exc:
                self._fail(exc, embedding=False)
                return
            self._transient = None

    def reconcile_in_background(self, events: list[Event]) -> threading.Thread:
        """Index everything missing on a daemon thread, with no batch limit."""
        self._threads = [t for t in self._threads if t.is_alive()]
        thread = threading.Thread(target=self._background_reconcile, args=(events,), daemon=True)
        self._threads.append(thread)
        thread.start()
        return thread

    def _background_reconcile(self, events: list[Event]) -> None:
        try:
            self.reconcile(events)
        except Exception:
            pass  # faults are recorded inside reconcile; a thread must never crash the server

    def retrieve(self, query: str, conversation_id: str, events: list[Event]) -> list[dict]:
        if not self.enabled:
            return []
        try:
            self.reconcile(events, max_events=RECONCILE_BATCH, wait=False)  # never queue behind the catch-up
        except Exception:
            pass
        if self._vector_usable() and self._store.ids():
            try:
                vector = self._embed([query])[0]
            except Exception as exc:
                self._fail(exc, embedding=True)
            else:
                try:
                    if self._store.dimensions() != len(vector):
                        raise ValueError("Embedding dimensions changed; rebuild runtime/memory.")
                    results = self._store.query(
                        vector, min(self.top_k, len(self._store.ids())), conversation_id)
                except Exception as exc:
                    self._fail(exc, embedding=False)
                else:
                    self._transient = None
                    self._lexical_transient = None
                    for item in results:
                        item.setdefault("method", "vector")
                    return results
        return self._lexical_results(query, conversation_id)

    def _lexical_results(self, query: str, conversation_id: str) -> list[dict]:
        if self._lexical is not None and self._lexical_fault is None:
            try:
                results = self._lexical.query(query, self.top_k, conversation_id)
            except Exception as exc:
                self._lexical_transient = ("transient", "check runtime/memory/lexical.sqlite3",
                                           f"Keyword search failed ({type(exc).__name__}).")
            else:
                self._lexical_transient = None
                return results
        if self._vector_down():
            self._failed_retrievals += 1
            self._last_error = "Both retrieval tiers failed for a reply: " + (
                self.status()["error"] or "no tier available.")
        return []

    def close(self) -> None:
        for thread in self._threads:
            thread.join(10)
        if self._store is not None:
            self._store.close()
            self._store = None
        if self._lexical is not None:
            self._lexical.close()
            self._lexical = None


def describe(status: dict) -> tuple[str, str] | None:
    """(level, text) for operators, or None when there is nothing to say. Level is "info" or "warning"."""
    state = status.get("state")
    if state == "disabled":
        return "info", "Conversation memory is disabled in config; set memory.enabled to true."
    fix = status.get("fix") or ""
    if state == "degraded":
        text = "Conversation memory is unavailable: " + (status.get("error") or "no retrieval tier works.")
        return "warning", text + (f" Fix: {fix}" if fix else "")
    notes = []
    if status.get("tier") == "lexical":
        notes.append("Conversation memory is using keyword search only, so recall of reworded questions is "
                     f"weaker ({status.get('reason') or 'vector tier unavailable'}).")
    elif status.get("reason"):
        notes.append(f"Conversation memory note ({status['reason']}).")
    if status.get("store_reason"):
        notes.append(status["store_reason"])
    if not notes:
        return None
    return "info", " ".join(notes) + (f" Fix: {fix}" if fix else "")


def disabled_memory() -> ConversationMemory:
    """A no-dependency implementation for the normal chat configuration."""
    return ConversationMemory(enabled=False, path=Path(), identity="", top_k=0, embed=lambda _texts: [])
