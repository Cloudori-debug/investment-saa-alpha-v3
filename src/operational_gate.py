from __future__ import annotations

from src.models import DataGate
from src.unified_data_gate import effective_data_gate, merge_data_gates

# system_health fail 중 실행 게이트를 RED로 올리는 항목
CRITICAL_HEALTH_NAMES = frozenset({
    "target_weights",
    "positions",
    "load",
    "prices_coverage",
    "core_price_gate",
    "target_portfolio_guard",
})


def is_critical_health_check(check) -> bool:
    return (
        getattr(check, "status", "") == "fail"
        and getattr(check, "name", "") in CRITICAL_HEALTH_NAMES
    )


def operational_overall_status(checks: list) -> str:
    """운용 overall — non-critical fail은 warn (Alpha 제한, ETF 유지)."""
    if any(is_critical_health_check(c) for c in checks):
        return "fail"
    if any(getattr(c, "status", "") == "fail" for c in checks):
        return "warn"
    if any(getattr(c, "status", "") == "warn" for c in checks):
        return "warn"
    return "pass"


def restricted_modes_from_checks(checks: list) -> list[str]:
    modes: list[str] = []
    if any(c.name == "core_price_gate" and c.status == "fail" for c in checks):
        modes.append("CORE_EXECUTION_BLOCKED")
    tg = next((c for c in checks if c.name == "target_portfolio_guard"), None)
    if tg and tg.status == "fail":
        modes.append("TARGET_PORTFOLIO_GUARD_FAIL")
    alpha = next((c for c in checks if c.name == "alpha_price_gate"), None)
    if alpha and alpha.status in ("fail", "warn"):
        action = (getattr(alpha, "detail", None) or {}).get("action", "")
        if alpha.status == "fail" or action == "ALPHA_DISABLED":
            modes.append("ALPHA_DISABLED")
        elif action == "ALPHA_REVIEW_ONLY" or alpha.status == "warn":
            modes.append("ALPHA_REVIEW_ONLY")
    tb = next((c for c in checks if c.name == "tier_b_refresh"), None)
    if tb and tb.status == "warn":
        modes.append("RESEARCH_QUALITY_WARN")
    return modes


def apply_alpha_price_action_to_permissions(
    alpha_price_action: str,
    trade_permission: str,
    position_action: str,
) -> tuple[str, str]:
    """alpha_price_gate.action → Alpha 매매 권한 (ETF·현금 리밸런싱과 분리)."""
    if alpha_price_action == "ALPHA_DISABLED":
        return "BLOCK_ALL", "REVIEW_ONLY"
    if alpha_price_action == "ALPHA_REVIEW_ONLY":
        if trade_permission == "ALLOW_NEW":
            return "BLOCK_NEW_BUY", "REVIEW_ONLY"
        if position_action == "EXECUTABLE":
            return trade_permission, "REVIEW_ONLY"
    return trade_permission, position_action


def gate_from_health_checks(checks: list) -> DataGate:
    """HealthCheck 목록에서 운용 게이트 도출.

    - CRITICAL fail → RED
    - 기타 fail (예: alpha_price_gate) → YELLOW
    - warn → YELLOW
    """
    has_critical_fail = any(
        c.status == "fail" and c.name in CRITICAL_HEALTH_NAMES for c in checks
    )
    if has_critical_fail:
        return "RED"
    if any(c.status == "fail" for c in checks):
        return "YELLOW"
    if any(c.status == "warn" for c in checks):
        return "YELLOW"
    return "GREEN"


def resolve_operational_gate(
    portfolio_gate: str,
    alpha_gate: str | None,
    health_gate: DataGate,
    *,
    merge_alpha: bool = True,
) -> DataGate:
    """portfolio + alpha + health를 하나의 실행 게이트로 통합."""
    base = effective_data_gate(portfolio_gate, alpha_gate, merge_alpha=merge_alpha)
    return merge_data_gates(base, health_gate)


def health_warn_summaries(checks: list) -> list[str]:
    return [f"{c.name}: {c.message}" for c in checks if getattr(c, "status", "") == "warn"]


def explain_operational_gate(
    portfolio_gate: str,
    alpha_gate: str | None,
    health_gate: DataGate,
    *,
    merge_alpha: bool = True,
    health_warns: list[str] | None = None,
) -> dict[str, object]:
    """통합 data_gate 산출 근거 — health가 YELLOW인데 portfolio/alpha가 GREEN일 때 명시."""
    base = effective_data_gate(portfolio_gate, alpha_gate, merge_alpha=merge_alpha)
    merged = merge_data_gates(base, health_gate)
    drivers: list[str] = []
    if portfolio_gate not in ("GREEN", ""):
        drivers.append(f"portfolio_gate={portfolio_gate}")
    if alpha_gate and alpha_gate not in ("GREEN", ""):
        drivers.append(f"alpha_gate={alpha_gate}")
    if health_gate != "GREEN":
        drivers.append(f"health_gate={health_gate}")
        if health_warns:
            drivers.extend(health_warns[:4])
    if not drivers:
        drivers.append("all GREEN")

    parts = [
        f"통합 data_gate={merged}",
        f"(portfolio={portfolio_gate}, alpha={alpha_gate or '—'}, health={health_gate}, base={base})",
    ]
    if health_gate != "GREEN" and base == "GREEN":
        if health_gate == "RED":
            parts.append("— portfolio·alpha는 GREEN, health fail이 RED로 올림")
        else:
            parts.append("— portfolio·alpha는 GREEN, health warn이 YELLOW로 올림")

    return {
        "portfolio_gate": portfolio_gate,
        "alpha_gate": alpha_gate,
        "health_gate": health_gate,
        "base_gate": base,
        "data_gate": merged,
        "drivers": drivers,
        "summary": " ".join(parts),
    }
