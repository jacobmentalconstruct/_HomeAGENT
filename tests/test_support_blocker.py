"""Verify that the AGENT_HARNESS_BLOCK_MODULES module blocker in support.py works."""

import importlib
import os
import unittest

from tests import support  # noqa: F401 — installs blocker when env var is set

_BLOCK = os.environ.get("AGENT_HARNESS_BLOCK_MODULES", "")
_CHROMADB_BLOCKED = "chromadb" in [n.strip() for n in _BLOCK.split(",") if n.strip()]


class TestBlockerActive(unittest.TestCase):
    """Run only when AGENT_HARNESS_BLOCK_MODULES includes 'chromadb'."""

    @unittest.skipUnless(_CHROMADB_BLOCKED, "chromadb not in AGENT_HARNESS_BLOCK_MODULES")
    def test_blocked_module_raises_import_error(self):
        """Importing a blocked module must raise ImportError (ModuleNotFoundError)."""
        with self.assertRaises(ImportError):
            importlib.import_module("chromadb")

    @unittest.skipUnless(_CHROMADB_BLOCKED, "chromadb not in AGENT_HARNESS_BLOCK_MODULES")
    def test_real_chroma_ordering_test_sees_chromadb_as_absent(self):
        """With chromadb blocked, _HAS_CHROMADB must be False so TestRealChromaOrdering skips."""
        from tests.test_store_contract import _HAS_CHROMADB
        self.assertFalse(
            _HAS_CHROMADB,
            "_HAS_CHROMADB should be False when chromadb is blocked; "
            "TestRealChromaOrdering would otherwise run under a broken blocker.")


class TestBlockerInactive(unittest.TestCase):
    """Run only when the env var is not set."""

    @unittest.skipIf(_CHROMADB_BLOCKED, "chromadb blocked by AGENT_HARNESS_BLOCK_MODULES")
    def test_chromadb_importable_when_not_blocked(self):
        """When the blocker is absent and chromadb is installed, import must succeed."""
        try:
            importlib.import_module("chromadb")
        except ImportError:
            self.skipTest("chromadb not installed")
