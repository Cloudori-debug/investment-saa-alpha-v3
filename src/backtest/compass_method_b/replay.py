"""Walk-forward compass replay — imports live compute_compass / build_portfolio_allocation."""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.compass.portfolio_builder import build_portfolio_allocation
from src.compass.regime_engine import compute_compass
from src.models import MarketIndicators, VALID_ASSET_GROUPS


def _row_to_market(row: pd.Series) -> MarketIndicators:
    return MarketIndicators(
        date=str(row["date"])[:10],
        kospi=float(row.get("kospi") or 0),
        kospi_recent_high=float(row.get("kospi_recent_high") or 0),
        kospi_200ma=float(row.get("kospi_200ma") or 0),
        sp500=float(row.get("sp500") or 0),
        sp500_recent_high=float(row.get("sp500_recent_high") or 0),
        vix=float(row.get("vix") or 0),
        usdkrw=float(row.get("usdkrw") or 0),
        korea_10y=float(row.get("korea_10y") or 0),
        oil_brent=float(row.get("oil_brent") or 0),
        gold=float(row.get("gold") or 0),
        foreign_flow_3d=str(row.get("foreign_flow_3d") or "neutral"),
        regime="NEUTRAL",
    )


def replay_compass(
    panel: pd.DataFrame,
    rules: dict[str, Any],
    profiles: dict[str, Any],
    *,
    warmup_trading_days: int = 200,
    profile_name: str = "core_absolute_return",
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Return results frame + judgment_history list (PIT, no future leak)."""
    judgment_history: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    if len(panel) <= warmup_trading_days:
        start_i = 0
    else:
        start_i = warmup_trading_days

    for i in range(start_i, len(panel)):
        row = panel.iloc[i]
        market = _row_to_market(row)
        # Critical: only past judgments (history already excludes today)
        compass = compute_compass(
            market,
            rules,
            use_manual_regime=False,
            tier2=None,
            judgment_history=list(judgment_history),
        )
        tilt_meta: dict[str, Any] = {}
        allocation = build_portfolio_allocation(
            compass,
            profiles,
            profile_name=profile_name,
            rules=rules,
            tilt_meta=tilt_meta,
        )
        weights = {g.asset_group: float(g.final_target) for g in allocation.groups}
        for ag in VALID_ASSET_GROUPS:
            weights.setdefault(ag, 0.0)

        computed_phase = (compass.computed_market_phase or compass.market_phase).value
        jrow = {
            "date": market.date,
            "computed_regime": compass.computed_regime.value,
            "applied_regime": compass.applied_regime.value,
            "market_phase": compass.market_phase.value,
            "computed_market_phase": computed_phase,
            "phase_confidence": compass.phase_confidence,
            "regime_confidence": compass.regime_confidence,
            "compass_direction": compass.compass_direction,
            "override_active": bool(compass.override.active),
            "hysteresis_note": compass.hysteresis_note,
            "taa_tilt_scale": tilt_meta.get("taa_tilt_scale"),
            "growth_score": compass.growth_score,
            "inflation_score": compass.inflation_score,
            "liquidity_score": compass.liquidity_score,
            "risk_appetite_score": compass.risk_appetite_score,
        }
        judgment_history.append(jrow)

        rec = {
            **jrow,
            **{f"w_{k}": v for k, v in weights.items()},
            "kospi": market.kospi,
            "sp500": market.sp500,
            "vix": market.vix,
            "usdkrw": market.usdkrw,
            "korea_10y": market.korea_10y,
            "gold": market.gold,
            "oil_brent": market.oil_brent,
        }
        records.append(rec)

    return pd.DataFrame(records), judgment_history
