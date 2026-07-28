from __future__ import annotations

from typing import Any

import numpy as np

from src.alpha_flow.flow_classifier import classify_flow_state
from src.alpha_v2.institutional_flow_loader import InstitutionalFlowRow
from src.alpha_v2.schemas import FLOW_SCORE_MAX, FLOW_SCORE_MIN


def _streak_direction(values: list[float | None]) -> tuple[str, int]:
    """Return (direction, days) from recent daily net values (newest last)."""
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return "neutral", 0
    direction = "buy" if cleaned[-1] >= 0 else "sell"
    days = 0
    for v in reversed(cleaned):
        if direction == "buy" and v >= 0:
            days += 1
        elif direction == "sell" and v < 0:
            days += 1
        else:
            break
    return direction, days


def _percentile_rank(values: dict[str, float], ticker: str) -> float | None:
    if ticker not in values:
        return None
    arr = np.array(list(values.values()), dtype=float)
    if len(arr) == 0:
        return None
    target = values[ticker]
    return float((arr <= target).sum() / len(arr))


def apply_flow_overlay(
    scored_rows: list[dict[str, Any]],
    flows: dict[str, InstitutionalFlowRow],
) -> list[dict[str, Any]]:
    pension_20d_map = {
        r["ticker"]: float(f.pension_net_buy_20d)
        for r in scored_rows
        for f in [flows.get(r["ticker"])]
        if f and f.pension_net_buy_20d is not None
    }
    pension_60d_map = {
        r["ticker"]: float(f.pension_net_buy_60d)
        for r in scored_rows
        for f in [flows.get(r["ticker"])]
        if f and f.pension_net_buy_60d is not None
    }

    out: list[dict[str, Any]] = []
    for row in scored_rows:
        ticker = row["ticker"]
        flow = flows.get(ticker)
        merged = dict(row)
        market_cap = float(row.get("market_cap") or 0)
        turnover = float(row.get("avg_turnover_20d") or 0)

        if not flow or flow.stale_flag:
            v1 = float(merged.get("total_score_v1") or 0)
            merged.update({
                "flow_data_stale": True,
                "pension_net_buy_20d": None,
                "pension_net_buy_60d": None,
                "foreign_net_buy_20d": None,
                "pension_streak_direction": "neutral",
                "pension_streak_days": 0,
                "pension_flow_to_market_cap": None,
                "pension_flow_to_turnover": None,
                "pension_foreign_co_buy": False,
                "pension_foreign_co_sell": False,
                "turning_buy_signal": False,
                "turning_sell_signal": False,
                "flow_confidence": "LOW",
                "flow_signal_state": "stale",
                "flow_score": 0.0,
                "buy_watch": False,
                "trim_watch": False,
                "total_score_v2_shadow": round(v1, 2),
            })
            out.append(merged)
            continue

        merged["flow_data_stale"] = False

        p20 = flow.pension_net_buy_20d or 0.0
        p60 = flow.pension_net_buy_60d or 0.0
        f20 = flow.foreign_net_buy_20d or 0.0
        p1 = flow.pension_net_buy_1d or 0.0
        f1 = flow.foreign_net_buy_1d or 0.0

        streak_vals = [flow.pension_net_buy_1d, flow.pension_net_buy_5d, flow.pension_net_buy_20d]
        streak_dir, streak_days = _streak_direction(streak_vals)

        p_rank_20 = _percentile_rank(pension_20d_map, ticker)
        p_rank_60 = _percentile_rank(pension_60d_map, ticker)

        co_buy = p20 > 0 and f20 > 0
        co_sell = p20 < 0 and f20 < 0
        turning_buy = (p20 > 0 and p60 is not None and p60 < 0) or (p1 > 0 and streak_dir == "sell")
        turning_sell = (p20 < 0 and p60 is not None and p60 > 0) or (p1 < 0 and streak_dir == "buy")

        flow_score = 0.0
        if p_rank_20 is not None and p_rank_20 >= 0.90:
            flow_score += 6.0
        if p_rank_60 is not None and p_rank_60 >= 0.90:
            flow_score += 5.0
        if streak_dir == "buy" and streak_days >= 5:
            flow_score += 4.0
        if co_buy:
            flow_score += 5.0
        if turning_buy:
            flow_score += 3.0
        if streak_dir == "sell" and streak_days >= 5:
            flow_score -= 5.0
        if co_sell:
            flow_score -= 7.0
        if turning_sell:
            flow_score -= 4.0

        flow_score = max(FLOW_SCORE_MIN, min(FLOW_SCORE_MAX, flow_score))

        state = classify_flow_state(
            pension_net_20d=p20,
            foreign_net_20d=f20,
            co_buy=co_buy,
            co_sell=co_sell,
            turning_buy=turning_buy,
            turning_sell=turning_sell,
        )

        p_to_mcap = (p20 / market_cap) if market_cap > 0 else None
        p_to_turn = (p20 / turnover) if turnover > 0 else None

        merged.update({
            "buy_watch": False,
            "trim_watch": False,
            "pension_net_buy_20d": p20,
            "pension_net_buy_60d": p60,
            "foreign_net_buy_20d": f20,
            "pension_streak_direction": streak_dir,
            "pension_streak_days": streak_days,
            "pension_flow_to_market_cap": p_to_mcap,
            "pension_flow_to_turnover": p_to_turn,
            "pension_rank_20d": p_rank_20,
            "foreign_rank_20d": _percentile_rank(
                {t: float(f.foreign_net_buy_20d or 0) for t, f in flows.items() if f.foreign_net_buy_20d is not None},
                ticker,
            ),
            "pension_foreign_co_buy": co_buy,
            "pension_foreign_co_sell": co_sell,
            "turning_buy_signal": turning_buy,
            "turning_sell_signal": turning_sell,
            "flow_confidence": "HIGH" if flow_score != 0 else "MEDIUM",
            "flow_signal_state": state,
            "flow_score": round(flow_score, 2),
        })
        v1 = float(merged.get("total_score_v1") or 0)
        merged["total_score_v2_shadow"] = round(v1 + float(merged["flow_score"]), 2)
        out.append(merged)
    return out
