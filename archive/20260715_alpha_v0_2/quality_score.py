from __future__ import annotations

from typing import Any

from src.alpha.schemas import FundamentalRecord, PriceRecord

from src.alpha_v0_2.config_loader import clamp_score
from src.alpha_v0_2.schemas import GateResult


def score_quality(
    fund: FundamentalRecord | None,
    price: PriceRecord | None,
    cfg: dict[str, Any],
) -> GateResult:
    qcfg = cfg.get("quality_gate", {})
    reasons: list[str] = []
    if fund is None:
        return GateResult(passed=False, score=0.0, reasons=["no_fundamentals"])

    points = 0.0
    max_pts = 5.0

    roe = fund.roe
    min_roe = float(qcfg.get("min_roe", 5.0))
    if roe is not None and roe >= min_roe:
        points += 1.0
    elif roe is not None:
        reasons.append(f"roe_low_{roe:.1f}")
    else:
        reasons.append("roe_missing")

    debt = fund.debt_ratio
    max_debt = float(qcfg.get("max_debt_ratio", 200.0))
    if debt is not None and debt <= max_debt:
        points += 1.0
    elif debt is not None:
        reasons.append(f"debt_high_{debt:.0f}")

    ic = fund.interest_coverage
    min_ic = float(qcfg.get("min_interest_coverage", 2.0))
    if ic is not None and ic >= min_ic:
        points += 1.0
    elif ic is not None:
        reasons.append(f"interest_coverage_low_{ic:.1f}")

    if fund.operating_margin is not None and fund.operating_margin > 0:
        points += 1.0
    else:
        reasons.append("margin_weak")

    if qcfg.get("require_positive_ocf_or_fcf", True):
        ocf_ok = fund.operating_cash_flow is not None and fund.operating_cash_flow > 0
        fcf_ok = fund.fcf is not None and fund.fcf > 0
        if ocf_ok or fcf_ok:
            points += 1.0
        else:
            reasons.append("cashflow_weak")

    score = clamp_score(points / max_pts * 100)
    passed = score >= 60 and "roe_missing" not in reasons and "cashflow_weak" not in reasons
    if score < 60:
        reasons.append("quality_score_below_60")
    return GateResult(passed=passed, score=score, reasons=reasons)
