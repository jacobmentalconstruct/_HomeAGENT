"""SQLite-backed vector store using float32 blobs and dot-product scoring.

All blobs are stored little-endian regardless of the host byte order, so a database
written on a big-endian machine is readable on a little-endian one and vice versa.
Only stdlib imports; passes the architecture test with no changes to that test.

FTS5 tier: an fts_turns virtual table is maintained alongside the vector table.
Distance transform for FTS results: distance = float(-rank) where rank is the raw
BM25 score returned by SQLite (more negative = better match; negating gives a
non-negative, monotonically decreasing distance). This is informational only; do
not compare FTS distances against vector distances numerically.
"""

from __future__ import annotations

import array
import heapq
import math
import re
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


def _l2norm(vec: list[float]) -> list[float]:
    """Return the L2-normalised form of vec; return vec unchanged for zero vectors."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sanitize_fts_query(raw: str) -> str:
    """Convert arbitrary user text to a safe FTS5 query.

    Splits on whitespace, double-quotes each token (escaping embedded quotes),
    and joins with OR. This prevents raw FTS syntax (AND, NEAR, colons, etc.)
    from being interpreted by SQLite's FTS5 query parser.
    """
    tokens = raw.split()
    if not tokens:
        return '""'
    safe = []
    for t in tokens:
        escaped = re.sub(r'"', "", t)  # remove embedded double quotes
        if escaped:
            safe.append(f'"{escaped}"')
    return " OR ".join(safe) if safe else '""'


class SqliteStore:
    """Flat dot-product vector index in a single SQLite database file.

    Practical scale: fast up to roughly 20k vectors; suitable as a fallback tier.
    Thread-safe: SQLite WAL plus a write lock prevent concurrent write corruption.
    Also maintains an FTS5 table for lexical retrieval when embeddings are unavailable.
    """

    def __init__(self, path: Path, identity: str) -> None:
        self._path = path
        self._identity = identity
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._ids: set[str] = set()
        self._fts_ids: set[str] = set()
        self._dimensions: int | None = None
        self._fts: bool = False

    def open(self) -> None:
        """Create or reopen the database. Raises on schema/identity mismatch."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        try:
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
            self._init_fts()
        except Exception:
            self._conn.close()
            self._conn = None
            raise

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

    def _init_fts(self) -> None:
        """Create the FTS5 table if the SQLite build supports it; set _fts flag."""
        try:
            self._conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS fts_turns
                USING fts5(text, conversation_id UNINDEXED,
                           event_seq UNINDEXED, role UNINDEXED)""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS fts_ids (
                id TEXT PRIMARY KEY, event_seq INTEGER NOT NULL)""")
            self._conn.commit()
            self._fts_ids = {row[0] for row in self._conn.execute("SELECT id FROM fts_ids")}
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False

    def ids(self) -> set[str]:
        return self._ids

    def fts_ids(self) -> set[str]:
        return self._fts_ids

    def fts_available(self) -> bool:
        return self._fts

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
            (eid, meta["conversation_id"], int(meta["seq"]), meta["role"], doc,
             _pack(_l2norm(vec)))
            for eid, vec, doc, meta in zip(ids, vectors, documents, metadatas)
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO vectors VALUES (?, ?, ?, ?, ?, ?)", rows)
            self._conn.commit()
        self._ids.update(ids)

    def query(self, vector: list[float], n_results: int,
              conversation_id: str) -> list[dict]:
        q = _l2norm(vector)
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, seq, role, content, vector FROM vectors WHERE conversation_id = ?",
                (conversation_id,)).fetchall()
        scored = [
            (eid, seq, role, content, _dot(q, _unpack(blob)))
            for eid, seq, role, content, blob in rows
        ]
        top = heapq.nlargest(n_results, scored, key=lambda r: r[4])
        return [
            {"id": f"{conversation_id}:{seq}", "seq": int(seq), "role": role,
             "content": content, "distance": max(0.0, 1.0 - score), "method": "vector"}
            for _, seq, role, content, score in top
        ]

    def fts_upsert(self, ids: list[str], texts: list[str],
                   conversation_ids: list[str], seqs: list[int],
                   roles: list[str]) -> None:
        if not self._fts:
            return
        with self._lock:
            for eid, text, conv_id, seq, role in zip(ids, texts, conversation_ids, seqs, roles):
                if eid in self._fts_ids:
                    row = self._conn.execute(
                        "SELECT event_seq FROM fts_ids WHERE id = ?", (eid,)).fetchone()
                    if row:
                        self._conn.execute(
                            "DELETE FROM fts_turns WHERE event_seq = ?", (row[0],))
                    self._conn.execute("DELETE FROM fts_ids WHERE id = ?", (eid,))
                self._conn.execute(
                    "INSERT INTO fts_turns(text, conversation_id, event_seq, role)"
                    " VALUES (?,?,?,?)",
                    (text, conv_id, seq, role))
                self._conn.execute(
                    "INSERT INTO fts_ids(id, event_seq) VALUES (?,?)", (eid, seq))
            self._conn.commit()
        self._fts_ids.update(ids)

    def fts_query(self, raw_query: str, n_results: int,
                  conversation_id: str) -> list[dict]:
        """Return top-n FTS5 matches for raw_query within conversation_id.

        Queries are sanitized before execution; user text cannot inject FTS5 syntax.
        Distance = float(-rank) where rank is the raw BM25 score (more negative = better
        match); negating gives a non-negative, monotonically decreasing distance value.
        """
        if not self._fts:
            return []
        safe_q = _sanitize_fts_query(raw_query)
        with self._lock:
            try:
                rows = self._conn.execute(
                    """SELECT event_seq, role, text, rank FROM fts_turns
                       WHERE fts_turns MATCH ? AND conversation_id = ?
                       ORDER BY rank LIMIT ?""",
                    (safe_q, conversation_id, n_results)).fetchall()
            except sqlite3.OperationalError:
                return []
        return [
            {"id": f"{conversation_id}:{seq}", "seq": int(seq), "role": role,
             "content": text, "distance": float(-rank), "method": "lexical"}
            for seq, role, text, rank in rows
        ]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
