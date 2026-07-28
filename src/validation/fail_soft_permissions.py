"""v1.0.3 Fail-Soft Validation — Core ETF vs Alpha permission separation."""
from __future__ import annotations

from typing import Any

FINDING_TYPES = frozenset({
    "NORMAL_BLOCK",
    "DATA_DEFECT_BLOCK",
    "OVER_CONSERVATIVE_BLOCK",
    "REPORT_CLARITY_ISSUE",
    "EXECUTION_MISMATCH",
    "MANUAL_REVIEW_REQUIRED",
})

# Alpha auto-buy blocked when shortlist unknown share exceeds this (fail-soft, not portfolio gate).
ALPHA_SECTOR_AUTO_BUY_BLOCK_RATE = 0.30
ALPHA_SECTOR_TOP10_BLOCK_RATE = 1.0
ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT = 80.0


def derive_core_etf_permission(
    *,
    execution_scope: str,
    core_price_gate_status: str,
    health_gate: str,
    data_gate: str,
    portfolio_gate: str,
    allowed_capabilities: list[str],
    policy_permissions: dict[str, str] | None = None,
    dry_run_days: int = 0,
    dry_run_required: int = 10,
) -> str:
    """Core ETF path — independent of alpha candidate sector coverage."""
    if execution_scope == "NO_TRADE":
        return "BLOCKED"
    if core_price_gate_status == "fail" or health_gate == "RED":
        return "BLOCKED"
    if data_gate == "RED" or portfolio_gate == "RED":
        return "BLOCKED"

    policy = policy_permissions or {}
    etf_new = policy.get("etf_new_buy", "ALLOWED")
    if etf_new == "BLOCKED":
        return "BLOCKED"

    has_etf_path = any(
        c in allowed_capabilities for c in ("ETF_REBALANCE", "CASH_PARK", "BOND_PARK", "RISK_REDUCE_TRIM")
    )
    if not has_etf_path and execution_scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "ETF_AND_BETA", "FULL_WITH_ALPHA"}:
        has_etf_path = True

    if not has_etf_path:
        return "BLOCKED"

    if dry_run_days < dry_run_required or etf_new == "REVIEW_ONLY" or data_gate == "YELLOW":
        return "RESTRICTED"
    return "ALLOWED"


def derive_alpha_auto_buy_permission(
    *,
    alpha_trade_permission: str,
    alpha_position_action: str,
    alpha_price_action: str,
    sector_coverage: dict[str, Any] | None,
    alpha_data_gate: str | None = None,
) -> str:
    """Alpha automatic buy — sector data defects block only this path."""
    cov = sector_coverage or {}
    shortlist_unknown = float(cov.get("shortlist_unknown_rate") or 0)
    top10_unknown = float(cov.get("top10_unknown_rate") or 0)
    top10_cov = float(cov.get("top10_sector_coverage_pct") or 0)

    if alpha_data_gate == "RED":
        return "BLOCKED"
    if top10_cov < ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT:
        return "BLOCKED"
    if top10_unknown >= ALPHA_SECTOR_TOP10_BLOCK_RATE:
        return "BLOCKED"
    if shortlist_unknown > ALPHA_SECTOR_AUTO_BUY_BLOCK_RATE:
        return "BLOCKED"
    if alpha_price_action in ("ALPHA_DISABLED", "ALPHA_REVIEW_ONLY"):
        return "BLOCKED"
    if alpha_trade_permission != "ALLOW_NEW":
        return "BLOCKED"
    if alpha_position_action != "EXECUTABLE":
        return "BLOCKED"
    return "ALLOWED"


def derive_alpha_research_permission(
    *,
    alpha_data_gate: str | None,
    candidate_count: int,
    sector_coverage: dict[str, Any] | None = None,
) -> str:
    """Research / WATCH — allowed when screener runs and PIT gate is not RED."""
    if alpha_data_gate == "RED":
        return "BLOCKED"
    if candidate_count <= 0:
        return "RESTRICTED"
    cov = sector_coverage or {}
    if float(cov.get("shortlist_unknown_rate") or 0) >= 1.0:
        return "ALLOWED"  # research still OK; auto-buy is separate
    if alpha_data_gate == "YELLOW":
        return "RESTRICTED"
    return "ALLOWED"


def derive_main_block_reason(
    *,
    actual_buy_allowed: int,
    core_etf_permission: str,
    alpha_auto_buy_permission: str,
    execution_scope: str,
    dry_run_days: int,
    dry_run_required: int,
    sector_coverage: dict[str, Any] | None,
    policy_cap_active: bool,
) -> str:
    if actual_buy_allowed > 0:
        return "EXECUTION_ALLOWED"
    reasons: list[str] = []
    if dry_run_days < dry_run_required:
        reasons.append(f"dry_run {dry_run_days}/{dry_run_required}")
    if execution_scope in {"NO_TRADE", "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW"}:
        reasons.append(f"execution_scope={execution_scope}")
    if policy_cap_active:
        reasons.append("policy_cap_active")
    cov = sector_coverage or {}
    if float(cov.get("shortlist_unknown_rate") or 0) >= 1.0:
        reasons.append("alpha_sector_unknown_100pct")
    elif float(cov.get("top10_sector_coverage_pct") or 100) < ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT:
        reasons.append("top10_sector_coverage_below_80pct")
    elif float(cov.get("holdings_sector_coverage_pct") or 100) < 100:
        reasons.append("holdings_sector_incomplete")
    elif alpha_auto_buy_permission == "BLOCKED":
        reasons.append("alpha_auto_buy_blocked")
    if core_etf_permission == "RESTRICTED" and not reasons:
        reasons.append("core_etf_review_only")
    if core_etf_permission == "BLOCKED" and not reasons:
        reasons.append("core_etf_blocked")
    return " · ".join(reasons) if reasons else "NORMAL_RISK_BLOCK"


def build_fail_soft_permissions(
    *,
    execution_scope: str,
    alpha_trade_permission: str,
    alpha_position_action: str,
    alpha_price_action: str,
    core_price_gate_status: str,
    alpha_price_gate_status: str,
    health_gate: str,
    data_gate: str,
    portfolio_gate: str,
    alpha_data_gate: str | None,
    allowed_capabilities: list[str],
    blocked_capabilities: list[str],
    policy_permissions: dict[str, str] | None,
    sector_coverage: dict[str, Any] | None,
    candidate_count: int,
    actual_buy_allowed: int,
    dry_run_days: int = 0,
    dry_run_required: int = 10,
    policy_cap_active: bool = False,
    alpha_sector_data_gate: str | None = None,
) -> dict[str, Any]:
    core_perm = derive_core_etf_permission(
        execution_scope=execution_scope,
        core_price_gate_status=core_price_gate_status,
        health_gate=health_gate,
        data_gate=data_gate,
        portfolio_gate=portfolio_gate,
        allowed_capabilities=allowed_capabilities,
        policy_permissions=policy_permissions,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
    )
    alpha_auto = derive_alpha_auto_buy_permission(
        alpha_trade_permission=alpha_trade_permission,
        alpha_position_action=alpha_position_action,
        alpha_price_action=alpha_price_action,
        sector_coverage=sector_coverage,
        alpha_data_gate=alpha_data_gate,
    )
    alpha_research = derive_alpha_research_permission(
        alpha_data_gate=alpha_data_gate,
        candidate_count=candidate_count,
        sector_coverage=sector_coverage,
    )
    main_block = derive_main_block_reason(
        actual_buy_allowed=actual_buy_allowed,
        core_etf_permission=core_perm,
        alpha_auto_buy_permission=alpha_auto,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        sector_coverage=sector_coverage,
        policy_cap_active=policy_cap_active,
    )
    return {
        "patch_version": "v1.0.3",
        "core_etf_permission": core_perm,
        "alpha_auto_buy_permission": alpha_auto,
        "alpha_research_permission": alpha_research,
        "main_block_reason": main_block,
        "sector_coverage": sector_coverage or {},
        "sector_risk_cap_status": (sector_coverage or {}).get("sector_risk_cap_status", "GREEN"),
        "alpha_sector_data_gate": alpha_sector_data_gate or alpha_data_gate or "GREEN",
        "manual_review_required": alpha_auto == "BLOCKED" and alpha_research == "ALLOWED",
        "note": (
            "Core ETF and Alpha permissions are independent. "
            "Alpha sector unknown does not block Core ETF path."
        ),
    }
