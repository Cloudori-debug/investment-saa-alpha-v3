from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.csv_utils import read_csv_optional


def load_output_csv(output_dir: Path, name: str, *, dtype: dict | type | None = None) -> pd.DataFrame | None:
    path = output_dir / name
    kwargs = {"dtype": dtype} if dtype else {}
    return read_csv_optional(path, **kwargs)


def load_output_json(output_dir: Path, name: str) -> dict | None:
    path = output_dir / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_markdown(output_dir: Path, name: str) -> str | None:
    path = output_dir / name
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
