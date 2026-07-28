from __future__ import annotations

from src.compass.models import PortfolioAllocation
from src.exposure.ar11_target_integrity import (
    ensure_decomposed_sum_100,
    redistribute_orphan_group_targets,
)
from src.models import TargetRow


def decompose_target_portfolio(
    allocation: PortfolioAllocation,
    template: list[TargetRow],
) -> list[TargetRow]:
    """자산군 final_target 비중을 종목 템플릿 비율로 분해."""
    allocation, _, _ = redistribute_orphan_group_targets(allocation, template)
    group_template: dict[str, list[TargetRow]] = {}
    for row in template:
        group_template.setdefault(row.asset_group, []).append(row)

    alloc_map = {g.asset_group: g for g in allocation.groups}
    result: list[TargetRow] = []

    for group, rows in group_template.items():
        alloc = alloc_map.get(group)
        if not alloc or alloc.final_target <= 0:
            continue
        template_sum = sum(r.target_weight for r in rows)
        if template_sum <= 0:
            continue
        scale = alloc.final_target / template_sum
        min_scale = alloc.min_weight / template_sum if template_sum else 0
        max_scale = alloc.max_weight / template_sum if template_sum else 0

        for row in rows:
            result.append(
                TargetRow(
                    ticker=row.ticker,
                    name=row.name,
                    asset_group=row.asset_group,
                    sector=row.sector,
                    role=row.role,
                    target_weight=round(row.target_weight * scale, 2),
                    min_weight=round(row.min_weight * min_scale, 2),
                    max_weight=round(min(row.max_weight * max_scale, 100), 2),
                )
            )

    _normalize_to_group_targets(result, alloc_map)
    merged = _merge_duplicate_tickers(sorted(result, key=lambda r: (r.asset_group, -r.target_weight)))
    return ensure_decomposed_sum_100(merged)


def _merge_duplicate_tickers(rows: list[TargetRow]) -> list[TargetRow]:
    from src.portfolio_gap import consolidate_targets

    return consolidate_targets(rows)


def _normalize_to_group_targets(
    rows: list[TargetRow],
    alloc_map: dict[str, object],
) -> None:
    """반올림 오차를 그룹 내 최대 비중 종목에 반영."""
    from src.compass.models import GroupAllocation

    by_group: dict[str, list[TargetRow]] = {}
    for row in rows:
        by_group.setdefault(row.asset_group, []).append(row)

    for group, group_rows in by_group.items():
        alloc = alloc_map.get(group)
        if not isinstance(alloc, GroupAllocation):
            continue
        target_sum = sum(r.target_weight for r in group_rows)
        diff = round(alloc.final_target - target_sum, 2)
        if abs(diff) >= 0.01 and group_rows:
            largest = max(group_rows, key=lambda r: r.target_weight)
            for i, row in enumerate(rows):
                if row.ticker == largest.ticker and row.asset_group == group:
                    rows[i] = row.model_copy(update={"target_weight": round(row.target_weight + diff, 2)})
                    break
