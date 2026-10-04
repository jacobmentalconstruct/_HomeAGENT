"""Double-click to open the control panel (no console window). It starts the server for you."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agent_harness.interfaces.gui import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
