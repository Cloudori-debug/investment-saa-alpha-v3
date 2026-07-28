from __future__ import annotations

from src.compass.models import GroupActionType, GroupGapRow, RiskRegime


def plan_group_actions(
    gap_rows: list[GroupGapRow],
    *,
    applied_regime: RiskRegime,
    data_gate: str,
    trim_threshold: float = 3.0,
    buy_threshold: float = 1.0,
    buy_triggers_active: bool = False,
    execution_scope: str | None = None,
    stop_buy: bool = False,
) -> list[GroupGapRow]:
    if data_gate == "RED":
        return [
            GroupGapRow(
                asset_group=row.asset_group,
                current=row.current,
                target=row.target,
                gap=row.gap,
                action="NoTrade",
                reason="Data Gate RED — 입력 수정 전 거래 금지",
            )
            for row in gap_rows
        ]

    result: list[GroupGapRow] = []
    block_buy = applied_regime in {RiskRegime.CRISIS, RiskRegime.RISK_OFF}
    caution = applied_regime == RiskRegime.CAUTION

    for row in gap_rows:
        action: GroupActionType
        reason: str

        if row.target <= 0.01:
            if row.gap <= -trim_threshold:
                action = "Trim"
                reason = f"목표 0% — 현재 {row.current:.1f}% 과체중 ({abs(row.gap):.1f}%p)"
            else:
                action = "Hold"
                reason = "목표 0% — 매수 수요 없음"
            result.append(
                GroupGapRow(
                    asset_group=row.asset_group,
                    current=row.current,
                    target=row.target,
                    gap=row.gap,
                    action=action,
                    reason=reason,
                )
            )
            continue

        if row.gap <= -trim_threshold:
            if row.asset_group == "cash_short_bond":
                action = "Park"
                reason = "현금·채권 과체중 — 매수 탄약으로 유지 (Trim 불필요)"
            else:
                action = "Trim"
                reason = f"목표 대비 {abs(row.gap):.1f}%p 과체중"

        elif abs(row.gap) < buy_threshold:
            action = "Hold"
            reason = "목표 밴드 내"

        elif row.gap >= buy_threshold:
            if row.asset_group == "kr_alpha" and execution_scope in {
                "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "ETF_AND_BETA", "NO_TRADE"
            }:
                action = "Wait"
                reason = "kr_alpha — 실행 범위 밖, 리뷰 전용"
            elif block_buy:
                action = "NoTrade"
                reason = f"{applied_regime.value} — 신규 매수 금지"
            elif stop_buy or data_gate == "YELLOW":
                action = "WaitTrigger"
                reason = (
                    "Stop-buy zone — executable 매수 보류"
                    if stop_buy
                    else "Data Gate YELLOW — executable 매수 보류 (종목 Wait와 동일)"
                )
            elif caution and row.asset_group in {"kr_alpha", "domestic_beta", "global_beta"}:
                action = "WaitTrigger"
                reason = "CAUTION — 베타·알파 트리거 대기"
            elif buy_triggers_active:
                action = "Buy"
                reason = f"목표 대비 {row.gap:.1f}%p 부족 + 매수 트리거 충족"
            else:
                action = "BuyCandidate"
                reason = f"목표 대비 {row.gap:.1f}%p 부족 — Buy Candidate (트리거 대기)"

        else:
            action = "Hold"
            reason = "소폭 편차 — 관망"

        result.append(
            GroupGapRow(
                asset_group=row.asset_group,
                current=row.current,
                target=row.target,
                gap=row.gap,
                action=action,
                reason=reason,
            )
        )

    return result
