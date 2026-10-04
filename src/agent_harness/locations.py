"""Repo-relative paths. The one place that knows where things live."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Locations:
    root: Path

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    @property
    def config_file(self) -> Path:
        return self.runtime / "config.json"

    @property
    def database(self) -> Path:
        return self.runtime / "harness.sqlite3"

    def ensure(self) -> None:
        self.runtime.mkdir(parents=True, exist_ok=True)


def repo_locations() -> Locations:
    return Locations(Path(__file__).resolve().parents[2])
