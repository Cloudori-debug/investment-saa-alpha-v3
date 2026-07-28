from __future__ import annotations

from typing import Any

from src.execution_scope import scope_blocks_kr_alpha_execution
from src.risk_limits import RiskReport


def build_hard_stops_detail(
    risk: RiskReport,
    *,
    execution_scope: str,
    dry_run_days: int,
    dry_run_required: int = 10,
) -> dict[str, Any]:
    """리스크 HARD vs 운용 정책 가드를 분리해 노출."""
    risk_hard = [
        {
            "code": v.code,
            "ticker": v.ticker,
            "detail": v.detail,
            "severity": v.severity,
        }
        for v in risk.violations
        if v.severity == "HARD"
    ]
    policy_guards: list[str] = ["auto_trading_disabled"]
    if dry_run_days < dry_run_required:
        policy_guards.append("dry_run_incomplete")
    policy_guards.append("core_deployment_throttle_active")
    if scope_blocks_kr_alpha_execution(execution_scope):  # type: ignore[arg-type]
        policy_guards.extend(["alpha_new_buy_blocked", "alpha_replace_blocked"])
    if execution_scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "NO_TRADE"}:
        policy_guards.append("etf_only_execution_cap")

    return {
        "risk_hard_stop_count": len(risk_hard),
        "risk_hard_stops": risk_hard,
        "policy_guards": policy_guards,
        "hard_stops": len(risk_hard),
        "note": (
            "hard_stops=포트폴리오 리스크 HARD 건수. "
            "policy_guards=운용 정책(자동매매·dry-run·알파 차단)."
        ),
    }
