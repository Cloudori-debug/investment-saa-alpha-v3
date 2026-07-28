from __future__ import annotations

from src.compass.models import PortfolioAllocation, TargetMismatchWarning
from src.models import TargetRow


def check_target_mismatch(
    allocation: PortfolioAllocation,
    ticker_targets: list[TargetRow],
    *,
    tolerance_pct: float = 0.5,
) -> list[TargetMismatchWarning]:
    ticker_sums: dict[str, float] = {}
    for row in ticker_targets:
        ticker_sums[row.asset_group] = ticker_sums.get(row.asset_group, 0.0) + row.target_weight

    warnings: list[TargetMismatchWarning] = []
    alloc_map = {g.asset_group: g.final_target for g in allocation.groups}

    all_groups = sorted(set(ticker_sums) | set(alloc_map))
    for group in all_groups:
        ticker_sum = round(ticker_sums.get(group, 0.0), 2)
        alloc_target = round(alloc_map.get(group, 0.0), 2)
        diff = round(ticker_sum - alloc_target, 2)
        if abs(diff) > tolerance_pct:
            warnings.append(
                TargetMismatchWarning(
                    asset_group=group,
                    ticker_target_sum=ticker_sum,
                    allocation_target=alloc_target,
                    diff=diff,
                )
            )
    return warnings
