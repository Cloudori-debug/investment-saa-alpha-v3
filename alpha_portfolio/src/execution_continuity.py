"""Shareholder-return execution continuity (CECS execution → SR4).

Maps recent payout-event quarters to 0–100 using the same rubric as
CECS execution_continuity (4/4→100 … 0/4→0).

Provenance:
  - quarters: explicit payout_event_quarters / execution_quarters_hit (0–4)
  - unit01: execution_continuity on 0–1 scale
  - score100: execution_continuity_score already 0–100
  - proxy_snapshot: interim from dividend_yield / buyback_3y / payout_ratio
    until a DART event table is wired (FASTJUSIK forbidden)
  - neutral: no signal → 50
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def quarters_hit_to_score(quarters_hit: int) -> float:
    """CECS rubric: n/4 quarters with dividend/buyback/cancel event."""
    n = max(0, min(4, int(quarters_hit)))
    return float(n) * 25.0


def _to_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def resolve_execution_continuity(row: pd.Series | dict[str, Any]) -> tuple[float, str]:
    """Return (score 0–100, provenance tag)."""
    get = row.get if hasattr(row, "get") else lambda k, default=None: row[k] if k in row else default

    for key in ("execution_quarters_hit", "payout_event_quarters", "payout_quarters_hit"):
        raw = get(key)
        n = _to_float(raw)
        if n is not None:
            return quarters_hit_to_score(int(round(n))), "quarters"

    score100 = _to_float(get("execution_continuity_score"))
    if score100 is not None:
        return max(0.0, min(100.0, score100)), "score100"

    unit = _to_float(get("execution_continuity"))
    if unit is not None:
        # Accept 0–1 CECS input or accidental 0–100
        if unit <= 1.0:
            return max(0.0, min(100.0, unit * 100.0)), "unit01"
        return max(0.0, min(100.0, unit)), "unit01"

    # Interim proxy from shareholder snapshot (documented; not full DART 4Q)
    hits = 0
    div = _to_float(get("dividend_yield"))
    if div is not None and div > 0:
        hits += 2
    if _truthy(get("buyback_3y")):
        hits += 1
    payout = _to_float(get("payout_ratio"))
    if payout is not None and 10.0 <= payout <= 80.0:
        hits += 1
    if hits <= 0:
        return 50.0, "neutral"
    return quarters_hit_to_score(min(4, hits)), "proxy_snapshot"
