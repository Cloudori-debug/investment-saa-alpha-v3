from __future__ import annotations

from typing import Any

from src.models import PositionRow


def build_profit_sweep_candidates(
    positions: list[PositionRow],
    *,
    market_status: str,
    no_trade: bool,
) -> list[dict[str, Any]]:
    """MVP: suggest sweep from unrealized gains on kr_alpha holdings — no execution."""
    rows: list[dict[str, Any]] = []
    for pos in positions:
        if pos.asset_group != "kr_alpha":
            continue
        qty = float(pos.quantity or 0)
        if qty <= 0:
            continue
        avg = float(pos.avg_price or 0)
        current = float(pos.current_price or 0)
        if avg <= 0 or current <= 0:
            continue
        profit_pct = (current - avg) / avg * 100
        realized = qty * (current - avg)
        if realized <= 0:
            continue
        sweep = round(realized * 0.5, 0)
        reinvest = round(realized * 0.5, 0) if not no_trade and market_status != "RED" else 0.0
        rows.append({
            "ticker": pos.ticker,
            "name": pos.name,
            "realized_profit": round(realized, 0),
            "profit_pct": round(profit_pct, 2),
            "suggested_sweep_to_saa": sweep,
            "suggested_alpha_reinvest": reinvest,
            "market_status": market_status,
            "no_trade": no_trade,
            "human_approval_required": True,
        })
    return sorted(rows, key=lambda r: -float(r["realized_profit"]))
