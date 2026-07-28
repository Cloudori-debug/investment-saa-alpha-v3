from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name).strip().lower())


def build_name_ticker_map(universe_path: Path) -> dict[str, str]:
    if not universe_path.exists():
        return {}
    df = pd.read_csv(universe_path, dtype=str)
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        name = str(row.get("name", "")).strip()
        if not ticker or not name:
            continue
        out[_norm_name(name)] = ticker
    return out


def resolve_ticker(name: str, name_map: dict[str, str], overrides: dict[str, str] | None = None) -> str:
    if overrides and name in overrides:
        return str(overrides[name]).zfill(6)
    key = _norm_name(name)
    if key in name_map:
        return name_map[key]
    # 부분 매칭 (홀딩스 등)
    for k, t in name_map.items():
        if key in k or k in key:
            return t
    return ""
