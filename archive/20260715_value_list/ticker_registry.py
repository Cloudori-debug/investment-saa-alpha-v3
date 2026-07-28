from __future__ import annotations

from pathlib import Path

import yaml

from src.value_list.seed_stocks import STOCKS
from src.value_list.ticker_resolver import build_name_ticker_map, resolve_ticker


def load_integration_config(data_dir: Path) -> dict:
    path = data_dir / "hakedaka_integration.yaml"
    if not path.exists():
        return {"enabled": True}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {"enabled": True}


def load_watchlist_stocks(data_dir: Path) -> list[dict]:
    path = data_dir / "hakedaka_watchlist.yaml"
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("stocks"):
            return list(raw["stocks"])
        if isinstance(raw, list):
            return raw
    return [dict(s) for s in STOCKS]


def resolve_hakedaka_registry(data_dir: Path) -> list[dict]:
    """50종 메타 + 해석된 ticker."""
    stocks = load_watchlist_stocks(data_dir)
    name_map = build_name_ticker_map(data_dir / "universe.csv")
    overrides_path = data_dir / "hakedaka_ticker_overrides.yaml"
    overrides: dict[str, str] = {}
    if overrides_path.exists():
        raw = yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or {}
        overrides = raw.get("overrides", raw) if isinstance(raw, dict) else {}

    out: list[dict] = []
    for s in stocks:
        row = dict(s)
        t = str(row.get("ticker", "")).strip()
        if not t:
            t = resolve_ticker(str(row["name"]), name_map, overrides)
        row["ticker"] = t.zfill(6) if t else ""
        out.append(row)
    return out


def hakedaka_ticker_set(data_dir: Path) -> set[str]:
    return {str(r["ticker"]).zfill(6) for r in resolve_hakedaka_registry(data_dir) if r.get("ticker")}


def hakedaka_meta_by_ticker(data_dir: Path) -> dict[str, dict]:
    return {
        str(r["ticker"]).zfill(6): r
        for r in resolve_hakedaka_registry(data_dir)
        if r.get("ticker")
    }
