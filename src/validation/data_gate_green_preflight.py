"""Data gate GREEN preflight — counterfactual PMI scenarios only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.report.execution_metrics import count_executable_actions
from src.report.io_utils import read_output_json
from src.validation.core_etf_permission_diagnostics import list_etf_underweight_candidates
from src.validation.policy_cap_counterfactual import _evaluate_scenario

PREFLIGHT_JSON = "outputs/data_gate_green_preflight.json"
COUNTERFACTUAL_WARNING = (
    "Counterfactual preflight only — does not change Actual Buy Allowed, "
    "data_gate status, policy cap, target write, or approval_bridge."
)


def _adjust_blockers_for_scenario(
    *,
    scenario: str,
    primary: list[str],
    secondary: list[str],
    stale_fields: list[str],
) -> tuple[list[str], list[str], list[str]]:
    primary = list(primary)
    secondary = list(secondary)
    stale = list(stale_fields)

    if scenario == "current":
        return primary, secondary, stale

    if scenario in {"pmi_kr_manual_verified_assumed", "pmi_kr_excluded_as_unavailable_assumed"}:
        stale = [f for f in stale if f != "pmi_kr"]
        if "tier2_stale" in primary and not any(f for f in stale if f in {"pmi_kr", "cpi_kr_yoy"}):
            primary = [p for p in primary if p != "tier2_stale"]
        return primary, secondary, stale

    return primary, secondary, stale


def _core_etf_if_data_gate_green(
    *,
    data_dir: Path,
    output_dir: Path,
    would_green: bool,
) -> tuple[str, int]:
    if not would_green:
        return "RESTRICTED", 0

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    perms = final_doc.get("execution_permissions") or {}
    core_etf_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    eligible_etf = len(list_etf_underweight_candidates(final_doc))
    if not eligible_etf:
        eligible_etf = int(core_etf_doc.get("eligible_etf_underweight_count") or 0)

    from src.report.authoritative_status import resolve_authoritative_execution
    from src.validation.fail_soft_pipeline import _sector_coverage_from_gpt
    from src.validation.policy_cap_counterfactual import _alpha_gate_status, _target_guard_blocks
    from src.execution_scope import count_dry_run_days

    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc, acceptance_doc=acceptance)
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    shadow = read_output_json(output_dir / "shadow_diagnostic.json") or {}
    dry_run_required = int((shadow.get("gates") or {}).get("dry_run_required") or 10)
    dry_run_days = count_dry_run_days(output_dir)
    shortlist_summary = read_output_json(output_dir / "alpha_shortlist_summary.json") or {}
    shortlist_eligible = int(shortlist_summary.get("shortlist_eligible_count") or 0)
    alpha_candidates = int(shortlist_summary.get("shortlisted_count") or 0)
    policy_cap = final_doc.get("policy_cap") or {}
    gates = perms.get("gates") or {}
    base = {
        "execution_scope": auth.get("execution_scope") or final_doc.get("execution_scope"),
        "technical_execution_scope": policy_cap.get("technical_execution_scope")
        or final_doc.get("execution_scope"),
        "data_gate": "GREEN",
        "portfolio_gate": auth.get("portfolio_gate") or gates.get("portfolio_gate") or "GREEN",
        "health_gate": gates.get("health_gate") or "YELLOW",
        "alpha_data_gate": perms.get("alpha_sector_data_gate") or sector_gate or _alpha_gate_status(output_dir, perms),
        "policy_cap_active": bool(policy_cap.get("active")),
    }
    evaluated = _evaluate_scenario(
        scenario_name="data_gate_green_preflight",
        assumed_changes=["data_gate=GREEN assumed (pmi scenario only)"],
        final_doc=final_doc,
        perms=perms,
        base=base,
        cov=cov,
        shortlist_eligible=shortlist_eligible,
        alpha_candidates=alpha_candidates,
        eligible_etf=eligible_etf,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        target_guard_block=_target_guard_blocks(output_dir),
        overrides={"data_gate": "GREEN"},
    )
    core_perm = str(evaluated.get("core_etf_permission") or "RESTRICTED")
    if would_green and core_perm == "RESTRICTED" and bool(base.get("policy_cap_active")):
        core_perm = "REVIEW_ONLY"
    hypo = int(evaluated.get("hypothetical_actual_buy_allowed") or 0)
    if would_green and eligible_etf > 0:
        hypo = eligible_etf
    return core_perm, hypo


def _build_scenario(
    *,
    name: str,
    data_dir: Path,
    output_dir: Path,
    dg_doc: dict[str, Any],
    actual_buy: int,
) -> dict[str, Any]:
    primary, secondary, stale = _adjust_blockers_for_scenario(
        scenario=name,
        primary=list(dg_doc.get("primary_data_blockers") or []),
        secondary=list(dg_doc.get("secondary_data_blockers") or []),
        stale_fields=list(dg_doc.get("stale_fields") or []),
    )
    would_green = len(primary) == 0
    core_perm, hypo_etf = _core_etf_if_data_gate_green(
        data_dir=data_dir,
        output_dir=output_dir,
        would_green=would_green,
    )

    notes: list[str] = []
    if name == "pmi_kr_manual_verified_assumed":
        notes.append("Assumes verified=true manual PMI with official source confirmed")
    elif name == "pmi_kr_excluded_as_unavailable_assumed":
        notes.append("Assumes pmi_kr excluded from gate — policy decision only, not applied")
    elif name == "pmi_kr_alt_used_assumed":
        notes.append("pmi_kr_alt tracked separately; pmi_kr remains manual_required")

    return {
        "would_data_gate_turn_green": would_green,
        "remaining_primary_blockers": primary,
        "remaining_secondary_blockers": secondary,
        "stale_fields": stale,
        "core_etf_permission_if_green": core_perm if would_green else str(
            (read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}).get(
                "core_etf_permission", "RESTRICTED"
            )
        ),
        "hypothetical_etf_buy_count": hypo_etf if would_green else 0,
        "actual_buy_allowed_unchanged": actual_buy,
        "warning_counterfactual_only": COUNTERFACTUAL_WARNING,
        "scenario_notes": notes,
    }


def build_data_gate_green_preflight(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    dg_doc = read_output_json(output_dir / "data_gate_diagnostics.json") or {}
    if not dg_doc:
        from src.validation.data_gate_diagnostics import build_data_gate_diagnostics

        dg_doc = build_data_gate_diagnostics(data_dir, output_dir)

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    actual_buy = int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0)

    scenario_names = (
        "current",
        "pmi_kr_manual_verified_assumed",
        "pmi_kr_excluded_as_unavailable_assumed",
        "pmi_kr_alt_used_assumed",
    )
    scenarios = {
        name: _build_scenario(
            name=name,
            data_dir=data_dir,
            output_dir=output_dir,
            dg_doc=dg_doc,
            actual_buy=actual_buy,
        )
        for name in scenario_names
    }

    current = scenarios["current"]
    return {
        "schema_version": "1.0",
        "as_of": dg_doc.get("as_of"),
        "actual_data_gate_status": dg_doc.get("data_gate_status"),
        "actual_primary_blockers": dg_doc.get("primary_data_blockers"),
        "actual_secondary_blockers": dg_doc.get("secondary_data_blockers"),
        "actual_stale_fields": dg_doc.get("stale_fields"),
        "actual_buy_allowed": actual_buy,
        "scenarios": scenarios,
        "summary": {
            "pmi_only_primary_blocker": "pmi_kr" in (dg_doc.get("stale_fields") or [])
            and "tier2_stale" in (dg_doc.get("primary_data_blockers") or []),
            "green_if_pmi_resolved": scenarios["pmi_kr_manual_verified_assumed"]["would_data_gate_turn_green"],
            "green_if_pmi_excluded": scenarios["pmi_kr_excluded_as_unavailable_assumed"]["would_data_gate_turn_green"],
            "pmi_alt_does_not_clear_blocker": not scenarios["pmi_kr_alt_used_assumed"]["would_data_gate_turn_green"],
            "current_matches_actual": (
                current.get("remaining_primary_blockers") == dg_doc.get("primary_data_blockers")
                and current.get("remaining_secondary_blockers") == dg_doc.get("secondary_data_blockers")
            ),
        },
        "warning": COUNTERFACTUAL_WARNING,
        "preflight_path": PREFLIGHT_JSON,
    }


def write_data_gate_green_preflight(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = build_data_gate_green_preflight(data_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "data_gate_green_preflight.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc
