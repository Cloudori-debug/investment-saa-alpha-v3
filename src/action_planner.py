from __future__ import annotations

from src.models import ActionType, DataGate, GapRow, TradeAction, TriggerAlert
from src.execution_scope import REVIEW_ONLY_ALPHA_SCOPES
from src.risk_limits import RiskReport
from src.trigger_engine import is_buy_trigger_active, is_stop_buy
from src.trim_sizing import compute_trim_guidance, format_trim_short, trim_config_from_rules


def _is_cash_ticker(ticker: str) -> bool:
    return ticker.upper() == "CASH"


def _priority(action: ActionType, gap: float, *, theoretical: bool = False) -> str:
    if theoretical or action == "Park":
        return "Low"
    if action in {"Replace", "Trim", "Risk defense", "Stop-buy", "No trade"}:
        return "High"
    if abs(gap) >= 5:
        return "High"
    if action in {"Wait", "Buy-allowed"}:
        return "Medium"
    return "Low"


def _cash_short_bond_overweight_action(
    row: GapRow,
    *,
    trim_ppt: float,
    group_actions: dict[str, str] | None,
    buy_triggers_active: bool,
) -> tuple[ActionType, str, float]:
    """현금·단기채 과체중 — Park 기본. Trim은 매수 트리거·자금 배분 시에만."""
    if _is_cash_ticker(row.ticker):
        return (
            "Park",
            "예수금은 매도 대상 아님 — 매수 트리거 시 funding source",
            0.0,
        )

    group_action = (group_actions or {}).get("cash_short_bond", "")
    if group_action == "Park" or not buy_triggers_active:
        return (
            "Park",
            "현금·채권 과체중 — 매수 탄약 유지 (매수 트리거 전 Trim 불가)",
            0.0,
        )

    if row.gap <= -trim_ppt:
        action, reason, allowed_size = (
            "Trim",
            "과체중 — 활성 매수 트리거에 자금 배분",
            max(row.gap, -row.current_weight),
        )
        return action, reason, allowed_size  # type: ignore[return-value]

    return ("Hold", "Near target — monitor", 0.0)


def _apply_trim_sizing(
    row: GapRow,
    reason: str,
    allowed_size: float,
    rules: dict,
) -> tuple[str, float]:
    step_frac, max_step = trim_config_from_rules(rules)
    guidance = compute_trim_guidance(
        row.gap,
        current_weight=row.current_weight,
        step_fraction=step_frac,
        max_step_ppt=max_step,
    )
    if guidance is None:
        return reason, allowed_size
    detail = (
        f"gap {guidance.overweight_ppt:.1f}%p → "
        f"1회 권장 Trim {guidance.suggested_step_ppt:.1f}%p "
        f"(전량 {guidance.full_ceiling_ppt:.1f}%p 금지·한 번에 한 건)"
    )
    return f"{reason} — {detail}", -guidance.suggested_step_ppt


def _kr_alpha_group_hard(risk: RiskReport) -> bool:
    return any(v.code == "KR_ALPHA_MAX" and v.severity == "HARD" for v in risk.violations)


def _is_kr_alpha_risk_trim(
    row: GapRow,
    risk: RiskReport,
    *,
    trim_ppt: float,
) -> bool:
    if row.asset_group != "kr_alpha" or row.gap >= 0:
        return False
    hard_tickers = {v.ticker for v in risk.violations if v.severity == "HARD" and v.ticker}
    return row.ticker in hard_tickers or _kr_alpha_group_hard(risk) or row.gap <= -trim_ppt


def plan_actions(
    gap_rows: list[GapRow],
    alerts: list[TriggerAlert],
    risk: RiskReport,
    data_gate: DataGate,
    rules: dict,
    *,
    execution_scope: str | None = None,
    group_actions: dict[str, str] | None = None,
    buy_triggers_active: bool = False,
    execution_policy: dict | None = None,
) -> list[TradeAction]:
    actions: list[TradeAction] = []
    stop_buy = is_stop_buy(alerts)
    trim_ppt = float(rules.get("position_triggers", {}).get("trim_if_target_overweight_ppt", 5))
    hard_violations = {v.ticker for v in risk.violations if v.severity == "HARD" and v.ticker}
    kr_alpha_risk_trim = bool((execution_policy or {}).get("kr_alpha_risk_trim_under_etf_only", False))

    if data_gate == "RED":
        return [
            TradeAction(
                ticker="PORTFOLIO",
                name="All",
                action="No trade",
                reason="Data Gate RED — fix inputs before any trade",
                allowed_size_pct=0,
                priority="High",
            )
        ]

    if stop_buy:
        actions.append(
            TradeAction(
                ticker="PORTFOLIO",
                name="All",
                action="Stop-buy",
                reason="VIX panic / risk trigger — no new buys",
                allowed_size_pct=0,
                priority="High",
            )
        )

    for row in gap_rows:
        if row.current_weight == 0 and row.target_weight == 0:
            continue

        action: ActionType
        reason: str
        allowed_size = 0.0

        theoretical = False

        if not row.in_target and row.current_weight > 0:
            action = "Replace"
            if row.asset_group == "kr_alpha" and execution_scope in {
                "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "ETF_AND_BETA", "NO_TRADE"
            }:
                reason = "target template 미포함 — 이론값 (실행·매도 금지)"
                theoretical = True
            else:
                reason = "Not in target portfolio"
            allowed_size = -row.current_weight

        elif row.gap <= -trim_ppt or row.ticker in hard_violations:
            if row.asset_group == "cash_short_bond":
                action, reason, allowed_size = _cash_short_bond_overweight_action(
                    row,
                    trim_ppt=trim_ppt,
                    group_actions=group_actions,
                    buy_triggers_active=buy_triggers_active,
                )
            else:
                action = "Trim"
                reason = "Target overweight or hard risk limit"
                allowed_size = max(row.gap, -row.current_weight)
                if (
                    row.asset_group == "kr_alpha"
                    and execution_scope in REVIEW_ONLY_ALPHA_SCOPES
                ):
                    if kr_alpha_risk_trim and _is_kr_alpha_risk_trim(row, risk, trim_ppt=trim_ppt):
                        reason = "kr_alpha 리스크 축소 Trim (ETF_ONLY·사람 승인 필요)"
                    else:
                        theoretical = True

        elif row.gap >= 1:
            if row.asset_group == "kr_alpha" and execution_scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "ETF_AND_BETA", "NO_TRADE"}:
                action = "Wait"
                reason = f"Execution scope {execution_scope} — kr_alpha 신규·교체 실행 금지"
            elif row.asset_group == "kr_alpha" and data_gate == "YELLOW":
                action = "Wait"
                reason = "Unified gate YELLOW — kr_alpha 신규매수 보류"
            elif stop_buy or data_gate == "YELLOW":
                action = "Wait"
                reason = "Underweight but stop-buy or data caution"
            elif is_buy_trigger_active(alerts, row.asset_group):
                action = "Buy-allowed"
                reason = "Underweight + buy trigger active"
                allowed_size = min(row.gap, row.max_weight - row.current_weight)
            else:
                action = "Wait"
                reason = "Underweight but no buy trigger"

        elif row.gap > -1:
            if row.status == "Within band":
                action = "Hold"
                reason = "Within target band"
            else:
                action = "Hold"
                reason = "Near target — monitor"

        else:
            action = "Hold"
            reason = "Slightly above target — hold unless rebound trim"

        if action == "Trim" and not theoretical:
            reason, allowed_size = _apply_trim_sizing(row, reason, allowed_size, rules)

        actions.append(
            TradeAction(
                ticker=row.ticker,
                name=row.name,
                action=action,
                reason=reason,
                allowed_size_pct=round(allowed_size, 2),
                priority=_priority(action, row.gap, theoretical=theoretical),  # type: ignore[arg-type]
            )
        )

    order = {
        "Risk defense": 0, "No trade": 0, "Review-only": 1, "Stop-buy": 1, "Replace": 2, "Trim": 3,
        "Wait": 4, "Buy-allowed": 5, "Add": 6, "Hold": 7, "Park": 8,
    }
    actions.sort(key=lambda a: (order.get(a.action, 9), -abs(
        next((r.gap for r in gap_rows if r.ticker == a.ticker), 0)
    )))
    return actions
