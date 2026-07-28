from __future__ import annotations

from src.models import GapRow, GapStatus, PositionRow, TargetRow


def total_portfolio_value(positions: list[PositionRow]) -> float:
    return sum(p.current_value for p in positions)


def current_weights(positions: list[PositionRow]) -> dict[str, float]:
    total = total_portfolio_value(positions)
    return {p.ticker: (p.current_value / total) * 100 for p in positions}


def classify_gap(gap: float, in_target: bool, current_weight: float) -> GapStatus:
    if not in_target and current_weight > 0:
        return "Not in target"
    if current_weight == 0 and gap > 0:
        return "No position"
    if gap >= 5:
        return "Underweight"
    if gap >= 1:
        return "Slightly underweight"
    if gap > -1:
        return "Within band"
    if gap > -5:
        return "Slightly overweight"
    return "Overweight"


def consolidate_targets(targets: list[TargetRow]) -> list[TargetRow]:
    """동일 ticker 중복 행을 합산 (템플릿·분해 산출물 중복 방지)."""
    by_ticker: dict[str, TargetRow] = {}
    for tgt in targets:
        if tgt.ticker in by_ticker:
            prev = by_ticker[tgt.ticker]
            by_ticker[tgt.ticker] = prev.model_copy(
                update={
                    "target_weight": round(prev.target_weight + tgt.target_weight, 2),
                    "min_weight": round(prev.min_weight + tgt.min_weight, 2),
                    "max_weight": round(prev.max_weight + tgt.max_weight, 2),
                }
            )
        else:
            by_ticker[tgt.ticker] = tgt
    return list(by_ticker.values())


def compute_gaps(
    positions: list[PositionRow],
    targets: list[TargetRow],
) -> list[GapRow]:
    total = total_portfolio_value(positions)
    cur_map = {p.ticker: p for p in positions}
    tgt_map = {t.ticker: t for t in consolidate_targets(targets)}
    all_tickers = sorted(set(cur_map) | set(tgt_map))

    rows: list[GapRow] = []
    for ticker in all_tickers:
        pos = cur_map.get(ticker)
        tgt = tgt_map.get(ticker)
        current_w = (pos.current_value / total * 100) if pos else 0.0
        target_w = tgt.target_weight if tgt else 0.0
        gap = round(target_w - current_w, 2)
        in_target = tgt is not None
        rows.append(
            GapRow(
                ticker=ticker,
                name=(pos.name if pos else (tgt.name if tgt else ticker)),
                asset_group=(pos.asset_group if pos else (tgt.asset_group if tgt else "")),
                current_weight=round(current_w, 2),
                target_weight=target_w,
                gap=gap,
                min_weight=tgt.min_weight if tgt else 0.0,
                max_weight=tgt.max_weight if tgt else 0.0,
                status=classify_gap(gap, in_target, current_w),
                in_target=in_target,
            )
        )
    return rows


def aggregate_by_asset_group(gap_rows: list[GapRow]) -> dict[str, dict[str, float]]:
    groups: dict[str, dict[str, float]] = {}
    for row in gap_rows:
        if not row.asset_group:
            continue
        bucket = groups.setdefault(row.asset_group, {"current": 0.0, "target": 0.0})
        bucket["current"] += row.current_weight
        bucket["target"] += row.target_weight
    for bucket in groups.values():
        bucket["gap"] = round(bucket["target"] - bucket["current"], 2)
    return groups
