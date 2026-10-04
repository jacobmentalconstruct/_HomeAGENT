"""Owns the configured backends: lists their models and resolves a `backend_id:model` choice."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..config import Config
from .backend import Backend
from .errors import BackendError, UnknownModelChoice
from .llamacpp import LlamaCppBackend
from .ollama import OllamaBackend
from .transport import Transport

_ADAPTERS = {"ollama": OllamaBackend, "llamacpp": LlamaCppBackend}


@dataclass(frozen=True)
class ModelEntry:
    """One model, or a backend that could not be listed (`available` is False and `reason` says why)."""
    backend_id: str
    model: str | None
    available: bool
    reason: str = ""
    message: str = ""
    chat: bool = True  # False for models that cannot chat, such as embedding models

    @property
    def choice(self) -> str | None:
        return f"{self.backend_id}:{self.model}" if self.model else None


class ModelRegistry:
    def __init__(self, backends: list[Backend], default: str = "", persist: Callable[[str], None] | None = None):
        self.backends = {b.config.id: b for b in backends}
        self.default = default  # the model new devices start with; the user can change it from the page
        self._persist = persist

    @classmethod
    def from_config(cls, config: Config, persist: Callable[[str], None] | None = None) -> ModelRegistry:
        transport = Transport(config.timeouts)
        return cls([_ADAPTERS[b.kind](b, transport, config.num_ctx, config.max_reply_tokens, config.keep_alive)
                    for b in config.backends], config.default_model, persist)

    def loaded(self) -> dict[str, list[dict] | str]:
        """What each backend holds in memory now. A backend that cannot be asked reports why, as text."""
        result: dict[str, list[dict] | str] = {}
        for backend_id, backend in self.backends.items():
            try:
                result[backend_id] = backend.loaded_models()
            except BackendError as exc:
                result[backend_id] = f"{exc.reason}: {exc.message}"
        return result

    def unload_all(self) -> dict[str, list[str] | str]:
        """Ask every backend to free its model memory. A backend that fails reports why instead of a list."""
        result: dict[str, list[str] | str] = {}
        for backend_id, backend in self.backends.items():
            try:
                result[backend_id] = backend.unload_all()
            except BackendError as exc:
                result[backend_id] = f"{exc.reason}: {exc.message}"
        return result

    def list_models(self) -> list[ModelEntry]:
        """List every backend in parallel, so the whole call takes at most the listing timeout.

        A backend that fails appears as an unavailable entry; it is never silently dropped."""
        def one(backend: Backend) -> list[ModelEntry]:
            try:
                names = backend.list_models()
                with ThreadPoolExecutor(max_workers=max(1, min(8, len(names)))) as pool:  # one question per model
                    chat_flags = list(pool.map(backend.is_chat, names))
                return [ModelEntry(backend.config.id, name, True, chat=flag) for name, flag in zip(names, chat_flags)]
            except BackendError as exc:
                return [ModelEntry(backend.config.id, None, False, exc.reason, exc.message)]

        if not self.backends:
            return []
        with ThreadPoolExecutor(max_workers=len(self.backends)) as pool:
            return [entry for group in pool.map(one, self.backends.values()) for entry in group]

    def set_default(self, choice: str) -> str:
        """Make `choice` the default model. It must exist now and be able to chat. Raises UnknownModelChoice."""
        backend, model = self.resolve(choice)
        if model not in backend.list_models():
            raise UnknownModelChoice(f"'{choice}' is not available right now.")
        if not backend.is_chat(model):
            raise UnknownModelChoice(f"'{choice}' is not a chat model.")
        if self._persist:
            self._persist(choice)  # saved first, so a failed save leaves the old default in force
        self.default = choice
        return choice

    def resolve(self, choice: str) -> tuple[Backend, str]:
        backend_id, colon, model = choice.partition(":")
        if not colon or not model:
            raise UnknownModelChoice(f"'{choice}' is not a model choice; use backend_id:model.")
        backend = self.backends.get(backend_id)
        if backend is None:
            raise UnknownModelChoice(f"No backend '{backend_id}'. Configured: {', '.join(self.backends) or 'none'}.")
        return backend, model
