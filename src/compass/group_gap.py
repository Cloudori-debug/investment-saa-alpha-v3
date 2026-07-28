from __future__ import annotations

from src.compass.models import GroupActionType, GroupGapRow, PortfolioAllocation, RiskRegime
from src.models import PositionRow


def current_weights_by_group(positions: list[PositionRow]) -> dict[str, float]:
    total = sum(p.current_value for p in positions)
    if total <= 0:
        return {}
    groups: dict[str, float] = {}
    for pos in positions:
        groups[pos.asset_group] = groups.get(pos.asset_group, 0.0) + pos.current_value
    return {g: round(w / total * 100, 2) for g, w in groups.items()}


def compute_group_gaps(
    positions: list[PositionRow],
    allocation: PortfolioAllocation,
) -> list[GroupGapRow]:
    current = current_weights_by_group(positions)
    rows: list[GroupGapRow] = []
    for group_alloc in allocation.groups:
        group = group_alloc.asset_group
        cur = current.get(group, 0.0)
        tgt = group_alloc.final_target
        gap = round(tgt - cur, 2)
        rows.append(
            GroupGapRow(
                asset_group=group,
                current=cur,
                target=tgt,
                gap=gap,
                action="Hold",
                reason="",
            )
        )
    return rows


def group_gap_rows_to_trigger_map(rows: list[GroupGapRow]) -> dict[str, dict[str, float]]:
    """트리거·리포트 공통 — Compass allocation 기준 group gap."""
    return {
        r.asset_group: {"current": r.current, "target": r.target, "gap": r.gap}
        for r in rows
    }
