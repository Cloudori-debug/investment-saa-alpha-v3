"""Shared helpers for Early Alpha v0.1 and Alpha Opportunity v0.2."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_refresh.price_store import normalize_ticker


def parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def load_prices_map(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / "prices.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, dict[str, Any]] = {}
    for r in df.to_dict(orient="records"):
        t = normalize_ticker(str(r.get("ticker", "")))
        if not t:
            continue
        row: dict[str, Any] = {"date": r.get("date", "")}
        for col in df.columns:
            if col in {"date", "ticker"}:
                continue
            try:
                row[col] = float(r[col]) if str(r[col]).strip() else None
            except ValueError:
                row[col] = r[col]
        out[t] = row
    return out


def load_price_history(data_dir: Path, ticker: str, n: int = 60) -> list[dict[str, Any]]:
    path = data_dir / "prices_history.csv"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if normalize_ticker(row.get("ticker", "")) == ticker:
                rows.append(row)
    return rows[-n:]


def volume_ratio(px: dict[str, Any], history: list[dict[str, Any]]) -> float | None:
    tv20 = float(px.get("trading_value_20d") or 0)
    tv60 = float(px.get("trading_value_60d") or 0)
    if tv20 > 0 and tv60 > 0:
        daily_20 = tv20 / 20.0
        daily_60 = tv60 / 60.0
        if daily_60 > 0:
            return round(daily_20 / daily_60, 2)
    if len(history) >= 5:
        try:
            recent = [float(h.get("trading_value_20d") or 0) for h in history[-5:]]
            base = [float(h.get("trading_value_20d") or 0) for h in history[:-5]]
            r_avg = sum(recent) / max(len(recent), 1)
            b_avg = sum(base) / max(len(base), 1) if base else 0
            if b_avg > 0:
                return round(r_avg / b_avg, 2)
        except (TypeError, ValueError):
            pass
    return None


def grade_from_score(total: int, thresholds: dict[str, Any]) -> str:
    if total <= int(thresholds.get("e0_max", 39)):
        return "E0"
    if total <= int(thresholds.get("e1_max", 54)):
        return "E1"
    if total <= int(thresholds.get("e2_max", 69)):
        return "E2"
    if total <= int(thresholds.get("e3_max", 84)):
        return "E3"
    return "E4"


def stop_and_invalidation(
    close: float,
    support: float | None,
    config: dict[str, Any],
) -> tuple[float | None, str]:
    if close <= 0:
        return None, "No price — stop undefined"
    pct = float((config.get("stop_rules") or {}).get("pct_below_entry", 0.07))
    stop = round(close * (1 - pct), 2)
    if support and support < close:
        stop = round(min(stop, support), 2)
    inv = (
        f"Exit if close < {stop} (-7% from entry or support break); "
        "volume fade; breakout failure; catalyst invalidated; no follow-through 3-5 sessions"
    )
    return stop, inv


def pilot_action(
    grade: str,
    stop_level: float | None,
    config: dict[str, Any],
) -> tuple[str, float, str]:
    fr = config.get("pilot_fractions") or {}
    abs_max = float(fr.get("absolute_max", 0.25))

    if grade == "E0":
        return "noise", 0.0, "No action"
    if grade == "E1":
        return "watch", 0.0, "Observe only — no pilot entry"
    if grade == "E4":
        return "confirmation_candidate", 0.0, "Escalate to Confirmation Engine"
    if stop_level is None:
        return "watch", 0.0, "stop_level missing — pilot_entry blocked"

    if grade == "E2":
        frac = min(float(fr.get("e2", 0.10)), abs_max)
        return "pilot_entry_10", frac, f"Pilot up to {frac:.0%} of target alpha weight"
    if grade == "E3":
        frac = min(float(fr.get("e3_max", 0.25)), abs_max)
        return "pilot_entry_20_25", frac, f"Pilot up to {frac:.0%} of target alpha weight"
    return "watch", 0.0, "Ungraded"
