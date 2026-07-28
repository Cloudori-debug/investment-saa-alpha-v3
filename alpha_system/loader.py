"""Load and validate alpha_system YAML config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from alpha_system.schema import AlphaSystemConfig

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "alpha_system.yaml"


def load_raw_yaml(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG_PATH
    with cfg_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {cfg_path}")
    return data


def load_config(path: Path | None = None) -> AlphaSystemConfig:
    return AlphaSystemConfig.model_validate(load_raw_yaml(path))
