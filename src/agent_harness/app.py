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
        backend = models.backends[config.memory.embedding_backend]
        memory = ConversationMemory(
            enabled=True, path=locations.runtime / "memory",
            identity=f"{config.memory.embedding_backend}:{config.memory.embedding_model}",
            top_k=config.memory.top_k, embed=lambda texts: backend.embed(config.memory.embedding_model, texts),
            store_kind=config.memory.store, strict=config.memory.strict)
    runner = GenerationRunner(conversations, models, system_prompt=config.system_prompt,
                              num_ctx=config.num_ctx, reply_tokens=config.max_reply_tokens, memory=memory)
    return App(locations, config, events, models, conversations, runner, memory)
