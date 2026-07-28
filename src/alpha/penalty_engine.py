from __future__ import annotations

from typing import Any

from src.alpha.schemas import FundamentalRecord, PriceRecord, UniverseRecord


def _penalty_amount(config: dict[str, Any], key: str) -> float:
    val = config.get("penalties", {}).get(key, 0)
    return abs(float(val))


def apply_penalties(
    scored: list[dict[str, Any]],
    universe_by_ticker: dict[str, UniverseRecord],
    fundamentals: dict[str, FundamentalRecord],
    prices: dict[str, PriceRecord],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    rules = config.get("penalty_rules", {})
    out: list[dict[str, Any]] = []

    for row in scored:
        ticker = row["ticker"]
        rec = universe_by_ticker.get(ticker)
        fund = fundamentals.get(ticker)
        px = prices.get(ticker)
        penalty = 0.0
        reasons: list[str] = []

        if px and px.trading_value_20d < 2_000_000_000:
            penalty += _penalty_amount(config, "low_liquidity")
            reasons.append("저유동성")

        if fund and fund.net_income is not None and fund.net_income < 0:
            penalty += _penalty_amount(config, "negative_earnings")
            reasons.append("적자")

        if fund and fund.earnings_yoy is not None and fund.earnings_yoy < 0:
            penalty += _penalty_amount(config, "declining_earnings")
            reasons.append("이익감소")

        debt_limit = float(rules.get("debt_ratio_above", 200))
        if fund and fund.debt_ratio is not None and fund.debt_ratio > debt_limit:
            penalty += _penalty_amount(config, "high_debt")
            reasons.append("고부채")

        vol_limit = float(rules.get("volatility_60d_above", 0.45))
        if px and px.volatility_60d > vol_limit:
            penalty += _penalty_amount(config, "high_volatility")
            reasons.append("고변동성")

        if rec and rec.audit_opinion not in {"clean", "unqualified", "qualified"}:
            penalty += _penalty_amount(config, "audit_or_trading_risk")
            reasons.append("감사리스크")
        if rec and (rec.is_trading_halt or rec.is_administrative_issue):
            penalty += _penalty_amount(config, "audit_or_trading_risk")
            reasons.append("거래/관리 리스크")

        if fund and rules.get("per_below_with_negative_income"):
            if fund.per is not None and fund.per < 5 and fund.net_income is not None and fund.net_income < 0:
                penalty += _penalty_amount(config, "value_trap")
                reasons.append("가치함정")

        ret_limit = float(rules.get("return_3m_above", 0.35))
        if px and px.return_3m > ret_limit:
            penalty += _penalty_amount(config, "overheated_price")
            reasons.append("급등과열")

        total = max(0.0, round(row["base_score"] - penalty, 2))
        row = dict(row)
        row["penalty"] = round(penalty, 2)
        row["total_score"] = total
        row["key_reason"] = ", ".join(reasons) if reasons else "Q/V/M/SR 양호"
        out.append(row)
    return out


def assign_grades(
    scored: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    grades_cfg = config.get("grades", {})
    a_min = float(grades_cfg.get("A_min_score", 70))
    b_min = float(grades_cfg.get("B_min_score", 55))
    c_min = float(grades_cfg.get("C_min_score", 40))

    ranked = sorted(scored, key=lambda x: x["total_score"], reverse=True)
    out: list[dict[str, Any]] = []
    for rank, row in enumerate(ranked, start=1):
        ts = row["total_score"]
        if ts >= a_min:
            grade, action = "A", "BUY_CANDIDATE"
        elif ts >= b_min:
            grade, action = "B", "WATCH"
        elif ts >= c_min:
            grade, action = "C", "WATCH"
        else:
            grade, action = "Reject", "NO_NEW"
        row = dict(row)
        row["rank"] = rank
        row["grade"] = grade
        row["eligible_action"] = action
        out.append(row)
    return out
