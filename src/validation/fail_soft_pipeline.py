"""Wire fail-soft permissions into pipeline outputs — v1.0.3."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.report.execution_metrics import count_executable_actions
from src.validation.fail_soft_permissions import build_fail_soft_permissions
from src.validation.manual_override_ledger import (
    ensure_ledger_template,
    ledger_summary_for_report,
    load_manual_override_ledger,
)
from src.validation.validation_findings import build_validation_findings, write_validation_findings


def _sector_coverage_from_gpt(output_dir: Path) -> tuple[dict[str, Any], str | None]:
    path = output_dir / "gpt_context.json"
    if not path.exists():
        return {}, None
    ctx = json.loads(path.read_text(encoding="utf-8"))
    meta = ctx.get("shortlist_meta") or {}
    kr = ctx.get("kr_alpha_meta") or {}
    cov = kr.get("sector_coverage") or {
        k: meta[k]
        for k in (
            "candidate_sector_coverage_pct",
            "shortlist_unknown_rate",
            "shortlist_unknown_count",
            "shortlist_count",
            "top10_unknown_rate",
            "top10_unknown_count",
            "top10_count",
            "top10_sector_coverage_pct",
        )
        if k in meta
    }
    sector_gate = meta.get("alpha_sector_data_gate") or kr.get("alpha_sector_data_gate")
    return cov, sector_gate


def apply_fail_soft_to_execution_permissions(
    execution_permissions: dict[str, Any],
    *,
    output_dir: Path,
    data_dir: Path,
    alpha_data_gate: str | None,
    candidate_count: int,
    dry_run_days: int,
    dry_run_required: int,
    policy_cap_active: bool,
    executable_actions_preview: list[Any] | None = None,
) -> dict[str, Any]:
    """Merge fail-soft permission block — does not change scoring or trade_actions."""
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    preview_final = {
        "allowed_actions": [],
        "final_trade_list": [],
        "execution_permissions": execution_permissions,
    }
    if executable_actions_preview is not None:
        from src.final_execution_decision import build_final_execution_decision

        # Count only — reuse metrics after full decision exists elsewhere
        pass
    actual_buy = 0

    fail_soft = build_fail_soft_permissions(
        execution_scope=str(execution_permissions.get("execution_scope", "NO_TRADE")),
        alpha_trade_permission=str(execution_permissions.get("alpha_trade_permission", "BLOCK_NEW_BUY")),
        alpha_position_action=str(execution_permissions.get("alpha_position_action", "REVIEW_ONLY")),
        alpha_price_action=str(execution_permissions.get("alpha_price_action", "ALPHA_OK")),
        core_price_gate_status=str(
            (execution_permissions.get("gates") or {}).get("core_price_gate", "pass")
        ),
        alpha_price_gate_status=str(
            (execution_permissions.get("gates") or {}).get("alpha_price_gate", "pass")
        ),
        health_gate=str((execution_permissions.get("gates") or {}).get("health_gate", "GREEN")),
        data_gate=str((execution_permissions.get("gates") or {}).get("data_gate", "GREEN")),
        portfolio_gate=str((execution_permissions.get("gates") or {}).get("portfolio_gate", "GREEN")),
        alpha_data_gate=alpha_data_gate,
        allowed_capabilities=list(execution_permissions.get("allowed_capabilities") or []),
        blocked_capabilities=list(execution_permissions.get("blocked_capabilities") or []),
        policy_permissions=execution_permissions.get("policy_permissions"),
        sector_coverage=cov,
        candidate_count=candidate_count,
        actual_buy_allowed=actual_buy,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        policy_cap_active=policy_cap_active,
        alpha_sector_data_gate=sector_gate,
    )
    merged = dict(execution_permissions)
    merged.update(fail_soft)
    policy = merged.get("policy_permissions") or {}
    if policy:
        merged["kr_alpha_new_buy"] = fail_soft["alpha_auto_buy_permission"]
        merged["kr_alpha_replace"] = policy.get("kr_alpha_replace", "BLOCKED")
    else:
        merged["kr_alpha_new_buy"] = fail_soft["alpha_auto_buy_permission"]
    return merged


def refresh_fail_soft_after_final(
    final_decision: dict[str, Any],
    *,
    output_dir: Path,
    data_dir: Path,
    alpha_data_gate: str | None,
    candidate_count: int,
    dry_run_days: int,
    dry_run_required: int,
    policy_cap_active: bool,
) -> dict[str, Any]:
    """Recompute main_block_reason with actual buy count from final decision."""
    perms = dict(final_decision.get("execution_permissions") or {})
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    metrics = count_executable_actions(final_decision)
    fail_soft = build_fail_soft_permissions(
        execution_scope=str(final_decision.get("execution_scope", "NO_TRADE")),
        alpha_trade_permission=str(perms.get("alpha_trade_permission", "BLOCK_NEW_BUY")),
        alpha_position_action=str(perms.get("alpha_position_action", "REVIEW_ONLY")),
        alpha_price_action=str(perms.get("alpha_price_action", "ALPHA_OK")),
        core_price_gate_status=str((perms.get("gates") or {}).get("core_price_gate", "pass")),
        alpha_price_gate_status=str((perms.get("gates") or {}).get("alpha_price_gate", "pass")),
        health_gate=str((perms.get("gates") or {}).get("health_gate", "GREEN")),
        data_gate=str(final_decision.get("data_gate", "GREEN")),
        portfolio_gate=str((perms.get("gates") or {}).get("portfolio_gate", "GREEN")),
        alpha_data_gate=alpha_data_gate,
        allowed_capabilities=list(perms.get("allowed_capabilities") or []),
        blocked_capabilities=list(perms.get("blocked_capabilities") or []),
        policy_permissions=perms.get("policy_permissions"),
        sector_coverage=cov,
        candidate_count=candidate_count,
        actual_buy_allowed=metrics["actual_buy_allowed_count"],
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        policy_cap_active=policy_cap_active,
        alpha_sector_data_gate=sector_gate,
    )
    perms.update(fail_soft)
    perms["kr_alpha_new_buy"] = fail_soft["alpha_auto_buy_permission"]
    final_decision["execution_permissions"] = perms
    return final_decision


def patch_gpt_context_fail_soft(output_dir: Path, execution_permissions: dict[str, Any]) -> None:
    path = output_dir / "gpt_context.json"
    if not path.exists():
        return
    ctx = json.loads(path.read_text(encoding="utf-8"))
    ctx["core_etf_permission"] = execution_permissions.get("core_etf_permission")
    ctx["alpha_auto_buy_permission"] = execution_permissions.get("alpha_auto_buy_permission")
    ctx["alpha_research_permission"] = execution_permissions.get("alpha_research_permission")
    ctx["fail_soft_patch_version"] = execution_permissions.get("patch_version", "v1.0.3")
    ctx["main_block_reason"] = execution_permissions.get("main_block_reason")
    if execution_permissions.get("sector_coverage"):
        ctx.setdefault("kr_alpha_meta", {})["sector_coverage"] = execution_permissions["sector_coverage"]
    path.write_text(json.dumps(ctx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_fail_soft_artifacts(
    *,
    output_dir: Path,
    data_dir: Path,
    run_id: str,
    as_of: str,
    final_decision: dict[str, Any],
    clarity: dict[str, Any] | None,
    cross_val: dict[str, Any] | None,
) -> dict[str, Any]:
    ensure_ledger_template(data_dir / "manual_override_ledger.csv")
    ledger_rows = load_manual_override_ledger(data_dir / "manual_override_ledger.csv")
    ledger_summary = ledger_summary_for_report(ledger_rows, as_of=as_of)

    perms = final_decision.get("execution_permissions") or {}
    metrics = count_executable_actions(final_decision)
    findings = build_validation_findings(
        run_id=run_id,
        as_of=as_of,
        fail_soft=perms,
        clarity=clarity,
        cross_val=cross_val,
        actual_buy_allowed=metrics["actual_buy_allowed_count"],
        execution_scope=str(final_decision.get("execution_scope", "")),
        dry_run_days=int(final_decision.get("dry_run_days") or 0),
        dry_run_required=int((final_decision.get("operating") or {}).get("dry_run_required") or 10),
        core_etf_permission=str(perms.get("core_etf_permission", "—")),
        alpha_auto_buy_permission=str(perms.get("alpha_auto_buy_permission", "BLOCKED")),
    )
    findings["manual_override_ledger"] = ledger_summary
    write_validation_findings(findings, output_dir / "validation_findings.json")
    return findings
