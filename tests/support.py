"""Shared test setup: put src/ on the path; optionally block modules."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_BLOCK = os.environ.get("AGENT_HARNESS_BLOCK_MODULES", "")
if _BLOCK:
    _names = [n.strip() for n in _BLOCK.split(",") if n.strip()]

    class _BlockedFinder:
        """Modern (PEP 451) meta-path finder; works on Python 3.4+ including 3.12+."""

        def find_spec(self, fullname, path, target=None):
            if any(fullname == n or fullname.startswith(n + ".") for n in _names):
                raise ModuleNotFoundError(
                    f"{fullname} blocked by AGENT_HARNESS_BLOCK_MODULES={_BLOCK}")
            return None

    for _k in [k for k in sys.modules
               if any(k == n or k.startswith(n + ".") for n in _names)]:
        del sys.modules[_k]

    sys.meta_path.insert(0, _BlockedFinder())
