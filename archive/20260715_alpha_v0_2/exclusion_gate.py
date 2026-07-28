from __future__ import annotations

from typing import Any

from src.alpha.schemas import FundamentalRecord, PriceRecord, UniverseRecord

from src.alpha_v0_2.schemas import GateResult


def run_exclusion_gate(
    rec: UniverseRecord,
    fund: FundamentalRecord | None,
    price: PriceRecord | None,
    cfg: dict[str, Any],
) -> GateResult:
    reasons: list[str] = []
    ex = cfg.get("exclusion", {})
    liq = cfg.get("liquidity", {})

    if rec.is_trading_halt:
        reasons.append("trading_halt")
    if rec.is_administrative_issue:
        reasons.append("admin_issue")
    if rec.capital_impairment:
        reasons.append("capital_impairment")
    if rec.audit_opinion not in {"", "clean", "unqualified"}:
        reasons.append(f"audit_{rec.audit_opinion}")

    if price is None:
        reasons.append("no_price")
    else:
        min_mcap = float(ex.get("min_market_cap_krw", 0))
        min_tv = float(liq.get("min_trading_value_20d", ex.get("min_trading_value_20d", 0)))
        if price.market_cap < min_mcap:
            reasons.append("low_market_cap")
        if price.trading_value_20d < min_tv:
            reasons.append("low_liquidity")

    if fund and fund.net_income is not None and fund.net_income < 0 and (fund.earnings_yoy or 0) < -0.2:
        reasons.append("severe_earnings_decline")

    passed = not reasons
    score = 100.0 if passed else 0.0
    return GateResult(passed=passed, score=score, reasons=reasons)
