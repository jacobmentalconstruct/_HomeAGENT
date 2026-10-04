"""Owns conversations: their turns, titles and which reply is in flight. Built from the event log."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from ..models.backend import ReplySummary
from ..store.event_store import Event, EventStore

TITLE_CHARS = 60


@dataclass
class Turn:
    role: str  # "user" or "assistant"
    text: str
    ts: float
    model: str = ""
    failed: str = ""  # failure reason for an assistant turn that never completed
    truncated: bool = False


@dataclass
class Conversation:
    id: str
    created: float
    title: str = "New conversation"
    updated: float = 0.0
    turns: list[Turn] = field(default_factory=list)
    open_generation: str | None = None
    last_window: dict | None = None  # what the latest reply was sent, for the context meter


class ConversationManager:
    """The only writer of conversation events. State is rebuilt from the log at startup."""

    def __init__(self, events: EventStore):
        self._events = events
        self._lock = threading.RLock()
        self._convs: dict[str, Conversation] = {}
        self._samples: list[tuple[str, int, int, int]] = []  # (model, chars, messages, prompt tokens) for the estimator
        for event in events.read():
            self._apply(event)

    # -- projection ---------------------------------------------------------

    def _apply(self, event: Event) -> None:
        kind, p = event.kind, event.payload
        if kind == "conversation.created":
            self._convs[event.conversation_id] = Conversation(event.conversation_id, event.ts, updated=event.ts)
            return
        conv = self._convs.get(event.conversation_id)
        if conv is None:
            return
        if kind == "turn.user":
            if not conv.turns:
                conv.title = p["text"].strip().replace("\n", " ")[:TITLE_CHARS] or conv.title
            conv.turns.append(Turn("user", p["text"], event.ts))
        elif kind == "turn.assistant":
            conv.turns.append(Turn("assistant", p["text"], event.ts, p.get("model", ""),
                                   truncated=bool(p.get("truncated"))))
            window = p.get("window")
            if isinstance(window, dict):
                conv.last_window = window
                if isinstance(p.get("prompt_tokens"), int):
                    self._samples.append((p.get("model", ""), window.get("chars", 0), window.get("messages", 0),
                                          p["prompt_tokens"]))
        elif kind == "generation.failed":
            conv.turns.append(Turn("assistant", p.get("partial_text", ""), event.ts, p.get("model", ""),
                                   failed=f"{p.get('reason', 'failed')}: {p.get('message', '')}"))
        conv.updated = event.ts

    def _record(self, kind: str, actor: str, conversation_id: str, payload: dict) -> None:
        self._apply(self._events.append(kind, actor, payload, conversation_id))

    # -- queries ------------------------------------------------------------

    def count(self) -> int:
        with self._lock:
            return len(self._convs)

    def list(self) -> list[dict]:
        with self._lock:
            ordered = sorted(self._convs.values(), key=lambda c: c.updated, reverse=True)
            return [{"id": c.id, "title": c.title, "updated": c.updated, "turns": len(c.turns),
                     "busy": c.open_generation is not None} for c in ordered]

    def get(self, conversation_id: str) -> dict | None:
        with self._lock:
            conv = self._convs.get(conversation_id)
            if conv is None:
                return None
            return {"id": conv.id, "title": conv.title, "open_generation": conv.open_generation,
                    "window": conv.last_window, "turns": [vars(t).copy() for t in conv.turns]}

    def history_indexed(self, conversation_id: str) -> list[tuple[int, dict]]:
        """(turn index, model-ready message) oldest first. Failed turns are left out; their user messages stay."""
        with self._lock:
            conv = self._convs[conversation_id]
            return [(i, {"role": t.role, "content": t.text}) for i, t in enumerate(conv.turns) if not t.failed]

    def samples(self) -> list[tuple[str, int, int, int]]:
        """What past replies measured, so a restart does not forget what a token costs."""
        with self._lock:
            return list(self._samples)

    # -- commands -----------------------------------------------------------

    def create(self, client: str = "") -> str:
        conversation_id = uuid.uuid4().hex
        with self._lock:
            self._record("conversation.created", "USER", conversation_id, {"client": client})
        return conversation_id

    def begin_turn(self, conversation_id: str, generation_id: str, text: str, model: str, client: str) -> None:
        """Record the user turn and mark a reply as in flight. Raises KeyError or Busy."""
        with self._lock:
            conv = self._convs.get(conversation_id)
            if conv is None:
                raise KeyError(conversation_id)
            if conv.open_generation is not None:
                raise Busy(conversation_id)
            self._record("turn.user", "USER", conversation_id,
                         {"text": text, "model": model, "generation_id": generation_id, "client": client})
            conv.open_generation = generation_id  # only once the turn is safely recorded

    def finish_turn(self, conversation_id: str, generation_id: str, text: str, model: str,
                    summary: ReplySummary, window: dict | None = None) -> None:
        with self._lock:
            self._record("turn.assistant", "AGENT", conversation_id,
                         {"text": text, "model": model, "generation_id": generation_id,
                          "truncated": summary.stop_reason == "truncated", "window": window,
                          "prompt_tokens": summary.prompt_tokens, "reply_tokens": summary.reply_tokens})
            self._close(conversation_id, generation_id)

    def fail_turn(self, conversation_id: str, generation_id: str, model: str, reason: str,
                  message: str, partial_text: str) -> None:
        with self._lock:
            self._record("generation.failed", "SYSTEM", conversation_id,
                         {"model": model, "generation_id": generation_id, "reason": reason,
                          "message": message, "partial_text": partial_text})
            self._close(conversation_id, generation_id)

    def _close(self, conversation_id: str, generation_id: str) -> None:
        conv = self._convs[conversation_id]
        if conv.open_generation == generation_id:
            conv.open_generation = None


class Busy(RuntimeError):
    """The conversation already has a reply in flight."""
