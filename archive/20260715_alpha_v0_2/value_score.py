from __future__ import annotations

from typing import Any

from src.alpha.schemas import FundamentalRecord

from src.alpha_v0_2.config_loader import clamp_score
from src.alpha_v0_2.schemas import GateResult


def score_value(fund: FundamentalRecord | None, cfg: dict[str, Any]) -> GateResult:
    vcfg = cfg.get("value_gate", {})
    if fund is None:
        return GateResult(passed=False, score=0.0, reasons=["no_fundamentals"])

    reasons: list[str] = []
    points = 0.0
    max_pts = 4.0

    pbr = fund.pbr
    max_pbr = float(vcfg.get("max_pbr", 3.5))
    if pbr is not None and 0 < pbr <= max_pbr:
        points += 1.0
    elif pbr is not None:
        reasons.append(f"pbr_high_{pbr:.2f}")

    per = fund.per
    max_per = float(vcfg.get("max_per", 40.0))
    if per is not None and 0 < per <= max_per:
        points += 1.0
    elif per is not None:
        reasons.append(f"per_high_{per:.1f}")

    if fund.ev_ebitda is not None and 0 < fund.ev_ebitda <= 12:
        points += 1.0
    elif fund.ev_ebitda is not None:
        reasons.append("ev_ebitda_high")

    fcf_yield = None
    if fund.fcf is not None and fund.pbr and fund.pbr > 0:
        fcf_yield = fund.fcf  # proxy without mcap in simple form
    if fund.fcf is not None and fund.fcf > 0:
        points += 1.0
    elif fcf_yield is not None:
        reasons.append("fcf_weak")

    score = clamp_score(points / max_pts * 100)
    passed = score >= 55
    if not passed:
        reasons.append("value_score_below_55")
    return GateResult(passed=passed, score=score, reasons=reasons)
