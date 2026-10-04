import unittest
from pathlib import Path

from tests import support  # noqa: F401
from agent_harness.memory.cartridge import ConversationMemory
from agent_harness.store.event_store import Event


class Collection:
    def __init__(self, metadata=None):
        self.metadata = metadata or {}
        self.rows = {}

    def get(self, ids=None, include=None):
        rows = [(key, value) for key, value in self.rows.items() if ids is None or key in ids]
        result = {"ids": [key for key, _ in rows], "metadatas": [value["metadata"] for _, value in rows]}
        if include and "embeddings" in include:
            result["embeddings"] = [value["embedding"] for _, value in rows]
        return result

    def upsert(self, ids, embeddings, documents, metadatas):
        for key, vector, document, metadata in zip(ids, embeddings, documents, metadatas):
            self.rows[key] = {"embedding": vector, "document": document, "metadata": metadata}

    def query(self, query_embeddings, n_results, where, include):
        query = query_embeddings[0]
        rows = [(key, row) for key, row in self.rows.items()
                if row["metadata"]["conversation_id"] == where["conversation_id"]]
        rows.sort(key=lambda pair: sum(a * b for a, b in zip(query, pair[1]["embedding"])), reverse=True)
        rows = rows[:n_results]
        return {"documents": [[row["document"] for _, row in rows]],
                "metadatas": [[row["metadata"] for _, row in rows]],
                "distances": [[0.0 for _ in rows]]}


class Client:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name, metadata):
        if not self.collection.metadata:
            self.collection.metadata = metadata
        return self.collection


def embed(texts):
    vectors = []
    for text in texts:
        lower = text.lower()
        vectors.append([1.0, 0.0] if any(word in lower for word in ("home", "cedar", "live"))
                       else [0.0, 1.0])
    return vectors


def event(seq, kind, conv, generation, text=""):
    payload = {"generation_id": generation, "text": text}
    return Event(seq, float(seq), kind, "USER" if kind == "turn.user" else "AGENT", conv, payload)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.collection = Collection()
        self.factory = lambda path: Client(self.collection)
        self.events = [
            event(1, "turn.user", "a", "g1", "Where is my home?"),
            event(2, "turn.assistant", "a", "g1", "Your home is in Cedar Rapids."),
            event(3, "turn.user", "b", "g2", "My office has a blue door."),
            event(4, "turn.assistant", "b", "g2", "The office door is blue."),
            event(5, "turn.user", "a", "g3", "unfinished request"),
        ]

    def memory(self, identity="ollama:nomic-embed-text", embedder=embed):
        return ConversationMemory(enabled=True, path=Path("unused"), identity=identity,
                                  top_k=4, embed=embedder, client_factory=self.factory)

    def test_reconcile_indexes_only_completed_turns_and_is_idempotent(self):
        memory = self.memory()
        memory.reconcile(self.events)
        memory.reconcile(self.events)
        self.assertEqual(set(self.collection.rows), {"event-1", "event-2", "event-3", "event-4"})
        self.assertEqual(memory.status()["indexed"], 4)

    def test_retrieval_is_paraphrase_friendly_and_conversation_scoped(self):
        memory = self.memory()
        found = memory.retrieve("Where do I live?", "a", self.events)
        self.assertEqual([item["content"] for item in found], ["Where is my home?", "Your home is in Cedar Rapids."])
        self.assertTrue(all(item["id"].startswith("a:") for item in found))
        self.assertEqual(memory.retrieve("Where do I live?", "missing", self.events), [])

    def test_restart_reconciles_missing_turns_from_event_log(self):
        memory = self.memory()
        memory.reconcile(self.events[:2])
        del self.collection.rows["event-2"]  # an interrupted index write
        restarted = self.memory()
        found = restarted.retrieve("home", "a", self.events)
        self.assertTrue(found)
        self.assertEqual(restarted.status()["state"], "ready")
        self.assertIn("event-2", self.collection.rows)

    def test_missing_chroma_dependency_degrades_without_blocking_the_app(self):
        memory = ConversationMemory(enabled=True, path=Path("unused"), identity="ollama:model", top_k=4,
                                    embed=embed, client_factory=lambda **kwargs: (_ for _ in ()).throw(
                                        ImportError("missing chromadb")))
        self.assertEqual(memory.status()["state"], "degraded")
        self.assertIn("requirements-rag.txt", memory.status()["error"])

    def test_embedding_identity_mismatch_is_degraded(self):
        self.memory().reconcile(self.events)
        other = self.memory(identity="ollama:other-model")
        self.assertEqual(other.status()["state"], "degraded")
        self.assertIn("different", other.status()["error"])

    def test_dimension_change_degrades_without_corrupting_index(self):
        memory = self.memory()
        memory.reconcile(self.events[:2])
        memory._embed = lambda texts: [[1.0, 2.0, 3.0] for _ in texts]
        self.assertEqual(memory.retrieve("home", "a", self.events), [])
        self.assertEqual(memory.status()["state"], "degraded")
        self.assertIn("dimensions changed", memory.status()["error"])

    def test_embedding_failure_is_visible_and_does_not_raise_into_chat(self):
        memory = self.memory(embedder=lambda texts: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertEqual(memory.retrieve("home", "a", self.events), [])
        self.assertEqual(memory.status()["state"], "degraded")

    def test_disabled_memory_does_no_index_work(self):
        memory = ConversationMemory(enabled=False, path=Path(), identity="", top_k=0,
                                    embed=lambda texts: (_ for _ in ()).throw(AssertionError()))
        self.assertEqual(memory.retrieve("anything", "a", self.events), [])
        self.assertEqual(memory.status()["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
