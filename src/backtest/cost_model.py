"""Alpha backtest cost model — diagnostic only (P5-C).

Does NOT change gate / policy_cap / Actual Buy Allowed / approval_bridge.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_COST_ASSUMPTIONS: dict[str, Any] = {
    "commission_bps": 15,
    "slippage_bps": 20,
    "securities_tx_tax_bps": 18,
    "typical_holding_days": 63,
    "note": "placeholder assumptions — confirm with operator before use",
}

# Sample-size quality labels (calendar/trading dates used in lite backtest)
QUALITY_INSUFFICIENT_MAX = 59
QUALITY_PRELIMINARY_MAX = 179


def load_cost_assumptions(path: Path | None = None) -> dict[str, Any]:
    """Load YAML assumptions; fall back to defaults. Never raises."""
    out = dict(DEFAULT_COST_ASSUMPTIONS)
    if path is None or not path.exists():
        out["source"] = "defaults"
        return out
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        out["source"] = "defaults_load_error"
        return out
    if not isinstance(raw, dict):
        out["source"] = "defaults_invalid_yaml"
        return out
    for key in ("commission_bps", "slippage_bps", "securities_tx_tax_bps", "typical_holding_days"):
        if key in raw and raw[key] is not None:
            try:
                out[key] = float(raw[key])
            except (TypeError, ValueError):
                pass
    if raw.get("note"):
        out["note"] = str(raw["note"])
    out["source"] = str(path)
    return out


def round_trip_cost_bps(assumptions: dict[str, Any] | None = None) -> float:
    a = assumptions or DEFAULT_COST_ASSUMPTIONS
    return float(
        float(a.get("commission_bps") or 0)
        + float(a.get("slippage_bps") or 0)
        + float(a.get("securities_tx_tax_bps") or 0)
    )


def apply_round_trip_cost(
    gross_return_pct: float,
    holding_days: int,
    assumptions: dict[str, Any] | None = None,
) -> float:
    """Deduct round-trip costs from a gross return expressed in percent points.

    Example: gross 2.0 (%), costs 53 bps → net 1.47.
    holding_days is kept for API compatibility / future turnover scaling;
    lite backtest currently applies a full round-trip once (return_3m proxy).
    """
    del holding_days  # reserved — do not silently prorate without a turnover model
    cost_pct = round_trip_cost_bps(assumptions) / 100.0  # bps → percent points
    return round(float(gross_return_pct) - cost_pct, 6)


def apply_round_trip_cost_fraction(
    gross_return_fraction: float,
    holding_days: int,
    assumptions: dict[str, Any] | None = None,
) -> float:
    """Same as apply_round_trip_cost but inputs/outputs are fractions (0.02 = 2%)."""
    gross_pct = float(gross_return_fraction) * 100.0
    net_pct = apply_round_trip_cost(gross_pct, holding_days, assumptions)
    return round(net_pct / 100.0, 8)


def sample_quality_label(dates_used: int) -> str:
    n = int(dates_used or 0)
    if n <= QUALITY_INSUFFICIENT_MAX:
        return "insufficient"
    if n <= QUALITY_PRELIMINARY_MAX:
        return "preliminary"
    return "provisional"


def sample_quality_banner(quality: str) -> str:
    q = str(quality or "insufficient")
    if q == "insufficient":
        return "예측력 판단 불가 — 참고용"
    if q == "preliminary":
        return "예비 검증 — 확정 아님"
    return "잠정 검증 (확정된 알파 아님)"


__all__ = [
    "DEFAULT_COST_ASSUMPTIONS",
    "apply_round_trip_cost",
    "apply_round_trip_cost_fraction",
    "load_cost_assumptions",
    "round_trip_cost_bps",
    "sample_quality_banner",
    "sample_quality_label",
]
