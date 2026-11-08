"""Shadow cost helpers — wraps src.backtest.cost_model (diagnostic only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.backtest.cost_model import (
    load_cost_assumptions,
    round_trip_cost_bps,
)


def one_way_cost_bps(assumptions: dict[str, Any] | None = None) -> float:
    """Approximate one-way cost as half round-trip (commission+slippage+tax/2)."""
    a = assumptions or load_cost_assumptions(None)
    # Round-trip includes sell tax once; one-way ≈ (comm+slip)/2 style is wrong.
    # Use: (commission + slippage) for each side + tax only on sells.
    # For turnover-based model we charge full round_trip * one_way_turnover
    # where turnover is already 0.5*L1 — equivalent to applying RT on two-way.
    return float(round_trip_cost_bps(a))


def load_shadow_cost_bps(root: Path | None = None) -> tuple[float, dict[str, Any]]:
    path = None
    if root is not None:
        cand = Path(root) / "data" / "cost_assumptions.yaml"
        if cand.exists():
            path = cand
    assumptions = load_cost_assumptions(path)
    # step_day multiplies one-way turnover by this bps.
    # turnover_one_way = 0.5 * sum|dw| so RT_bps * turnover ≈ cost on traded notional.
    return float(round_trip_cost_bps(assumptions)), assumptions
