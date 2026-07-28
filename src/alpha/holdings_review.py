from __future__ import annotations

from src.alpha.schemas import AlphaCandidate, HoldingReview
from src.models import PositionRow, TargetRow
from src.portfolio_gap import compute_gaps


def review_holdings(
    positions: list[PositionRow],
    targets: list[TargetRow],
    candidates_by_ticker: dict[str, AlphaCandidate],
    config: dict,
    *,
    missing_price_tickers: list[str] | None = None,
) -> list[HoldingReview]:
    review_cfg = config.get("holdings_review", {})
    keep_min = float(review_cfg.get("keep_grade_min_score", 55))
    trim_below = float(review_cfg.get("trim_below_score", 40))
    no_price = set(missing_price_tickers or [])

    gap_rows = compute_gaps(positions, targets)
    reviews: list[HoldingReview] = []

    for row in gap_rows:
        if row.asset_group != "kr_alpha":
            continue
        if row.ticker in {"CASH"}:
            continue

        cand = candidates_by_ticker.get(row.ticker)
        if cand:
            score = cand.total_score
            grade = cand.grade
        else:
            score = 0.0
            grade = "Reject"

        if row.current_weight <= 0 and row.target_weight <= 0:
            continue

        if row.current_weight <= 0 and row.target_weight > 0:
            if row.ticker in no_price:
                action = "WATCH"
                reason = "목표 포함·미보유 — 시세 미확보 (research-only, target 편입 보류)"
            elif score >= keep_min and grade in {"A", "B"}:
                action = "WATCH"
                reason = "목표 포함·미보유 — 진입 검토 (신규)"
            elif score >= trim_below:
                action = "WATCH"
                reason = "목표 포함·미보유 — 점수 중간, 신규 매수 보류"
            elif score > 0:
                action = "WATCH"
                reason = "목표 포함·미보유 — 저점수, 신규 매수 회피"
            else:
                action = "WATCH"
                reason = "목표 포함·미보유 — 스크리너 미통과"
        elif score >= keep_min and grade in {"A", "B"}:
            action = "KEEP"
            reason = "알파 점수 양호, 유지"
        elif score >= trim_below:
            action = "WATCH"
            reason = "점수 중간, 모니터링"
        elif score > 0:
            action = "TRIM"
            reason = "알파 점수 하락, 비중 축소 검토"
        else:
            action = "REPLACE_CANDIDATE"
            reason = "스크리너 미통과 또는 저점수, 교체 후보"

        reviews.append(
            HoldingReview(
                ticker=row.ticker,
                name=row.name,
                current_weight=row.current_weight,
                target_weight=row.target_weight,
                alpha_score=score,
                grade=grade if grade != "Reject" else "C",
                review_action=action,
                reason=reason,
            )
        )
    return reviews
