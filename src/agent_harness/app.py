"""Composition root: assembles the application. It implements no domain behavior."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config, load_config, update_file
from .conversation.generation import GenerationRunner
from .conversation.manager import ConversationManager
from .locations import Locations, repo_locations
from .memory.cartridge import ConversationMemory, disabled_memory
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
        if self.memory._store is not None:
            self.memory._store.close()
        self.events.close()


def build_app(locations: Locations | None = None) -> App:
    locations = locations or repo_locations()
    locations.ensure()
    config = load_config(locations.config_file)
    events = EventStore(locations.database)
    models = ModelRegistry.from_config(
        config, persist=lambda choice: update_file(locations.config_file, default_model=choice))
    conversations = ConversationManager(events)
    memory = disabled_memory()
    if config.memory.enabled:
        embed_backend_id = config.memory.embedding_backend
        backend = models.backends.get(embed_backend_id)
        if backend is None:
            memory = disabled_memory()
        else:
            embed_model = config.memory.embedding_model
            memory = ConversationMemory(
                enabled=True, path=locations.runtime / "memory",
                identity=f"{embed_backend_id}:{embed_model}",
                top_k=config.memory.top_k,
                embed=lambda texts: backend.embed(embed_model, texts),
                store_kind=config.memory.store, strict=config.memory.strict,
                model_checker=lambda: embed_model in backend.list_models())
            # Background startup catch-up: index any history not yet in the vector store.
            all_events = events.read()
            if all_events:
                memory.reconcile_in_background(all_events)
    runner = GenerationRunner(conversations, models, system_prompt=config.system_prompt,
                              num_ctx=config.num_ctx, reply_tokens=config.max_reply_tokens, memory=memory)
    return App(locations, config, events, models, conversations, runner, memory)
