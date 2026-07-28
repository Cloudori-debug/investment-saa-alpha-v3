from __future__ import annotations

from typing import Any

from src.alpha.schemas import FundamentalRecord

from src.alpha_v0_2.config_loader import clamp_score
from src.alpha_v0_2.schemas import GateResult


def score_catalyst(fund: FundamentalRecord | None, cfg: dict[str, Any]) -> GateResult:
    ccfg = cfg.get("catalyst", {})
    if fund is None:
        return GateResult(passed=False, score=0.0, reasons=["no_fundamentals"])

    reasons: list[str] = []
    points = 0.0
    count = 0

    min_div = float(ccfg.get("min_dividend_yield", 0.015))
    if fund.dividend_yield is not None and fund.dividend_yield >= min_div:
        points += 1.0
        count += 1
    else:
        reasons.append("dividend_weak")

    min_turn = float(ccfg.get("min_earnings_yoy_turnaround", 0.05))
    if fund.earnings_yoy is not None and fund.earnings_yoy >= min_turn:
        points += 1.0
        count += 1
    else:
        reasons.append("earnings_turnaround_absent")

    if ccfg.get("fcf_positive_points", True) and fund.fcf is not None and fund.fcf > 0:
        points += 1.0
        count += 1

    if count == 0:
        return GateResult(passed=False, score=0.0, reasons=reasons or ["no_catalyst"])

    score = clamp_score(points / 3 * 100)
    passed = count >= 1
    return GateResult(passed=passed, score=score, reasons=reasons)
