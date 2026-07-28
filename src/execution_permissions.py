from __future__ import annotations

from typing import Any

from src.policy_cap import fsr_policy_permissions


def infer_trim_reason(action: str, reason: str) -> str | None:
    if action != "Trim":
        return None
    text = reason.lower()
    if "리스크 축소" in reason or "risk reduce" in text:
        return "risk_reduce"
    if "과체중" in reason or "overweight" in text:
        return "overweight_reduce"
    if "replace" in text or "교체" in reason:
        return "replace_funding"
    if "rebalance" in text or "리밸런스" in reason:
        return "rebalance"
    return "overweight_reduce"


def build_execution_permissions(
    *,
    execution_scope: str,
    alpha_trade_permission: str,
    alpha_position_action: str,
    alpha_price_action: str,
    restricted_modes: list[str],
    health_gate: str,
    core_price_gate_status: str,
    alpha_price_gate_status: str,
    data_gate: str,
    portfolio_gate: str,
    alpha_gate: str,
    policy_cap_active: bool = False,
    max_operational_approval: str = "GREEN",
    cap_regime: str | None = None,
    target_guard_severity: str = "PASS",
) -> dict[str, Any]:
    """최종 권위 파일용 — 오늘 가능/불가능 capability 단일 요약."""
    allowed: list[str] = []
    blocked: list[str] = []

    if execution_scope != "NO_TRADE" and core_price_gate_status != "fail":
        allowed.extend(["ETF_REBALANCE", "CASH_PARK", "BOND_PARK"])

    if alpha_position_action == "RISK_REDUCE_ONLY":
        allowed.append("RISK_REDUCE_TRIM")
    elif alpha_position_action == "EXECUTABLE" and alpha_trade_permission == "ALLOW_NEW":
        allowed.extend(["KR_ALPHA_NEW_BUY", "KR_ALPHA_REPLACE"])

    if alpha_trade_permission in ("BLOCK_NEW_BUY", "BLOCK_ALL"):
        blocked.extend(["KR_ALPHA_NEW_BUY", "KR_ALPHA_ADD"])
    if alpha_trade_permission == "BLOCK_ALL":
        blocked.append("KR_ALPHA_REPLACE")
    if alpha_price_action == "ALPHA_DISABLED":
        blocked.extend(["KR_ALPHA_NEW_BUY", "KR_ALPHA_REPLACE", "KR_ALPHA_ADD"])
    elif alpha_price_action == "ALPHA_REVIEW_ONLY":
        blocked.extend(["KR_ALPHA_NEW_BUY", "KR_ALPHA_ADD"])

    if execution_scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "NO_TRADE"}:
        blocked.extend(["KR_ALPHA_NEW_BUY", "KR_ALPHA_REPLACE"])

    allowed_out: list[str] = []
    for x in allowed:
        if x not in allowed_out:
            allowed_out.append(x)
    blocked_out: list[str] = []
    for x in blocked:
        if x not in blocked_out:
            blocked_out.append(x)

    trim_policy: dict[str, Any] = {
        "executable_trim_reasons": ["risk_reduce", "overweight_reduce"],
        "blocked_trim_reasons": ["replace_funding", "rebalance"],
    }
    if target_guard_severity == "FAIL":
        for cap in ("KR_ALPHA_NEW_BUY", "KR_ALPHA_ADD", "KR_ALPHA_REPLACE", "ETF_REBALANCE"):
            if cap not in blocked_out:
                blocked_out.append(cap)
        allowed_out = [c for c in allowed_out if c not in {
            "KR_ALPHA_NEW_BUY", "KR_ALPHA_REPLACE", "ETF_REBALANCE",
        }]
        trim_policy = {
            "executable_trim_reasons": ["risk_reduce"],
            "blocked_trim_reasons": ["overweight_reduce", "replace_funding", "rebalance"],
            "target_guard_fail": True,
        }
        if "TARGET_PORTFOLIO_GUARD_FAIL" not in restricted_modes:
            restricted_modes = [*restricted_modes, "TARGET_PORTFOLIO_GUARD_FAIL"]

    operating_mode = "GREEN"
    if (
        core_price_gate_status == "fail"
        or health_gate == "RED"
        or data_gate == "RED"
        or target_guard_severity == "FAIL"
    ):
        operating_mode = "RED"
    elif alpha_price_action in ("ALPHA_DISABLED", "ALPHA_REVIEW_ONLY") or alpha_price_gate_status in ("fail", "warn"):
        operating_mode = "YELLOW_ALPHA_RESTRICTED"
    elif health_gate == "YELLOW" or data_gate == "YELLOW":
        operating_mode = "YELLOW_STABLE"

    if policy_cap_active:
        operating_mode = "RED" if max_operational_approval == "RED" else "YELLOW"

    policy_perms = fsr_policy_permissions(cap_regime) if policy_cap_active else {}

    out: dict[str, Any] = {
        "operating_mode": operating_mode,
        "execution_scope": execution_scope,
        "alpha_trade_permission": alpha_trade_permission,
        "alpha_position_action": alpha_position_action,
        "alpha_price_action": alpha_price_action,
        "restricted_modes": restricted_modes,
        "gates": {
            "data_gate": data_gate,
            "portfolio_gate": portfolio_gate,
            "alpha_gate": alpha_gate,
            "health_gate": health_gate,
            "core_price_gate": core_price_gate_status,
            "alpha_price_gate": alpha_price_gate_status,
            "target_portfolio_guard": target_guard_severity,
        },
        "allowed_capabilities": allowed_out,
        "blocked_capabilities": blocked_out,
        "trim_policy": trim_policy,
    }
    if policy_perms:
        out["policy_permissions"] = policy_perms
        if policy_perms.get("etf_chase_buy") == "BLOCKED" and "ETF_CHASE_BUY" not in blocked_out:
            blocked_out.append("ETF_CHASE_BUY")
        out["blocked_capabilities"] = blocked_out
    return out
