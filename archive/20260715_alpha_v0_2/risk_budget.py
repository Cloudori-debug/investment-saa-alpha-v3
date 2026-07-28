from __future__ import annotations

from typing import Any

from src.models import PositionRow

from src.alpha_v0_2.schemas import AlphaBudgetStatus


def compute_alpha_weights(positions: list[PositionRow]) -> tuple[float, dict[str, float]]:
    total = sum(p.current_value for p in positions if p.ticker.upper() != "CASH")
    if total <= 0:
        return 0.0, {}
    by_ticker: dict[str, float] = {}
    alpha_total = 0.0
    for p in positions:
        if p.asset_group != "kr_alpha":
            continue
        w = p.current_value / total * 100
        by_ticker[p.ticker] = round(w, 2)
        alpha_total += w
    return round(alpha_total, 2), by_ticker


def score_risk_control(
    *,
    ticker: str,
    sector: str,
    weight_pct: float,
    sector_weights: dict[str, float],
    cfg: dict[str, Any],
) -> tuple[float, list[str]]:
    rb = cfg.get("risk_budget", {})
    reasons: list[str] = []
    points = 10.0

    hard_max = float(rb.get("single_name_hard_max_pct", 8.0))
    core_max = float(rb.get("single_name_core_max_pct", 5.0))
    if weight_pct > hard_max:
        points -= 4
        reasons.append("single_name_hard_max")
    elif weight_pct > core_max:
        points -= 2
        reasons.append("single_name_above_core")

    sector_max = float(rb.get("sector_max_pct", 28.0))
    sec_w = sector_weights.get(sector, 0.0) + weight_pct
    if sec_w > sector_max:
        points -= 3
        reasons.append("sector_cap_pressure")

    return max(0.0, points), reasons


def portfolio_risk_budget(
    positions: list[PositionRow],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    rb = cfg.get("risk_budget", {})
    alpha_w, _ = compute_alpha_weights(positions)
    target = float(rb.get("alpha_target_pct", 12.5))
    max_pct = float(rb.get("alpha_max_pct", 22.5))
    tol = float(rb.get("overweight_tolerance_pct", 1.0))

    status: AlphaBudgetStatus = "OK"
    if alpha_w > max_pct + tol:
        status = "OVERWEIGHT"
    elif alpha_w < target - 5:
        status = "UNDERWEIGHT"

    new_allowed = status != "OVERWEIGHT" and alpha_w <= max_pct
    allowed_action = "hold_or_trim_only" if status == "OVERWEIGHT" else "research_only"

    return {
        "alpha_budget_status": status,
        "current_alpha_weight_pct": alpha_w,
        "weight_basis": "investable_assets_ex_cash",
        "new_alpha_buy_allowed": new_allowed,
        "allowed_action": allowed_action,
        "alpha_target_pct": target,
        "alpha_max_pct": max_pct,
    }
