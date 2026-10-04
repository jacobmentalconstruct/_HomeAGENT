"""llama.cpp server protocol: `/v1/models` and server-sent `data:` lines from `/v1/chat/completions`.

Shapes follow the server's documentation, not observation: no llama.cpp server was available
when this was written. `num_ctx` is not sent because the server fixes its context at launch."""

from __future__ import annotations

import json
from collections.abc import Iterator

from .backend import Backend, ChatStream
from .errors import BackendError


class LlamaCppBackend(Backend):
    def list_models(self) -> list[str]:
        data = self.transport.get_json(self.config.url, "/v1/models")
        try:
            return sorted(item["id"] for item in data["data"])
        except (KeyError, TypeError) as exc:
            raise BackendError("protocol_error", "The model list has an unexpected shape.") from exc

    def chat(self, model: str, messages: list[dict], options: dict | None = None) -> ChatStream:
        payload = {"model": model, "messages": messages, "stream": True,
                   "max_tokens": self._cap(options), "stream_options": {"include_usage": True}}
        if options and "temperature" in options:
            payload["temperature"] = options["temperature"]
        return ChatStream(self._events(payload))

    def _events(self, payload: dict) -> Iterator[tuple[str, object]]:
        finish, usage = None, {}
        try:
            for line in self.transport.stream_lines(self.config.url, "/v1/chat/completions", payload):
                if line.startswith("error:"):  # some builds send in-stream errors as their own SSE field
                    raise BackendError("protocol_error", f"The server reported an error: {line[6:].strip()[:200]}")
                if not line.startswith("data:"):
                    continue  # comments, event names, keepalives
                data = line[5:].strip()
                if data == "[DONE]":
                    yield "done", {"stop_reason": "truncated" if finish == "length" else "complete",
                                   "prompt_tokens": usage.get("prompt_tokens"),
                                   "reply_tokens": usage.get("completion_tokens")}
                    return
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise BackendError("protocol_error", f"The server sent a data line that is not JSON: {data[:80]!r}") from exc
                if not isinstance(obj, dict):
                    raise BackendError("protocol_error", f"The server sent an unexpected data line: {data[:80]!r}")
                if "error" in obj:
                    raise BackendError("protocol_error", f"The server reported an error: {obj['error']}")
                usage = obj.get("usage") or usage
                for choice in obj.get("choices") or []:  # the usage chunk has no choices
                    finish = choice.get("finish_reason") or finish
                    text = (choice.get("delta") or {}).get("content")
                    if text:
                        yield "text", text
        except BackendError as exc:
            if exc.reason == "http_error" and exc.status == 400 and "context" in exc.detail.lower():
                raise BackendError("context_exceeded", "The conversation is longer than the model's "
                                   f"context: {exc.detail[:200]}", status=400, detail=exc.detail) from exc
            raise
