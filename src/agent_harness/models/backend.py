"""What every backend adapter shares: the stream wrapper, the summary and the base class."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from ..config import BackendConfig
from .errors import BackendError
from .transport import Transport


@dataclass(frozen=True)
class ReplySummary:
    text: str
    stop_reason: str  # "complete" or "truncated" (stopped by the token cap)
    prompt_tokens: int | None
    reply_tokens: int | None


class ChatStream:
    """Iterate to get text chunks. `summary` is set only if the reply ended with the backend's marker.

    Adapters supply events: ("text", str) and a final ("done", {stop_reason, prompt_tokens, reply_tokens}).
    A stream that ends without "done" raises `incomplete`. Any BackendError carries `partial_text`.
    """

    def __init__(self, events: Iterator[tuple[str, object]]):
        self._events = events
        self.text = ""
        self.chunks = 0
        self.summary: ReplySummary | None = None

    def __iter__(self) -> Iterator[str]:
        try:
            for kind, value in self._events:
                if kind == "text":
                    self.text += value
                    self.chunks += 1
                    yield value
                else:
                    self.summary = ReplySummary(self.text, **value)
                    return
            raise BackendError("incomplete", "The backend ended the reply without a final marker.")
        except BackendError as exc:
            exc.partial_text = self.text
            raise
        finally:
            close = getattr(self._events, "close", None)
            if close:
                close()


class Backend:
    """A configured model server. Subclasses translate one protocol."""

    def __init__(self, config: BackendConfig, transport: Transport, num_ctx: int, max_reply_tokens: int,
                 keep_alive: str = "3m"):
        self.keep_alive = keep_alive
        self.config = config
        self.transport = transport
        self.num_ctx = num_ctx
        self.max_reply_tokens = max_reply_tokens

    def list_models(self) -> list[str]:
        raise NotImplementedError

    def loaded_models(self) -> list[dict]:
        """Models this backend holds in memory right now, as {name, size} (bytes). Empty if it cannot say."""
        return []

    def unload_all(self) -> list[str]:
        """Free the model memory this backend holds. Returns the models released (none if it cannot)."""
        return []

    def is_chat(self, model: str) -> bool:
        """False for models that cannot chat, such as embedding models. Unknown counts as True."""
        return True

    def chat(self, model: str, messages: list[dict], options: dict | None = None,
             deadline: float | None = None) -> ChatStream:
        """`options` may hold `max_reply_tokens`, `temperature` and (Ollama) `think`."""
        raise NotImplementedError

    def _cap(self, options: dict | None) -> int:
        return int((options or {}).get("max_reply_tokens", self.max_reply_tokens))
