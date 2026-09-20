from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_paths(root: Path | None = None, *, book: str = "KOSPI") -> dict[str, Path]:
    base = root or project_root()
    if str(book or "KOSPI").upper() == "KOSDAQ":
        data = base / "data" / "books" / "kosdaq"
    else:
        data = base / "data"
    return {
        "project": base,
        "config": base / "config",
        "raw": data / "raw",
        "input": data / "input",
        "output": data / "output",
        "state": data / "state",
    }
