"""Shared test setup: put src/ on the path; block modules to test an absent dependency.

Two ways to make a module absent, one pattern: set AGENT_HARNESS_BLOCK_MODULES=name[,name] for a whole
run (or a subprocess), or use `with blocked_modules("name"):` for one test. Both install a meta-path finder
that raises ModuleNotFoundError, so code under test sees a real ImportError.
"""

import contextlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _matches(name, names):
    return any(name == n or name.startswith(n + ".") for n in names)


class BlockedFinder:
    """Modern (PEP 451) meta-path finder; works on Python 3.4+ including 3.12+."""

    def __init__(self, names, label):
        self.names, self.label = list(names), label

    def find_spec(self, fullname, path, target=None):
        if _matches(fullname, self.names):
            raise ModuleNotFoundError(f"{fullname} blocked ({self.label})")
        return None


@contextlib.contextmanager
def blocked_modules(*names):
    """Hide modules (and their submodules) for the duration of the block; restore them after."""
    finder = BlockedFinder(names, "blocked_modules")
    evicted = {k: sys.modules.pop(k) for k in list(sys.modules) if _matches(k, names)}
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        for key in [k for k in sys.modules if _matches(k, names)]:
            del sys.modules[key]
        sys.modules.update(evicted)


_BLOCK = os.environ.get("AGENT_HARNESS_BLOCK_MODULES", "")
if _BLOCK:
    _names = [n.strip() for n in _BLOCK.split(",") if n.strip()]
    for _k in [k for k in sys.modules if _matches(k, _names)]:
        del sys.modules[_k]
    sys.meta_path.insert(0, BlockedFinder(_names, f"AGENT_HARNESS_BLOCK_MODULES={_BLOCK}"))
