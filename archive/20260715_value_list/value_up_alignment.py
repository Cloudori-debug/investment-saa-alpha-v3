from __future__ import annotations

from typing import Any


def compute_alignment_score(
    *,
    fund: dict[str, Any] | None,
    dart: dict[str, Any] | None,
) -> float:
    """밸류업·자사주 소각 정합 점수 (0–100). DART 없으면 재무 휴리스틱만."""
    score = 50.0

    if dart:
        score += float(dart.get("alignment_pts", 0) or 0)
        if dart.get("cancel_disclosure"):
            score += 5.0
        if dart.get("signal") == "weak":
            score -= 5.0

    if fund:
        try:
            ocf = fund.get("operating_cash_flow")
            if ocf not in (None, "") and float(ocf) > 0:
                score += 12.0
            elif ocf not in (None, "") and float(ocf) < 0:
                score -= 8.0
        except (TypeError, ValueError):
            pass
        try:
            pbr = fund.get("pbr")
            if pbr not in (None, "") and float(pbr) > 0:
                if float(pbr) < 0.6:
                    score += 10.0
                elif float(pbr) < 1.0:
                    score += 6.0
        except (TypeError, ValueError):
            pass
        try:
            div = fund.get("dividend_yield")
            if div not in (None, "") and float(div) >= 3:
                score += 5.0
        except (TypeError, ValueError):
            pass

    return max(0.0, min(100.0, score))
