"""Composition root: assembles the application. It implements no domain behavior."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config, load_config, update_file
from .conversation.generation import GenerationRunner
from .conversation.manager import ConversationManager
from .locations import Locations, repo_locations
from .memory.cartridge import ConversationMemory, disabled_memory
from .models.ollama import has_model
from .models.registry import ModelRegistry
from .store.event_store import EventStore


@dataclass
class App:
    locations: Locations
    config: Config
    events: EventStore
    models: ModelRegistry
    conversations: ConversationManager
    runner: GenerationRunner
    memory: ConversationMemory

    def close(self) -> None:
        self.memory.close()
        self.events.close()


def _build_memory(config: Config, models: ModelRegistry, locations: Locations,
                  events: EventStore) -> ConversationMemory:
    settings = config.memory
    backend = models.backends.get(settings.embedding_backend)
    common = dict(enabled=True, path=locations.runtime / "memory", top_k=settings.top_k,
                  store_kind=settings.store, strict=settings.strict,
                  identity=f"{settings.embedding_backend}:{settings.embedding_model}")
    if backend is None:
        memory = ConversationMemory(
            embed=lambda texts: [], embed_fault=(
                "embedding_backend_missing",
                f"add an Ollama backend with id '{settings.embedding_backend}' or set "
                "memory.embedding_backend to a configured one",
                f"No configured backend named '{settings.embedding_backend}' to make embeddings."),
            **common)
    else:
        model = settings.embedding_model
        memory = ConversationMemory(
            embed=lambda texts: backend.embed(model, texts),
            model_checker=lambda: has_model(model, backend.list_models()), **common)
    memory.reconcile_in_background(events.read())  # catch up on history without delaying startup
    return memory


def build_app(locations: Locations | None = None, *, with_memory: bool = False) -> App:
    """Assemble the app. Only the server process (`serve`) passes with_memory=True: opening the memory
    stores and indexing is that process's job, so other commands never touch them."""
    locations = locations or repo_locations()
    locations.ensure()
    config = load_config(locations.config_file)
    events = EventStore(locations.database)
    models = ModelRegistry.from_config(
        config, persist=lambda choice: update_file(locations.config_file, default_model=choice))
    conversations = ConversationManager(events)
    memory = (_build_memory(config, models, locations, events)
              if with_memory and config.memory.enabled else disabled_memory())
    runner = GenerationRunner(conversations, models, system_prompt=config.system_prompt,
                              num_ctx=config.num_ctx, reply_tokens=config.max_reply_tokens, memory=memory,
                              overflow_fallback=config.overflow_fallback)
    return App(locations, config, events, models, conversations, runner, memory)
