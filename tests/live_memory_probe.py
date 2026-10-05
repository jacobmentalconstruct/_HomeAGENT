"""Live memory probe against a real Ollama (not part of the unit suite; it needs Ollama running).

    python -m tests.live_memory_probe [--model NAME] [--store chroma|sqlite] [--backlog N]

--backlog N seeds N turns, lets the startup catch-up run in the background, retrieves after about
0.5 s, and prints how long retrieve() took, what served it, and how long the whole catch-up took.
A timing is evidence about this machine, not a pass or fail.

Set AGENT_HARNESS_BLOCK_MODULES=chromadb to simulate Chroma being absent. Use a model name that is not
installed to simulate an unavailable embedding model. Prints memory status and what retrieval used.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path

from tests import support  # noqa: F401
from agent_harness.app import build_app
from agent_harness.locations import Locations

TURNS = [("turn.user", "USER", "Where is my home?"),
         ("turn.assistant", "AGENT", "Your home is in Cedar Rapids."),
         ("turn.user", "USER", "What colour is my office door?"),
         ("turn.assistant", "AGENT", "The office door is blue.")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nomic-embed-text")
    parser.add_argument("--store", default="chroma", choices=["chroma", "sqlite"])
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--backlog", type=int, default=0, help="seed this many turns and time the catch-up")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        loc = Locations(Path(tmp))
        loc.ensure()
        loc.config_file.write_text(json.dumps({
            "token": "t" * 32, "host": "127.0.0.1",
            "backends": [{"id": "ollama", "kind": "ollama", "url": args.url}],
            "memory": {"enabled": True, "store": args.store, "embedding_model": args.model}}))
        seeding = build_app(loc)  # without memory: the log is written, nothing is indexed
        turns = TURNS if not args.backlog else [
            ("turn.user" if i % 2 == 0 else "turn.assistant", "USER" if i % 2 == 0 else "AGENT",
             f"Turn {i}: the home number is {i}, near Cedar Rapids.") for i in range(args.backlog)]
        for index in range(0, len(turns), 2):
            for kind, actor, text in turns[index:index + 2]:
                seeding.events.append(kind, actor, {"text": text, "generation_id": f"g{index}"}, "c1")
        seeding.close()
        began = time.monotonic()
        app = build_app(loc, with_memory=True)
        try:
            if args.backlog:
                time.sleep(0.5)
                asked = time.monotonic()
                found = app.memory.retrieve("Where do I live?", "c1", app.events.read())
                took = time.monotonic() - asked
                during = app.memory.status()
                for thread in list(app.memory._threads):
                    thread.join(600)
                caught_up = time.monotonic() - began
                again = app.memory.retrieve("Where do I live?", "c1", app.events.read())
                print(json.dumps({
                    "backlog_turns": args.backlog, "retrieve_seconds": round(took, 3),
                    "served_by": sorted({item["method"] for item in found}),
                    "indexed_when_asked": {"vector": during["indexed"], "lexical": during["lexical_indexed"]},
                    "catch_up_seconds": round(caught_up, 2),
                    "after": {"tier": app.memory.status()["tier"], "state": app.memory.status()["state"],
                              "methods": sorted({item["method"] for item in again})}}, indent=2))
                return 0
            for thread in list(app.memory._threads):
                thread.join(120)
            found = app.memory.retrieve("Where do I live?", "c1", app.events.read())
            print(json.dumps({"status": app.memory.status(), "methods": [item["method"] for item in found],
                              "top": found[0]["content"] if found else None}, indent=2))
        finally:
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
