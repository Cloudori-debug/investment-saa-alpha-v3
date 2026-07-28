"""PMI KR manual_verified apply + core ETF permission re-evaluation routine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data_refresh.kosis_tier2_manual import PMI_KR_FIELD, validate_pmi_kr_manual_ready
from src.report.execution_metrics import count_executable_actions
from src.report.io_utils import read_output_json

REEVAL_JSON = "outputs/pmi_kr_manual_verified_reevaluation.json"
ETF_ONLY_NOTE = "ETF_ONLY is execution scope constraint — not ETF buy permission."


def _pmi_provenance(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "tier2_provenance.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    meta = (doc.get("fields") or {}).get(PMI_KR_FIELD)
    return meta if isinstance(meta, dict) else {}


def _target_write_count(output_dir: Path) -> int:
    guard = read_output_json(output_dir / "target_portfolio_guard.json") or {}
    return int(guard.get("changed_rows") or guard.get("write_count") or 0)


def build_pmi_kr_manual_verified_reevaluation(
    data_dir: Path,
    output_dir: Path,
    *,
    refresh_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_pmi_kr_manual_ready(data_dir)
    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    perms = final_doc.get("execution_permissions") or {}
    policy_cap = final_doc.get("policy_cap") or {}
    metrics = count_executable_actions(final_doc)
    actual_buy = int(metrics.get("actual_buy_allowed_count") or 0)

    dg_doc = read_output_json(output_dir / "data_gate_diagnostics.json") or {}
    core_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    preflight = read_output_json(output_dir / "data_gate_green_preflight.json") or {}

    if not validation.get("ready"):
        return {
            "schema_version": "1.0",
            "status": "manual_required_skipped",
            "validation": validation,
            "action_taken": "none — pmi_kr verified=false or required fields incomplete",
            "pmi_kr_provenance": _pmi_provenance(data_dir),
            "data_gate_diagnostics": {
                "status": dg_doc.get("data_gate_status"),
                "primary_blockers": dg_doc.get("primary_data_blockers"),
                "secondary_blockers": dg_doc.get("secondary_data_blockers"),
                "stale_fields": dg_doc.get("stale_fields"),
                "pmi_kr_in_stale": PMI_KR_FIELD in (dg_doc.get("stale_fields") or []),
            },
            "final_execution_decision": {
                "data_gate": final_doc.get("data_gate"),
                "core_etf_permission": perms.get("core_etf_permission"),
                "actual_buy_allowed": actual_buy,
            },
            "core_etf_reevaluation": {
                "observed_permission": perms.get("core_etf_permission"),
                "eligible_etf_underweight": core_doc.get("eligible_etf_underweight_count"),
                "reevaluation_deferred": True,
            },
            "actual_buy_trace": {
                "final_actual_buy_allowed": actual_buy,
                "changed_from_zero": False,
                "change_path": None,
            },
            "safety": _safety_block(policy_cap, output_dir),
            "warning": "Apply verified=true only after official PMI source confirmation.",
            "reevaluation_path": REEVAL_JSON,
        }

    pmi_prov = _pmi_provenance(data_dir)
    primary = list(dg_doc.get("primary_data_blockers") or [])
    stale = list(dg_doc.get("stale_fields") or [])
    pmi_in_stale = PMI_KR_FIELD in stale
    diagnostics_would_green = len(primary) == 0

    verified_scenario = (preflight.get("scenarios") or {}).get("pmi_kr_manual_verified_assumed") or {}
    core_observed = str(perms.get("core_etf_permission") or core_doc.get("core_etf_permission") or "RESTRICTED")
    core_if_green = str(verified_scenario.get("core_etf_permission_if_green") or "REVIEW_ONLY")
    hypo_etf = int(verified_scenario.get("hypothetical_etf_buy_count") or 0)

    final_data_gate = str(final_doc.get("data_gate") or "YELLOW")
    pipeline_rerun_required = final_data_gate != "GREEN" and diagnostics_would_green

    provenance_ok = (
        str(pmi_prov.get("fetch_method") or "") == "manual_verified"
        or str(pmi_prov.get("fetch_status") or "") == "manual_verified"
    ) and str(pmi_prov.get("status") or "") == "fresh"

    actual_buy_changed = actual_buy != 0
    change_path: str | None = None
    if actual_buy_changed:
        change_path = "final_execution_decision.execution_permissions — pipeline recomputed permission"

    return {
        "schema_version": "1.0",
        "status": "manual_verified_applied" if provenance_ok else "manual_verified_pending_provenance",
        "validation": validation,
        "action_taken": "kosis tier2 refresh with manual_verified override"
        if refresh_result
        else "reevaluation from current tier2 provenance",
        "tier2_refresh": refresh_result or {},
        "pmi_kr_provenance": {
            "status": pmi_prov.get("status"),
            "fetch_method": pmi_prov.get("fetch_method"),
            "fetch_status": pmi_prov.get("fetch_status"),
            "source": pmi_prov.get("source"),
            "value_date": pmi_prov.get("value_date"),
            "manual_verified_recorded": provenance_ok,
        },
        "data_gate_diagnostics": {
            "status": dg_doc.get("data_gate_status"),
            "primary_blockers": primary,
            "secondary_blockers": dg_doc.get("secondary_data_blockers"),
            "stale_fields": stale,
            "pmi_kr_in_stale": pmi_in_stale,
            "pmi_kr_removed_from_primary": PMI_KR_FIELD not in stale and "tier2_stale" not in primary,
            "would_be_green_by_diagnostics": diagnostics_would_green,
            "remaining_blockers_if_not_green": primary + list(dg_doc.get("secondary_data_blockers") or []),
        },
        "final_execution_decision": {
            "data_gate": final_data_gate,
            "unified_data_gate": final_doc.get("execution_permissions", {}).get("gates", {}).get("data_gate"),
            "core_etf_permission": core_observed,
            "actual_buy_allowed": actual_buy,
            "pipeline_rerun_required": pipeline_rerun_required,
            "note": "final_execution_decision reflects last pipeline run — rerun pipeline after manual_verified",
        },
        "core_etf_reevaluation": {
            "observed_permission": core_observed,
            "observed_etf_new_buy": (perms.get("policy_permissions") or {}).get("etf_new_buy"),
            "permission_changed_from_restricted": core_observed != "RESTRICTED",
            "if_data_gate_green_permission": core_if_green,
            "eligible_etf_underweight": int(core_doc.get("eligible_etf_underweight_count") or 0),
            "hypothetical_etf_buy_count_if_data_gate_green": hypo_etf,
            "actual_etf_buy_permission_open": core_observed == "ALLOWED"
            and str((perms.get("policy_permissions") or {}).get("etf_new_buy")) == "ALLOWED"
            and actual_buy > 0,
            "remaining_etf_blockers": core_doc.get("restriction_reasons") or [],
        },
        "actual_buy_trace": {
            "final_actual_buy_allowed": actual_buy,
            "changed_from_zero": actual_buy_changed,
            "change_path": change_path,
            "policy_cap_active": bool(policy_cap.get("active")),
            "execution_scope": final_doc.get("execution_scope"),
        },
        "checks": {
            "1_provenance_manual_verified": provenance_ok,
            "2_pmi_kr_removed_from_stale": not pmi_in_stale,
            "3_data_gate_primary_cleared": "tier2_stale" not in primary,
            "4_data_gate_green_diagnostics": diagnostics_would_green,
            "5_core_etf_reevaluated": bool(core_doc),
            "6_actual_buy_trace_recorded": True,
            "7_target_write_zero": _target_write_count(output_dir) == 0,
            "8_approval_bridge_not_connected": True,
        },
        "safety": _safety_block(policy_cap, output_dir),
        "warning": (
            "pmi_kr_excluded_as_unavailable is policy change — not auto-applied. "
            "pmi_kr_alt never auto-maps to pmi_kr."
        ),
        "reevaluation_path": REEVAL_JSON,
    }


def _safety_block(policy_cap: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    return {
        "target_write_count": _target_write_count(output_dir),
        "target_write_zero": _target_write_count(output_dir) == 0,
        "approval_bridge_connected": False,
        "policy_cap_active": bool(policy_cap.get("active")),
        "policy_cap_unchanged": True,
        "pmi_excluded_not_applied": True,
        "pmi_alt_auto_map": False,
        "etf_only_note": ETF_ONLY_NOTE,
    }


def run_pmi_kr_manual_verified_reevaluation(
    data_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Apply manual_verified refresh when ready, then build reevaluation doc."""
    validation = validate_pmi_kr_manual_ready(data_dir)
    refresh_summary: dict[str, Any] | None = None

    if validation.get("ready"):
        from src.validation.kosis_tier2_refresh_diagnostics import run_kosis_tier2_refresh_with_diagnostics

        result, kosis_diag = run_kosis_tier2_refresh_with_diagnostics(
            data_dir,
            output_dir,
            run_discovery_if_invalid=False,
        )
        refresh_summary = {
            "refreshed_fields": result.refreshed_fields,
            "manual_applied_fields": result.manual_applied_fields,
            "stale_after": result.stale_after,
            "manual_required_fields": result.manual_required_fields,
            "kosis_diagnostics_path": kosis_diag.get("diagnostics_path"),
        }
        from src.validation.core_etf_permission_diagnostics import write_core_etf_permission_diagnostics
        from src.validation.data_gate_diagnostics import write_data_gate_diagnostics

        write_core_etf_permission_diagnostics(data_dir, output_dir)
        write_data_gate_diagnostics(data_dir, output_dir)

    return write_pmi_kr_manual_verified_reevaluation(
        data_dir,
        output_dir,
        refresh_result=refresh_summary,
    )


def write_pmi_kr_manual_verified_reevaluation(
    data_dir: Path,
    output_dir: Path,
    *,
    refresh_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc = build_pmi_kr_manual_verified_reevaluation(
        data_dir,
        output_dir,
        refresh_result=refresh_result,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pmi_kr_manual_verified_reevaluation.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def reevaluation_summary_for_no_action(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": doc.get("status"),
        "validation_ready": (doc.get("validation") or {}).get("ready"),
        "pmi_kr_manual_verified": (doc.get("pmi_kr_provenance") or {}).get("manual_verified_recorded"),
        "data_gate_primary_cleared": (doc.get("data_gate_diagnostics") or {}).get("pmi_kr_removed_from_primary"),
        "pipeline_rerun_required": (doc.get("final_execution_decision") or {}).get("pipeline_rerun_required"),
        "core_etf_permission": (doc.get("core_etf_reevaluation") or {}).get("observed_permission"),
        "actual_buy_allowed": (doc.get("actual_buy_trace") or {}).get("final_actual_buy_allowed"),
        "reevaluation_path": REEVAL_JSON,
    }


def format_pmi_kr_reevaluation_report_lines(doc: dict[str, Any]) -> list[str]:
    val = doc.get("validation") or {}
    dg = doc.get("data_gate_diagnostics") or {}
    core = doc.get("core_etf_reevaluation") or {}
    buy = doc.get("actual_buy_trace") or {}
    return [
        "### PMI KR Manual Verified Re-evaluation",
        f"- **Status**: `{doc.get('status', '—')}` · ready=`{val.get('ready')}` · reason: {val.get('reason', '—')}",
        f"- **Provenance**: manual_verified=`{(doc.get('pmi_kr_provenance') or {}).get('manual_verified_recorded')}` · "
        f"pmi in stale=`{dg.get('pmi_kr_in_stale')}`",
        f"- **Data gate (diagnostics)**: primary={dg.get('primary_blockers') or '—'} · "
        f"would GREEN=`{dg.get('would_be_green_by_diagnostics')}`",
        f"- **Core ETF**: observed=`{core.get('observed_permission')}` · "
        f"if GREEN=`{core.get('if_data_gate_green_permission')}` · "
        f"hypo ETF={core.get('hypothetical_etf_buy_count_if_data_gate_green', 0)}",
        f"- **Actual Buy Allowed**: {buy.get('final_actual_buy_allowed', 0)} "
        f"(changed={buy.get('changed_from_zero')}) · pipeline rerun required="
        f"{(doc.get('final_execution_decision') or {}).get('pipeline_rerun_required')}",
        f"- **Detail**: `{REEVAL_JSON}`",
        "",
    ]
