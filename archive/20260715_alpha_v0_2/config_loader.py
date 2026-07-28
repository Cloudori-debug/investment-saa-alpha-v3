from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import load_yaml


def load_alpha_v02_config(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "alpha_v0_2.yaml"
    if not path.exists():
        raise FileNotFoundError(f"alpha_v0_2 config missing: {path}")
    return load_yaml(path)


def clamp_score(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, value)), 2)
