from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.execution_scope import DRY_RUN_REQUIRED_DAYS, REVIEW_ONLY_ALPHA_SCOPES
from src.models import TradeAction
from src.operational_gate import CRITICAL_HEALTH_NAMES

OperatingState = Literal[
    "ERROR",
    "BLOCKED",
    "EXECUTE_ETF",
    "EXECUTE_ALPHA",
    "EXECUTE_MIXED",
    "REVIEW_TARGET",
    "NO_ACTION",
]

UI_OPERATING_STATES = frozenset({
    "ERROR", "BLOCKED", "EXECUTE_ETF", "REVIEW_TARGET", "NO_ACTION",
})

_BUY_ACTIONS = frozenset({"Buy-allowed", "Add"})
_SELL_ACTIONS = frozenset({"Trim"})


@dataclass
class OperatingStateBundle:
    operating_state: OperatingState
    primary_user_action: str
    allowed_scope_label: str
    forbidden_actions: list[str] = field(default_factory=list)
    has_executable_trade: bool = False
    has_executable_etf_trade: bool = False
    has_executable_alpha_trade: bool = False
    has_theoretical_signal: bool = False
    blocked_reasons: list[str] = field(default_factory=list)
    caution_reasons: list[str] = field(default_factory=list)
    secondary_tasks: list[str] = field(default_factory=list)
    next_required_step: str = ""
    executable_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operating_state": self.operating_state,
            "primary_user_action": self.primary_user_action,
            "allowed_scope_label": self.allowed_scope_label,
            "forbidden_actions": self.forbidden_actions,
            "has_executable_trade": self.has_executable_trade,
            "has_executable_etf_trade": self.has_executable_etf_trade,
            "has_executable_alpha_trade": self.has_executable_alpha_trade,
            "has_theoretical_signal": self.has_theoretical_signal,
            "blocked_reasons": self.blocked_reasons,
            "caution_reasons": self.caution_reasons,
            "secondary_tasks": self.secondary_tasks,
            "next_required_step": self.next_required_step,
            "executable_candidates": self.executable_candidates,
        }


def _fatal_error_reasons(health_checks: list[Any] | None) -> list[str]:
    if not health_checks:
        return []
    reasons: list[str] = []
    for check in health_checks:
        status = getattr(check, "status", "")
        name = getattr(check, "name", "")
        message = getattr(check, "message", "")
        if status == "fail" and name in CRITICAL_HEALTH_NAMES:
            reasons.append(f"{name}: {message}")
    return reasons


def _asset_group_map(gap_rows: list[Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in gap_rows or []:
        ticker = str(getattr(row, "ticker", "") or "")
        group = str(getattr(row, "asset_group", "") or "")
        if ticker:
            out[ticker] = group
    return out


def _is_kr_alpha(ticker: str, group_map: dict[str, str]) -> bool:
    return group_map.get(ticker) == "kr_alpha"


def _classify_executable(
    actions: list[TradeAction],
    *,
    group_map: dict[str, str],
) -> tuple[bool, bool, list[dict[str, Any]]]:
    etf = False
    alpha = False
    candidates: list[dict[str, Any]] = []

    for act in actions:
        if act.ticker == "PORTFOLIO":
            continue
        is_trade = act.action in _BUY_ACTIONS or (
            act.action in _SELL_ACTIONS and float(act.allowed_size_pct or 0) != 0
        )
        if not is_trade:
            continue
        row = {
            "ticker": act.ticker,
            "name": act.name,
            "action": act.action,
            "allowed_size_pct": act.allowed_size_pct,
            "reason": act.reason,
        }
        candidates.append(row)
        if _is_kr_alpha(act.ticker, group_map):
            alpha = True
        else:
            etf = True
    return etf, alpha, candidates


def _has_theoretical_signal(
    *,
    executable_actions: list[TradeAction],
    review_actions: list[TradeAction],
    group_gaps: list[Any] | None,
    buy_triggers_active: bool,
    theoretical_actions: list[TradeAction] | None,
) -> bool:
    if review_actions:
        return True
    if buy_triggers_active:
        return True
    for gap in group_gaps or []:
        action = str(getattr(gap, "action", "") or "")
        if action in {"WaitTrigger", "Buy", "Trim"}:
            return True
    for act in executable_actions:
        if act.action == "Wait" and "underweight" in act.reason.lower():
            return True
    for act in theoretical_actions or []:
        if act.action in {"Buy-allowed", "Add", "Replace", "Trim", "Buy"}:
            return True
    return False


def _collect_gate_blocks(
    *,
    system_status: str,
    data_gate: str,
    execution_scope: str,
    alpha_approval: str,
    dry_run_days: int,
) -> tuple[list[str], list[str]]:
    blocked: list[str] = []
    caution: list[str] = []

    if system_status == "RED":
        blocked.append(f"Overall RED ({system_status})")
    if data_gate == "RED":
        blocked.append("Data Gate RED")
    elif data_gate == "YELLOW":
        blocked.append("Data Gate YELLOW")
    if execution_scope == "NO_TRADE":
        blocked.append("Execution scope NO_TRADE")
    if execution_scope in REVIEW_ONLY_ALPHA_SCOPES:
        blocked.append("kr_alpha review-only scope")
    if alpha_approval in {"BLOCKED", "RESTRICTED"}:
        blocked.append(f"alpha_approval={alpha_approval}")
    if dry_run_days < DRY_RUN_REQUIRED_DAYS:
        caution.append(f"dry-run {dry_run_days}/{DRY_RUN_REQUIRED_DAYS} — 소액·제한 운용")
    return blocked, caution


def _has_wait_underweight(actions: list[TradeAction]) -> bool:
    for act in actions:
        if act.ticker == "PORTFOLIO":
            continue
        if act.action == "Wait" and "underweight" in act.reason.lower():
            return True
    return False


def derive_operating_state(
    *,
    system_status: str,
    data_gate: str,
    execution_scope: str,
    alpha_approval: str,
    dry_run_days: int,
    executable_actions: list[TradeAction],
    review_actions: list[TradeAction],
    gap_rows: list[Any] | None = None,
    group_gaps: list[Any] | None = None,
    health_checks: list[Any] | None = None,
    target_draft_pending: bool = False,
    buy_triggers_active: bool = False,
    theoretical_actions: list[TradeAction] | None = None,
) -> OperatingStateBundle:
    group_map = _asset_group_map(gap_rows)
    fatal = _fatal_error_reasons(health_checks)
    gate_blocked, caution = _collect_gate_blocks(
        system_status=system_status,
        data_gate=data_gate,
        execution_scope=execution_scope,
        alpha_approval=alpha_approval,
        dry_run_days=dry_run_days,
    )

    has_etf, has_alpha, candidates = _classify_executable(
        executable_actions, group_map=group_map
    )
    has_trade = bool(candidates)
    theoretical = _has_theoretical_signal(
        executable_actions=executable_actions,
        review_actions=review_actions,
        group_gaps=group_gaps,
        buy_triggers_active=buy_triggers_active,
        theoretical_actions=theoretical_actions,
    )

    forbidden = [
        "자동매매",
        "theoretical Replace/Trim을 실제 매도로 해석",
        "전액 리밸런싱",
    ]
    if execution_scope in REVIEW_ONLY_ALPHA_SCOPES or alpha_approval != "APPROVED":
        forbidden.append("kr_alpha 신규매수·교체")
        forbidden.append("kr_alpha 전량·무제한 매도 (리스크 축소 Trim만 승인 시 예외)")

    allowed_label = {
        "NO_TRADE": "관찰만",
        "ETF_ONLY": "ETF·현금·채권 후보 검토",
        "ETF_ONLY_ALPHA_REVIEW": "ETF + kr_alpha 연구·목표 검토",
        "ETF_AND_BETA": "ETF·베타 리밸런싱 검토",
        "FULL_WITH_ALPHA": "ETF + kr_alpha (승인 시)",
    }.get(execution_scope, execution_scope)

    secondary: list[str] = []
    if target_draft_pending:
        secondary.append("target_draft 승인 검토 (목표비중 변경, 실매매 아님)")

    blocked_reasons = list(gate_blocked)

    # --- priority ladder ---
    if fatal:
        return OperatingStateBundle(
            operating_state="ERROR",
            primary_user_action="매매 금지 — 데이터·입력 오류 수정 후 재분석",
            allowed_scope_label="없음",
            forbidden_actions=forbidden + ["모든 매매"],
            blocked_reasons=fatal,
            caution_reasons=caution,
            secondary_tasks=secondary,
            next_required_step="검증 탭에서 critical fail 해소 → 전체 분석 재실행",
        )

    if (
        has_alpha
        and has_etf
        and system_status != "RED"
        and execution_scope not in {"NO_TRADE"}
    ):
        state: OperatingState = "EXECUTE_MIXED"
        primary = "사용자 승인 필요 — ETF·kr_alpha 각 최대 1액션, 소액"
        next_step = "executable_brief 확인 → 체결 후 positions 갱신 → 재분석"
    elif has_alpha and system_status != "RED" and execution_scope not in {"NO_TRADE"}:
        state = "EXECUTE_ALPHA"
        primary = "사용자 승인 필요 — kr_alpha 최대 1액션, 소액"
        next_step = "Alpha 실행 가능 범위 확인 후 1건만 실행"
    elif has_etf and system_status != "RED" and execution_scope != "NO_TRADE":
        state = "EXECUTE_ETF"
        primary = "사용자 승인 필요 — ETF/베타 최대 1액션, 소액"
        next_step = "executable_brief Buy/Trim 확인 → 1건 실행 → positions 갱신 → 재분석"
    elif theoretical or _has_wait_underweight(executable_actions):
        state = "BLOCKED"
        primary = "매매 없음 — 신호·Gap은 있으나 실행 차단"
        if not blocked_reasons:
            blocked_reasons.append("executable Buy/Sell 없음 (Wait·Review-only)")
        next_step = "차단 사유 해소 또는 트리거·Gate GREEN 대기"
    elif target_draft_pending:
        state = "REVIEW_TARGET"
        primary = "목표비중 draft 검토 (실매매 아님)"
        next_step = "⑥ 알파/target_draft 승인 → 전체 분석 재실행"
    else:
        state = "NO_ACTION"
        primary = "관망 — 실행할 액션 없음"
        next_step = "내일 전체 분석 또는 시장 변화 시 재확인"

    return OperatingStateBundle(
        operating_state=state,
        primary_user_action=primary,
        allowed_scope_label=allowed_label,
        forbidden_actions=forbidden,
        has_executable_trade=has_trade,
        has_executable_etf_trade=has_etf,
        has_executable_alpha_trade=has_alpha,
        has_theoretical_signal=theoretical,
        blocked_reasons=blocked_reasons,
        caution_reasons=caution,
        secondary_tasks=secondary,
        next_required_step=next_step,
        executable_candidates=candidates,
    )


def format_operating_card_markdown(bundle: OperatingStateBundle, *, final: dict[str, Any]) -> list[str]:
    """executable_brief.md 상단 「오늘 운용」 섹션."""
    state = bundle.operating_state
    icon = {
        "ERROR": "❌",
        "BLOCKED": "⛔",
        "EXECUTE_ETF": "✅",
        "EXECUTE_ALPHA": "✅",
        "EXECUTE_MIXED": "✅",
        "REVIEW_TARGET": "📋",
        "NO_ACTION": "⬜",
    }.get(state, "·")

    lines = [
        "## 오늘 운용",
        "",
        f"- **상태**: {icon} `{state}`",
        f"- **할 일**: {bundle.primary_user_action}",
        f"- **허용**: {bundle.allowed_scope_label}",
        f"- **금지**: {', '.join(bundle.forbidden_actions[:4])}"
        + (" …" if len(bundle.forbidden_actions) > 4 else ""),
        "",
        f"- 운용 판정: **{final.get('system_status', '—')}** · Scope: `{final.get('execution_scope', '—')}` · "
        f"dry-run: **{final.get('dry_run_days', 0)}/{DRY_RUN_REQUIRED_DAYS}**",
    ]

    if bundle.executable_candidates:
        lines.append("- **실행 후보**:")
        for c in bundle.executable_candidates[:5]:
            lines.append(
                f"  - {c.get('name', c.get('ticker'))} ({c.get('ticker')}): "
                f"**{c.get('action')}**"
            )
    else:
        lines.append("- **실행 후보**: 없음")

    if bundle.blocked_reasons:
        lines.append(f"- **차단 사유**: {'; '.join(bundle.blocked_reasons[:5])}")
    if bundle.caution_reasons:
        lines.append(f"- **주의**: {'; '.join(bundle.caution_reasons)}")
    if bundle.secondary_tasks:
        lines.append(f"- **보조 확인**: {'; '.join(bundle.secondary_tasks)}")
    lines.append(f"- **다음 단계**: {bundle.next_required_step}")
    lines.append("")
    return lines
