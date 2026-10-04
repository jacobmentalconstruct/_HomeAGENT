"""Ollama protocol: `/api/tags` and newline-delimited JSON from `/api/chat`."""

from __future__ import annotations

import json
from collections.abc import Iterator

from .backend import Backend, ChatStream
from .errors import BackendError


class OllamaBackend(Backend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._capabilities: dict[str, list[str]] = {}

    def is_chat(self, model: str) -> bool:
        """Ollama reports what each model can do; embedding-only models lack "completion"."""
        if model not in self._capabilities:
            try:
                info = self.transport.post_json(self.config.url, "/api/show", {"model": model})
            except BackendError:
                return True
            caps = info.get("capabilities")
            if not isinstance(caps, list):
                return True
            self._capabilities[model] = caps
        return "completion" in self._capabilities[model]

    def loaded_models(self) -> list[dict]:
        data = self.transport.get_json(self.config.url, "/api/ps").get("models", [])
        return [{"name": item["name"], "size": int(item.get("size_vram") or item.get("size") or 0)}
                for item in data if isinstance(item, dict) and "name" in item]

    def unload_all(self) -> list[str]:
        names = [item["name"] for item in self.loaded_models()]
        released = []
        for name in names:  # keep_alive 0 asks Ollama to drop the model from memory now
            try:
                self.transport.post_json(self.config.url, "/api/generate", {"model": name, "keep_alive": 0, "stream": False})
                released.append(name)
            except BackendError:
                continue  # one model that will not unload must not leave the others in memory
        return released

    def list_models(self) -> list[str]:
        data = self.transport.get_json(self.config.url, "/api/tags")
        try:
            return sorted(item["name"] for item in data["models"])
        except (KeyError, TypeError) as exc:
            raise BackendError("protocol_error", "Ollama's model list has an unexpected shape.") from exc

    def chat(self, model: str, messages: list[dict], options: dict | None = None) -> ChatStream:
        sent = {"num_ctx": self.num_ctx, "num_predict": self._cap(options)}
        if options and "temperature" in options:
            sent["temperature"] = options["temperature"]
        # Thinking is off unless asked for: replies start sooner without it.
        payload = {"model": model, "messages": messages, "stream": True, "options": sent,
                   "think": bool((options or {}).get("think", False)), "keep_alive": self.keep_alive}
        return ChatStream(self._events(payload))

    def _events(self, payload: dict) -> Iterator[tuple[str, object]]:
        for line in self.transport.stream_lines(self.config.url, "/api/chat", payload):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BackendError("protocol_error", f"Ollama sent a line that is not JSON: {line[:80]!r}") from exc
            if not isinstance(obj, dict):
                raise BackendError("protocol_error", f"Ollama sent an unexpected line: {line[:80]!r}")
            if "error" in obj:
                raise BackendError("protocol_error", f"Ollama reported an error: {obj['error']}")
            text = (obj.get("message") or {}).get("content", "")
            if text:
                yield "text", text
            if obj.get("done"):
                yield "done", {"stop_reason": "truncated" if obj.get("done_reason") == "length" else "complete",
                               "prompt_tokens": obj.get("prompt_eval_count"),
                               "reply_tokens": obj.get("eval_count")}
                return
