from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from src.models import GapRow, TradeAction

ExecutionScope = Literal[
    "NO_TRADE",
    "ETF_ONLY",
    "ETF_ONLY_ALPHA_REVIEW",
    "ETF_AND_BETA",
    "FULL_WITH_ALPHA",
]

AlphaTradePermission = Literal["ALLOW_NEW", "BLOCK_NEW_BUY", "BLOCK_ALL"]
AlphaPositionAction = Literal["EXECUTABLE", "REVIEW_ONLY", "RISK_REDUCE_ONLY"]

REVIEW_ONLY_ALPHA_SCOPES = frozenset({
    "NO_TRADE",
    "ETF_ONLY",
    "ETF_ONLY_ALPHA_REVIEW",
    "ETF_AND_BETA",
})
DRY_RUN_REQUIRED_DAYS = 10


def count_dry_run_days(output_dir: Path) -> int:
    path = output_dir / "dry_run_log.jsonl"
    if not path.exists():
        return 0
    dates: set[str] = set()
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        if line.strip():
            dates.add(str(json.loads(line).get("date", "")))
    return len(dates)


def apply_dry_run_scope_cap(
    scope: ExecutionScope,
    dry_run_days: int,
    *,
    required_days: int = DRY_RUN_REQUIRED_DAYS,
) -> ExecutionScope:
    """dry-run 미완료 시 FULL_WITH_ALPHA → ETF_ONLY_ALPHA_REVIEW."""
    if dry_run_days < required_days and scope == "FULL_WITH_ALPHA":
        return "ETF_ONLY_ALPHA_REVIEW"
    return scope


def derive_execution_scope(
    *,
    data_gate: str,
    portfolio_gate: str,
    alpha_data_gate: str | None,
    health_gate: str | None = None,
    health_overall: str = "pass",
    dry_run_days: int | None = None,
) -> ExecutionScope:
    """acceptance_check과 동일한 실행 범위 (파이프라인·리포트용)."""
    hg = health_gate
    if hg is None:
        hg = "RED" if health_overall == "fail" else "YELLOW" if health_overall == "warn" else "GREEN"

    if hg == "RED" or portfolio_gate == "RED" or data_gate == "RED":
        scope: ExecutionScope = "NO_TRADE"
    elif data_gate == "YELLOW":
        scope = "ETF_ONLY"
    elif alpha_data_gate in ("RED", "YELLOW"):
        scope = "ETF_ONLY"
    elif data_gate == "GREEN" and portfolio_gate == "GREEN" and (alpha_data_gate or "GREEN") == "GREEN":
        scope = "FULL_WITH_ALPHA"
    elif data_gate == "GREEN" and portfolio_gate == "GREEN":
        scope = "ETF_AND_BETA"
    else:
        scope = "ETF_ONLY"

    if dry_run_days is not None:
        scope = apply_dry_run_scope_cap(scope, dry_run_days)
    return scope


def derive_alpha_permissions(
    *,
    alpha_data_gate: str | None,
    execution_scope: ExecutionScope,
    execution_policy: dict | None = None,
) -> tuple[AlphaTradePermission, AlphaPositionAction]:
    if execution_scope == "NO_TRADE":
        return "BLOCK_ALL", "REVIEW_ONLY"
    if execution_scope in REVIEW_ONLY_ALPHA_SCOPES:
        if (execution_policy or {}).get("kr_alpha_risk_trim_under_etf_only", False):
            return "BLOCK_NEW_BUY", "RISK_REDUCE_ONLY"
        return "BLOCK_NEW_BUY", "REVIEW_ONLY"
    if alpha_data_gate == "RED":
        return "BLOCK_ALL", "REVIEW_ONLY"
    if alpha_data_gate == "YELLOW":
        return "BLOCK_NEW_BUY", "REVIEW_ONLY"
    return "ALLOW_NEW", "EXECUTABLE"


def derive_alpha_approval(
    alpha_data_gate: str | None,
    execution_scope: ExecutionScope,
) -> Literal["APPROVED", "RESTRICTED", "BLOCKED"]:
    if alpha_data_gate == "RED" or execution_scope == "NO_TRADE":
        return "BLOCKED"
    if execution_scope != "FULL_WITH_ALPHA":
        return "RESTRICTED"
    if alpha_data_gate == "YELLOW":
        return "RESTRICTED"
    return "APPROVED"


def is_executable_kr_risk_trim(act: TradeAction, execution_policy: dict | None) -> bool:
    """ETF_ONLY 등에서 trade_actions에 Trim으로 남는 kr_alpha 리스크 축소 매도."""
    return _is_kr_alpha_risk_reduction_trim(act, execution_policy)


def _is_kr_alpha_risk_reduction_trim(act: TradeAction, execution_policy: dict | None) -> bool:
    if act.action != "Trim":
        return False
    if not (execution_policy or {}).get("kr_alpha_risk_trim_under_etf_only", False):
        return False
    return float(act.allowed_size_pct or 0) < 0


def _review_only_reason(scope: ExecutionScope, act: TradeAction) -> str:
    if act.action == "Replace":
        return f"{scope} — [이론값·매도금지] target template 미포함 (theoretical Replace)"
    if act.action == "Trim":
        return f"{scope} — [이론값·매도금지] 과체중 Trim (theoretical Trim)"
    return f"{scope} — kr_alpha 실행 금지 (theoretical: {act.action})"


def apply_execution_scope_to_actions(
    actions: list[TradeAction],
    gap_rows: list[GapRow],
    scope: ExecutionScope,
    *,
    execution_policy: dict | None = None,
) -> tuple[list[TradeAction], list[TradeAction]]:
    """Executable vs kr_alpha review-only 분리."""
    gap_map = {r.ticker: r for r in gap_rows}
    executable: list[TradeAction] = []
    review_only: list[TradeAction] = []

    for act in actions:
        row = gap_map.get(act.ticker)
        if act.ticker == "PORTFOLIO":
            if scope == "NO_TRADE":
                executable.append(
                    act.model_copy(
                        update={
                            "action": "No trade",
                            "reason": "Execution scope NO_TRADE — 관찰만",
                            "allowed_size_pct": 0,
                        }
                    )
                )
            else:
                executable.append(act)
            continue

        is_kr = row is not None and row.asset_group == "kr_alpha"
        if scope == "NO_TRADE":
            executable.append(
                TradeAction(
                    ticker=act.ticker,
                    name=act.name,
                    action="No trade",
                    reason="NO_TRADE — 실행 금지",
                    allowed_size_pct=0,
                    priority=act.priority,
                )
            )
            review_only.append(act)
        elif scope in REVIEW_ONLY_ALPHA_SCOPES and is_kr:
            if _is_kr_alpha_risk_reduction_trim(act, execution_policy):
                review_only.append(act)
                executable.append(
                    TradeAction(
                        ticker=act.ticker,
                        name=act.name,
                        action="Trim",
                        reason=f"{scope} — kr_alpha 리스크 축소 Trim (사람 승인·1회 제한)",
                        allowed_size_pct=act.allowed_size_pct,
                        priority="High",
                    )
                )
            else:
                review_only.append(act)
                executable.append(
                    TradeAction(
                        ticker=act.ticker,
                        name=act.name,
                        action="Review-only",
                        reason=_review_only_reason(scope, act),
                        allowed_size_pct=0,
                        priority="Low",
                    )
                )
        else:
            executable.append(act)

    return executable, review_only


def scope_blocks_kr_alpha_execution(scope: ExecutionScope) -> bool:
    return scope in REVIEW_ONLY_ALPHA_SCOPES


def kr_alpha_report_mode(scope: ExecutionScope | None) -> Literal["review_only", "executable"]:
    if scope == "FULL_WITH_ALPHA":
        return "executable"
    return "review_only"
