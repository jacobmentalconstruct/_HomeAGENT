"""Run the deterministic overflow document through a real local 0.5B Ollama model."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import support  # noqa: F401
from tests.overflow_fixtures import primary_document
from agent_harness.config import BackendConfig, Timeouts
from agent_harness.conversation.generation import GenerationRunner
from agent_harness.conversation.manager import ConversationManager
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.errors import BackendError
from agent_harness.models.registry import ModelRegistry
from agent_harness.models.transport import Transport
from agent_harness.store.event_store import EventStore


def main() -> int:
    text, expected_facts = primary_document()
    with tempfile.TemporaryDirectory(prefix="agent-harness-overflow-") as directory:
        store = EventStore(Path(directory) / "events.sqlite3")
        try:
            conversations = ConversationManager(store)
            conversation_id = conversations.create()
            timeouts = Timeouts(connect=5, listing=5, first_byte=90, idle=90, total=600)
            backend = OllamaBackend(BackendConfig("ol", "ollama", "http://127.0.0.1:11434"),
                                    Transport(timeouts), 2048, 256)
            try:
                for _part in backend.chat("qwen2.5:0.5b", [{"role": "user", "content": text}]):
                    pass
                raw_overflow_reason = "unexpected_success"
            except BackendError as exc:
                raw_overflow_reason = exc.reason
            runner = GenerationRunner(conversations, ModelRegistry([backend]),
                                      system_prompt=("Read the user's final Question: section and answer with only "
                                                     "the requested value. Do not quote or summarize the context."),
                                      num_ctx=2048, reply_tokens=256)
            generation = runner.send(conversation_id, text, "ol:qwen2.5:0.5b")
            if not generation.finished.wait(600):
                print(json.dumps({"state": "timeout"}))
                return 2
            snapshot = generation.snapshot()
            window = conversations.get(conversation_id)["window"] or {}
            derived = window.get("derived") or {}
            result = {
                "state": snapshot["state"],
                "raw_overflow_reason": raw_overflow_reason,
                "answer": snapshot["text"],
                "error": snapshot["error"],
                "prompt_eval_count": (snapshot["summary"] or {}).get("prompt_tokens"),
                "derived_depth": derived.get("depth"),
                "derived_contains_expected_facts": all(fact in derived.get("text", "") for fact in expected_facts),
                "derived_sources": derived.get("sources"),
            }
            print(json.dumps(result, indent=2))
            return 0 if (raw_overflow_reason == "context_exceeded" and snapshot["state"] == "done"
                         and result["derived_contains_expected_facts"]
                         and "VIOLET" in snapshot["text"]
                         and isinstance(result["prompt_eval_count"], int)) else 1
        finally:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
