"""Conversation-scoped retrieval backed by a derived persistent Chroma index."""

from __future__ import annotations

import importlib
import threading
from pathlib import Path

from ..models.errors import BackendError
from ..store.event_store import Event

SCHEMA = 1
COLLECTION = "conversation_turns"
BATCH_SIZE = 32


class ConversationMemory:
    """Optional adapter; the SQLite event log remains the source of truth."""

    def __init__(self, *, enabled: bool, path: Path, identity: str, top_k: int, embed,
                 client_factory=None):
        self.enabled, self.identity, self.top_k = enabled, identity, top_k
        self._embed = embed
        self._lock = threading.RLock()
        self._error = ""
        self._collection = None
        self._ids: set[str] = set()
        self._dimensions: int | None = None
        if not enabled:
            self._state = "disabled"
            return
        try:
            settings = None
            if client_factory is None:
                chromadb = importlib.import_module("chromadb")
                client_factory = chromadb.PersistentClient
                settings = chromadb.config.Settings(anonymized_telemetry=False)
            client = client_factory(path=str(path), settings=settings)
            self._collection = client.get_or_create_collection(
                name=COLLECTION,
                metadata={"schema": SCHEMA, "embedding_identity": identity, "hnsw:space": "cosine"})
            self._load_metadata()
            self._state = "ready"
        except Exception as exc:
            self._degrade(exc)

    def _load_metadata(self) -> None:
        metadata = self._collection.metadata or {}
        if metadata.get("schema") != SCHEMA or metadata.get("embedding_identity") != self.identity:
            raise ValueError("Memory index uses a different schema or embedding model; rebuild runtime/memory.")
        self._dimensions = metadata.get("embedding_dimensions")
        data = self._collection.get(include=["metadatas"])
        self._ids = set(data.get("ids") or [])
        if self._dimensions is None and self._ids:
            sample = self._collection.get(ids=[next(iter(self._ids))], include=["embeddings"])
            vectors = sample.get("embeddings")
            if vectors is not None and len(vectors):
                self._dimensions = len(vectors[0])

    def _degrade(self, exc: Exception) -> None:
        self._state = "degraded"
        detail = str(exc)
        if isinstance(exc, ImportError):
            self._error = "Chroma is unavailable; install requirements-rag.txt."
        elif isinstance(exc, ValueError) and detail.startswith(("Memory index uses", "Embedding dimensions")):
            self._error = detail[:240]
        elif isinstance(exc, BackendError):
            self._error = f"Embedding service {exc.reason}."
        else:
            self._error = f"Local memory operation failed ({type(exc).__name__}); check Chroma and Ollama."

    def status(self) -> dict:
        return {"enabled": self.enabled, "state": self._state, "indexed": len(self._ids),
                "error": self._error}

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
            missing = [e for e in self._completed_turn_events(events) if f"event-{e.seq}" not in self._ids]
            try:
                for offset in range(0, len(missing), BATCH_SIZE):
                    batch = missing[offset:offset + BATCH_SIZE]
                    documents = [e.payload["text"] for e in batch]
                    vectors = self._embed(documents)
                    dimensions = len(vectors[0]) if vectors else 0
                    if not dimensions or any(len(v) != dimensions for v in vectors):
                        raise ValueError("Embedding dimensions are inconsistent.")
                    if self._dimensions is not None and self._dimensions != dimensions:
                        raise ValueError("Embedding dimensions changed; rebuild runtime/memory.")
                    if self._dimensions is None:
                        self._dimensions = dimensions
                        metadata = dict(self._collection.metadata or {})
                        metadata["embedding_dimensions"] = dimensions
                        metadata.pop("hnsw:space", None)  # Chroma rejects modifying immutable distance settings.
                        try:
                            self._collection.modify(metadata=metadata)
                        except Exception:
                            pass  # In-memory validation and the stored-vector fallback remain available.
                    ids = [f"event-{e.seq}" for e in batch]
                    self._collection.upsert(
                        ids=ids, embeddings=vectors, documents=documents,
                        metadatas=[{"conversation_id": e.conversation_id, "seq": e.seq,
                                    "role": "user" if e.kind == "turn.user" else "assistant"} for e in batch])
                    self._ids.update(ids)
            except Exception as exc:
                self._degrade(exc)
                raise

    def retrieve(self, query: str, conversation_id: str, events: list[Event]) -> list[dict]:
        if not self.enabled or self._state != "ready":
            return []
        try:
            self.reconcile(events)
            if self._state != "ready" or not self._ids:
                return []
            vector = self._embed([query])[0]
            if self._dimensions != len(vector):
                raise ValueError("Embedding dimensions changed; rebuild runtime/memory.")
            results = self._collection.query(
                query_embeddings=[vector], n_results=min(self.top_k, len(self._ids)),
                where={"conversation_id": conversation_id},
                include=["documents", "metadatas", "distances"])
            documents = (results.get("documents") or [[]])[0] or []
            metadatas = (results.get("metadatas") or [[]])[0] or []
            distances = (results.get("distances") or [[]])[0] or []
            found = []
            for document, metadata, distance in zip(documents, metadatas, distances):
                if not document:
                    continue
                seq = int(metadata["seq"])
                found.append({"id": f"{conversation_id}:{seq}", "seq": seq,
                              "role": metadata["role"], "content": document,
                              "distance": float(distance)})
            return found
        except Exception as exc:
            self._degrade(exc)
            return []


def disabled_memory() -> ConversationMemory:
    """A no-dependency implementation for the normal chat configuration."""
    return ConversationMemory(enabled=False, path=Path(), identity="", top_k=0, embed=lambda _texts: [])
