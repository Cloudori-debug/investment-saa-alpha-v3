"""Human-readable report formatting — avoid None% and buy-like shadow labels."""
from __future__ import annotations

import math
from typing import Any


def fmt_pct(value: Any, *, na: str = "N/A", decimals: int = 1) -> str:
    if value is None:
        return na
    if isinstance(value, str):
        if value.strip().lower() in {"", "none", "null", "nan"}:
            return na
        try:
            value = float(value)
        except ValueError:
            return value
    try:
        f = float(value)
    except (TypeError, ValueError):
        return na
    if math.isnan(f):
        return na
    return f"{f:.{decimals}f}"


def fmt_pct_with_suffix(value: Any, *, na: str = "N/A", decimals: int = 1) -> str:
    label = fmt_pct(value, na=na, decimals=decimals)
    if label == na:
        return na
    return f"{label}%"


def fmt_rate_pct(value: Any, *, closed_count: int = 0, na: str = "insufficient sample") -> str:
    if closed_count <= 0:
        return na
    return fmt_pct(value, na=na)


def fmt_rate_pct_display(value: Any, *, closed_count: int = 0, na: str = "insufficient sample") -> str:
    label = fmt_rate_pct(value, closed_count=closed_count, na=na)
    if label == na:
        return na
    return f"{label}%"


def shadow_opportunity_action_label(allowed_action: str) -> str:
    """Display label for Opportunity / Early Alpha shadow rows — not execution permission."""
    action = str(allowed_action or "").strip()
    if action == "watch":
        return "shadow_watch — execution prohibited"
    if action.startswith("pilot_entry_"):
        pct = action.replace("pilot_entry_", "").replace("_", "")
        return f"shadow_pilot_candidate_{pct}pct_of_target — execution prohibited"
    if action == "confirmation_candidate":
        return "shadow_confirmation_candidate — execution prohibited"
    return f"{action} — shadow only"


def is_planner_trade_action(action: str) -> bool:
    return action in {
        "Wait", "Hold", "Park", "Replace", "Review-only",
        "No trade", "Stop-buy", "Risk defense", "BuyCandidate",
    }
