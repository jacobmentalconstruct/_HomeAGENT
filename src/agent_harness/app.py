"""Composition root: assembles the application. It implements no domain behavior."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config, load_config, update_file
from .conversation.generation import GenerationRunner
from .conversation.manager import ConversationManager
from .locations import Locations, repo_locations
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
    runner = GenerationRunner(conversations, models, system_prompt=config.system_prompt,
                              num_ctx=config.num_ctx, reply_tokens=config.max_reply_tokens)
    return App(locations, config, events, models, conversations, runner)
