"""SQLite FTS5 keyword index, independent of the vector store. Stdlib only.

Rows use the event sequence number as the FTS rowid, so upsert and presence checks are cheap.
`score` is -bm25 clamped at zero (larger is better). `distance` is 1 / (1 + score) so that, like a
vector distance, smaller is better; it is only comparable to other lexical results.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


def _sanitize(raw: str) -> str | None:
    """Quote every whitespace-separated term and OR them, dropping quotes and control characters (a NUL ends an
    FTS5 string early); user text never reaches the FTS5 parser raw."""
    terms = ["".join(ch for ch in t if ch != '"' and ch >= " " and ch != "\x7f") for t in raw.split()]
    terms = [t for t in terms if t]
    return " OR ".join(f'"{t}"' for t in terms) if terms else None


class LexicalStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._seqs: set[int] = set()

    def open(self) -> None:
        """Create or reopen the index. Raises sqlite3.OperationalError when FTS5 is not compiled in."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts_turns "
                         "USING fts5(text, conversation_id UNINDEXED, role UNINDEXED)")
            conn.commit()
            self._seqs = {row[0] for row in conn.execute("SELECT rowid FROM fts_turns")}
        except Exception:
            conn.close()
            raise
        self._conn = conn

    def seqs(self) -> set[int]:
        return self._seqs

    def upsert(self, seqs: list[int], texts: list[str], conversation_ids: list[str],
               roles: list[str]) -> None:
        with self._lock:
            for seq, text, conversation_id, role in zip(seqs, texts, conversation_ids, roles):
                if seq in self._seqs:
                    self._conn.execute("DELETE FROM fts_turns WHERE rowid = ?", (seq,))
                self._conn.execute(
                    "INSERT INTO fts_turns(rowid, text, conversation_id, role) VALUES (?,?,?,?)",
                    (seq, text, conversation_id, role))
            self._conn.commit()
        self._seqs.update(seqs)

    def query(self, raw_query: str, n_results: int, conversation_id: str) -> list[dict]:
        """Best matches within one conversation. Raises sqlite3.Error on a real database failure."""
        match = _sanitize(raw_query)
        if match is None:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT rowid, role, text, rank FROM fts_turns "
                "WHERE fts_turns MATCH ? AND conversation_id = ? ORDER BY rank LIMIT ?",
                (match, conversation_id, n_results)).fetchall()
        found = []
        for seq, role, text, rank in rows:
            score = max(0.0, -float(rank))
            found.append({"id": f"{conversation_id}:{seq}", "seq": int(seq), "role": role, "content": text,
                          "score": score, "distance": 1.0 / (1.0 + score), "method": "lexical"})
        return found

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
