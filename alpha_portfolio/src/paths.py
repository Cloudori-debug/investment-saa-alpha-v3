from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_paths(root: Path | None = None) -> dict[str, Path]:
    base = root or project_root()
    return {
        "project": base,
        "config": base / "config",
        "raw": base / "data" / "raw",
        "input": base / "data" / "input",
        "output": base / "data" / "output",
        "state": base / "data" / "state",
    }
