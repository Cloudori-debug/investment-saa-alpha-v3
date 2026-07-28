from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from src.decision.shadow_performance import (
    _load_price_history,
    _row_on_or_before,
    add_business_days,
)
from src.alpha.benchmark_data import load_combined_prices, ticker_return_mtd


FORWARD_HORIZONS = (5, 20, 60, 120)


def _forward_return_combined(
    prices: pd.DataFrame,
    ticker: str,
    from_date: str,
    business_days: int,
) -> float | None:
    from src.decision.shadow_performance import _pct_change

    norm = ticker.zfill(6) if ticker.isdigit() else ticker
    sub = prices[prices["ticker"] == norm].sort_values("date")
    if sub.empty:
        return None
    start = _row_on_or_before(sub, from_date)  # type: ignore[arg-type]
    if start is None:
        return None
    target = add_business_days(from_date, business_days)
    if not target:
        return None
    end = _row_on_or_before(sub, target)
    if end is None or end["date"] <= start["date"]:
        return None
    return _pct_change(float(end["close"]), float(start["close"]))


def enrich_gate_opportunity_cost_csv(path: Path, data_dir: Path) -> int:
    """과거 gate 차단 행에 forward return 보강 — 실행 변경 없음."""
    if not path.exists():
        return 0
    prices = load_combined_prices(data_dir)
    if prices.empty:
        prices = _load_price_history(data_dir)
    if prices.empty:
        return 0

    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    for h in FORWARD_HORIZONS:
        col = f"forward_return_{h}d"
        if col not in fieldnames:
            fieldnames.append(col)
    if "gate_effect" not in fieldnames:
        fieldnames.append("gate_effect")

    updated = 0
    for row in rows:
        as_of = row.get("date", "")
        ticker = row.get("ticker", "")
        if not as_of or not ticker:
            continue
        for h in FORWARD_HORIZONS:
            col = f"forward_return_{h}d"
            if row.get(col):
                continue
            target = add_business_days(as_of, h)
            if not target or target > today:
                continue
            ret = _forward_return_combined(prices, ticker, as_of, h)
            if ret is not None:
                row[col] = str(ret)
                updated += 1
        fr20 = row.get("forward_return_20d")
        if fr20 and not row.get("gate_effect"):
            val = float(fr20)
            if val > 0:
                row["gate_effect"] = "missed_upside"
            elif val < 0:
                row["gate_effect"] = "avoided_loss"
            else:
                row["gate_effect"] = "neutral"

    if updated == 0:
        return 0

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return updated
