"""Append-only SQLite event log: the single source of truth."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    conversation_id TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_conversation ON events (conversation_id, seq);
"""


@dataclass(frozen=True)
class Event:
    seq: int
    ts: float
    kind: str
    actor: str
    conversation_id: str
    payload: dict


class EventStore:
    """Owns the log file. It appends and reads; callers decide what is valid."""

    def __init__(self, path: Path):
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    def append(self, kind: str, actor: str, payload: dict | None = None,
               conversation_id: str = "") -> Event:
        ts = time.time()
        body = json.dumps(payload or {}, ensure_ascii=False)
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (ts, kind, actor, conversation_id, payload) VALUES (?,?,?,?,?)",
                (ts, kind, actor, conversation_id, body))
            self._db.commit()
        return Event(cur.lastrowid, ts, kind, actor, conversation_id, json.loads(body))

    def read(self, after_seq: int = 0, conversation_id: str | None = None,
             limit: int | None = None) -> list[Event]:
        """Events after `after_seq`, oldest first. No limit means all of them."""
        sql = "SELECT * FROM events WHERE seq > ?"
        args: list = [after_seq]
        if conversation_id is not None:
            sql += " AND conversation_id = ?"
            args.append(conversation_id)
        sql += " ORDER BY seq"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [Event(r["seq"], r["ts"], r["kind"], r["actor"], r["conversation_id"],
                      json.loads(r["payload"])) for r in rows]

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()
