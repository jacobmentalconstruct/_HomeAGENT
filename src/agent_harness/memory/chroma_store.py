"""Chroma-backed vector store. Only imported when memory is enabled; no static chromadb dep."""

from __future__ import annotations

import importlib
from pathlib import Path

SCHEMA = 1
COLLECTION = "conversation_turns"


class ChromaStore:
    """Thin adapter around a Chroma persistent collection.

    `open()` is where I/O happens; the constructor is synchronous and infallible.
    """

    def __init__(self, path: Path, identity: str, client_factory=None) -> None:
        self._path = path
        self._identity = identity
        self._client_factory = client_factory
        self._client = None
        self._collection = None
        self._ids: set[str] = set()
        self._dimensions: int | None = None

    def open(self) -> None:
        """Initialise (or reattach to) the Chroma collection. Raises on any failure."""
        settings = None
        factory = self._client_factory
        if factory is None:
            chromadb = importlib.import_module("chromadb")
            factory = chromadb.PersistentClient
            settings = chromadb.config.Settings(anonymized_telemetry=False)
        self._client = factory(path=str(self._path), settings=settings)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"schema": SCHEMA, "embedding_identity": self._identity, "hnsw:space": "cosine"})
        self._load_metadata()

    def _load_metadata(self) -> None:
        metadata = self._collection.metadata or {}
        if metadata.get("schema") != SCHEMA or metadata.get("embedding_identity") != self._identity:
            raise ValueError(
                "Memory index uses a different schema or embedding model; rebuild runtime/memory.")
        self._dimensions = metadata.get("embedding_dimensions")
        data = self._collection.get(include=["metadatas"])
        self._ids = set(data.get("ids") or [])
        if self._dimensions is None and self._ids:
            sample = self._collection.get(ids=[next(iter(self._ids))], include=["embeddings"])
            vectors = sample.get("embeddings")
            if vectors is not None and len(vectors):
                self._dimensions = len(vectors[0])

    def ids(self) -> set[str]:
        return self._ids

    def dimensions(self) -> int | None:
        return self._dimensions

    def set_dimensions(self, d: int) -> None:
        if self._dimensions is None:
            self._dimensions = d
            metadata = dict(self._collection.metadata or {})
            metadata["embedding_dimensions"] = d
            metadata.pop("hnsw:space", None)
            try:
                self._collection.modify(metadata=metadata)
            except Exception:
                pass  # In-memory tracking remains valid; stored-vector fallback also catches mismatch.
        elif self._dimensions != d:
            raise ValueError("Embedding dimensions changed; rebuild runtime/memory.")

    def upsert(self, ids: list[str], vectors: list[list[float]],
               documents: list[str], metadatas: list[dict]) -> None:
        self._collection.upsert(
            ids=ids, embeddings=vectors, documents=documents, metadatas=metadatas)
        self._ids.update(ids)

    def query(self, vector: list[float], n_results: int,
              conversation_id: str) -> list[dict]:
        results = self._collection.query(
            query_embeddings=[vector], n_results=n_results,
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

    def close(self) -> None:
        self._collection = None
        if self._client is not None:
            try:
                self._client._system.stop()
            except Exception:
                pass
            self._client = None
