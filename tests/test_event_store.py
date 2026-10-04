import tempfile
import unittest
from pathlib import Path

from tests import support  # noqa: F401
from agent_harness.store.event_store import EventStore


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "e.sqlite3"
        self.store = EventStore(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_append_assigns_increasing_seq_and_roundtrips_payload(self):
        a = self.store.append("turn", "USER", {"text": "héllo"}, "c1")
        b = self.store.append("turn", "AGENT", {"text": "hi"}, "c1")
        self.assertLess(a.seq, b.seq)
        self.assertEqual(self.store.read()[0].payload, {"text": "héllo"})
        self.assertEqual(self.store.count(), 2)

    def test_cursor_and_conversation_filter(self):
        a = self.store.append("turn", "USER", conversation_id="c1")
        self.store.append("turn", "USER", conversation_id="c2")
        c = self.store.append("turn", "AGENT", conversation_id="c1")
        self.assertEqual([e.seq for e in self.store.read(after_seq=a.seq)][-1], c.seq)
        self.assertEqual([e.seq for e in self.store.read(conversation_id="c1")], [a.seq, c.seq])

    def test_limit_pages_results(self):
        for _ in range(5):
            self.store.append("x", "SYSTEM")
        first = self.store.read(limit=2)
        rest = self.store.read(after_seq=first[-1].seq, limit=10)
        self.assertEqual((len(first), len(rest)), (2, 3))

    def test_events_survive_reopen(self):
        self.store.append("x", "SYSTEM")
        self.store.close()
        self.store = EventStore(self.path)
        self.assertEqual(self.store.count(), 1)

    def test_read_without_a_limit_returns_every_event(self):
        for i in range(600):
            self.store.append("x", "SYSTEM", {"i": i}, "c1" if i % 2 else "c2")
        self.assertEqual(len(self.store.read()), 600)
        self.assertEqual(len(self.store.read(conversation_id="c1")), 300)
        self.assertEqual(len(self.store.read(limit=10)), 10)
        self.assertEqual(self.store.read(after_seq=595)[0].seq, 596)


if __name__ == "__main__":
    unittest.main()
