from __future__ import annotations

from typing import Any

from src.alpha.target_bridge import kr_alpha_target_sum, load_kr_alpha_budget
from src.data_loader import load_target_portfolio
from src.field_normalize import normalize_sector
from src.models import TargetRow


def check_kr_alpha_constraints(
    targets: list[TargetRow],
    output_dir,
    *,
    candidates: list[dict[str, Any]] | None = None,
    holdings_review: list[dict[str, Any]] | None = None,
    max_sector_share: float = 0.40,
) -> tuple[list[str], dict[str, Any]]:
    """kr_alpha 예산·섹터·교체 압력 경고 (실행 차단 아님)."""
    warnings: list[str] = []
    meta: dict[str, Any] = {}

    budget = load_kr_alpha_budget(output_dir)
    kr_sum = kr_alpha_target_sum(targets)
    meta["kr_alpha_target_sum"] = kr_sum
    meta["kr_alpha_budget"] = budget

    if budget is not None:
        gap = round(kr_sum - budget, 2)
        meta["kr_alpha_gap"] = gap
        if gap > 1.0:
            warnings.append(f"kr_alpha target 합 {kr_sum:.1f}% > Compass 예산 {budget:.1f}% (+{gap:.1f}%p)")
        elif gap < -5.0:
            warnings.append(f"kr_alpha target 합 {kr_sum:.1f}% — Compass {budget:.1f}% 대비 {-gap:.1f}%p 여유")

    kr_rows = [t for t in targets if t.asset_group == "kr_alpha" and t.target_weight > 0]
    if kr_rows:
        sector_weights: dict[str, float] = {}
        for row in kr_rows:
            sector = normalize_sector(row.sector)
            sector_weights[sector] = sector_weights.get(sector, 0) + row.target_weight
        total = sum(sector_weights.values()) or 1.0
        for sector, w in sector_weights.items():
            share = w / total
            if share > max_sector_share:
                warnings.append(f"섹터 집중: {sector} {share:.0%} (한도 {max_sector_share:.0%})")
        meta["sector_weights"] = sector_weights

    if holdings_review:
        replace_n = sum(1 for h in holdings_review if h.get("review_action") == "REPLACE_CANDIDATE")
        trim_n = sum(1 for h in holdings_review if h.get("review_action") == "TRIM")
        meta["replace_count"] = replace_n
        meta["trim_count"] = trim_n
        if replace_n >= 3:
            warnings.append(f"REPLACE_CANDIDATE {replace_n}건 — 단기 대량 교체 자제 권장")

    if candidates is not None:
        buy_n = sum(1 for c in candidates if c.get("eligible_action") == "BUY_CANDIDATE")
        meta["buy_candidate_count"] = buy_n
        sectors = [
            normalize_sector(c.get("sector", ""))
            for c in candidates[:10]
            if c.get("eligible_action") == "BUY_CANDIDATE"
        ]
        sectors = [s for s in sectors if s != "unknown"]
        if sectors and len(set(sectors)) == 1 and len(sectors) >= 3:
            warnings.append(f"상위 BUY 후보 섹터 편중: {sectors[0]}")

    return warnings, meta


def load_targets_for_constraints(data_dir) -> list[TargetRow]:
    return load_target_portfolio(data_dir / "target_portfolio.csv")
