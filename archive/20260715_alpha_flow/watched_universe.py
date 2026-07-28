"""Watched-universe ticker resolution for flow refresh (not full market)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

MAX_WATCHED_TICKERS_DEFAULT = 80


def _zfill_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _merge_ticker(merged: dict[str, dict[str, str]], ticker: str, name: str = "") -> None:
    tk = _zfill_ticker(ticker)
    if not tk or tk.upper() == "CASH":
        return
    merged.setdefault(tk, {"ticker": tk, "name": name or merged.get(tk, {}).get("name", tk)})
    if name:
        merged[tk]["name"] = name


def _from_csv(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    if not path.exists():
        return []
    out: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            tk = _zfill_ticker(row.get("ticker", ""))
            if tk:
                out.append({"ticker": tk, "name": str(row.get("name") or tk)})
            if limit and len(out) >= limit:
                break
    return out


def resolve_watched_universe_tickers(
    data_dir: Path,
    output_dir: Path,
    *,
    max_tickers: int = MAX_WATCHED_TICKERS_DEFAULT,
    scored_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Priority: held/target → signal board → v1 candidates → v2 top30/final → v2 scored top."""
    merged: dict[str, dict[str, str]] = {}

    try:
        from src.data_loader import load_positions, load_target_portfolio

        for row in load_positions(data_dir / "positions.csv"):
            if float(row.quantity or 0) > 0 and row.asset_group == "kr_alpha":
                _merge_ticker(merged, row.ticker, row.name or "")
        for row in load_target_portfolio(data_dir / "target_portfolio.csv"):
            if row.asset_group == "kr_alpha":
                _merge_ticker(merged, row.ticker, row.name or "")
    except Exception:
        pass

    for item in _from_csv(output_dir / "alpha_signal_board.csv"):
        _merge_ticker(merged, item["ticker"], item.get("name", ""))

    for item in _from_csv(output_dir / "alpha_candidates.csv", limit=30):
        _merge_ticker(merged, item["ticker"], item.get("name", ""))

    for item in _from_csv(output_dir / "alpha_top10_scored.csv", limit=10):
        _merge_ticker(merged, item["ticker"], item.get("name", ""))

    for fname in ("alpha_v2_final_candidates.csv", "alpha_v2_top30.csv"):
        for item in _from_csv(output_dir / fname):
            _merge_ticker(merged, item["ticker"], item.get("name", ""))

    if scored_rows:
        ranked = sorted(
            scored_rows,
            key=lambda r: float(r.get("total_score_v2_shadow") or r.get("total_score_v1") or 0),
            reverse=True,
        )
        for row in ranked[:30]:
            _merge_ticker(merged, str(row.get("ticker", "")), str(row.get("name") or ""))

    if len(merged) < max_tickers:
        for item in _from_csv(output_dir / "alpha_v2_scored.csv", limit=max_tickers):
            _merge_ticker(merged, item["ticker"], item.get("name", ""))

    return list(merged.values())[:max_tickers]
