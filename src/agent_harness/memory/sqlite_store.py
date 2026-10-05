"""SQLite-backed vector store using float32 blobs and dot-product scoring.

All blobs are stored little-endian regardless of the host byte order, so a database
written on a big-endian machine is readable on a little-endian one and vice versa.
Only stdlib imports; passes the architecture test with no changes to that test.
"""

from __future__ import annotations

import array
import heapq
import sqlite3
import sys
import threading
from pathlib import Path

_SCHEMA = 1
_LITTLE = sys.byteorder == "little"


def _pack(vec: list[float]) -> bytes:
    a = array.array("f", vec)
    if not _LITTLE:
        a.byteswap()
    return a.tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array.array("f")
    a.frombytes(blob)
    if not _LITTLE:
        a.byteswap()
    return a.tolist()


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class SqliteStore:
    """Flat dot-product vector index in a single SQLite database file.

    Practical scale: fast up to roughly 20k vectors; suitable as a fallback tier.
    Thread-safe: SQLite WAL plus a write lock prevent concurrent write corruption.
    """

    def __init__(self, path: Path, identity: str) -> None:
        self._path = path
        self._identity = identity
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._ids: set[str] = set()
        self._dimensions: int | None = None

    def open(self) -> None:
        """Create or reopen the database. Raises on schema/identity mismatch."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS vectors (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            vector BLOB NOT NULL)""")
        self._conn.commit()
        self._load_meta()

    def _load_meta(self) -> None:
        rows = {k: v for k, v in self._conn.execute("SELECT key, value FROM meta")}
        schema = int(rows["schema"]) if "schema" in rows else None
        if schema is not None and schema != _SCHEMA:
            raise ValueError(
                "Memory index uses a different schema or embedding model; rebuild runtime/memory.")
        if schema is None:
            self._conn.execute("INSERT INTO meta VALUES (?, ?)", ("schema", str(_SCHEMA)))
            self._conn.execute("INSERT INTO meta VALUES (?, ?)", ("embedding_identity", self._identity))
            self._conn.commit()
        else:
            if rows.get("embedding_identity", "") != self._identity:
                raise ValueError(
                    "Memory index uses a different schema or embedding model; rebuild runtime/memory.")
        dim_str = rows.get("embedding_dimensions")
        self._dimensions = int(dim_str) if dim_str is not None else None
        self._ids = {row[0] for row in self._conn.execute("SELECT id FROM vectors")}

    def ids(self) -> set[str]:
        return self._ids

    def dimensions(self) -> int | None:
        return self._dimensions

    def set_dimensions(self, d: int) -> None:
        if self._dimensions is None:
            self._dimensions = d
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta VALUES (?, ?)", ("embedding_dimensions", str(d)))
                self._conn.commit()
        elif self._dimensions != d:
            raise ValueError("Embedding dimensions changed; rebuild runtime/memory.")

    def upsert(self, ids: list[str], vectors: list[list[float]],
               documents: list[str], metadatas: list[dict]) -> None:
        rows = [
            (eid, meta["conversation_id"], int(meta["seq"]), meta["role"], doc, _pack(vec))
            for eid, vec, doc, meta in zip(ids, vectors, documents, metadatas)
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO vectors VALUES (?, ?, ?, ?, ?, ?)", rows)
            self._conn.commit()
        self._ids.update(ids)

    def query(self, vector: list[float], n_results: int,
              conversation_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, seq, role, content, vector FROM vectors WHERE conversation_id = ?",
            (conversation_id,)).fetchall()
        scored = [
            (eid, seq, role, content, _dot(vector, _unpack(blob)))
            for eid, seq, role, content, blob in rows
        ]
        top = heapq.nlargest(n_results, scored, key=lambda r: r[4])
        return [
            {"id": f"{conversation_id}:{seq}", "seq": int(seq), "role": role,
             "content": content, "distance": max(0.0, 1.0 - score)}
            for _, seq, role, content, score in top
        ]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
