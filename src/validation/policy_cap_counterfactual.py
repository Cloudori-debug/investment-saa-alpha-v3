"""Policy cap counterfactual — hypothetical buy-path analysis (no config changes)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.execution_scope import derive_alpha_permissions, derive_execution_scope
from src.report.authoritative_status import resolve_authoritative_execution
from src.report.execution_metrics import count_executable_actions
from src.report.io_utils import read_output_json
from src.validation.fail_soft_permissions import build_fail_soft_permissions
from src.validation.fail_soft_pipeline import _sector_coverage_from_gpt

COUNTERFACTUAL_PATH = "outputs/policy_cap_counterfactual.json"
DISCLAIMER = "Counterfactual only — not execution permission. No config, policy cap, or Actual Buy Allowed changed."


from src.validation.core_etf_permission_diagnostics import list_etf_underweight_candidates


def _eligible_etf_candidates(final_doc: dict[str, Any]) -> int:
    return len(list_etf_underweight_candidates(final_doc))


def _target_guard_blocks(output_dir: Path) -> bool:
    health = read_output_json(output_dir / "system_health.json") or {}
    for chk in health.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == "target_portfolio_guard":
            detail = chk.get("detail") or {}
            if str(chk.get("status") or "") == "fail":
                return True
            if str(detail.get("severity") or "").upper() == "FAIL":
                return True
    return False


def _alpha_gate_status(output_dir: Path, perms: dict[str, Any]) -> str:
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    for item in acceptance.get("items") or []:
        if isinstance(item, dict) and item.get("id") == "AC-04":
            msg = str(item.get("message") or "")
            if "gate=" in msg:
                return msg.split("gate=", 1)[-1].strip()
    return str((perms.get("gates") or {}).get("alpha_gate") or "YELLOW")


def _evaluate_scenario(
    *,
    scenario_name: str,
    assumed_changes: list[str],
    final_doc: dict[str, Any],
    perms: dict[str, Any],
    base: dict[str, Any],
    cov: dict[str, Any],
    shortlist_eligible: int,
    alpha_candidates: int,
    eligible_etf: int,
    dry_run_days: int,
    dry_run_required: int,
    target_guard_block: bool,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    data_gate = str(overrides.get("data_gate", base["data_gate"]))
    portfolio_gate = str(overrides.get("portfolio_gate", base["portfolio_gate"]))
    health_gate = str(overrides.get("health_gate", base["health_gate"]))
    alpha_data_gate = str(overrides.get("alpha_data_gate", base["alpha_data_gate"]))
    policy_cap_active = bool(overrides.get("policy_cap_active", base["policy_cap_active"]))

    scope = overrides.get("execution_scope")
    if scope is None:
        if overrides.get("assume_data_gate_green"):
            scope = derive_execution_scope(
                data_gate="GREEN",
                portfolio_gate="GREEN",
                alpha_data_gate=alpha_data_gate if overrides.get("assume_alpha_gate_green") else alpha_data_gate,
                health_gate="GREEN",
                dry_run_days=dry_run_days,
            )
        elif not policy_cap_active:
            scope = base.get("technical_execution_scope") or base["execution_scope"]
        else:
            scope = base["execution_scope"]

    policy_permissions = dict(perms.get("policy_permissions") or {})
    if overrides.get("core_etf_unrestricted"):
        policy_permissions["etf_new_buy"] = "ALLOWED"
        policy_permissions["etf_rebalance"] = "ALLOWED"
        policy_permissions["etf_chase_buy"] = "BLOCKED"

    alpha_trade, alpha_pos = derive_alpha_permissions(
        alpha_data_gate=alpha_data_gate,
        execution_scope=scope,  # type: ignore[arg-type]
    )
    if overrides.get("assume_alpha_gate_green"):
        alpha_data_gate = "GREEN"
        if scope in {"FULL_WITH_ALPHA", "ETF_AND_BETA"}:
            alpha_trade, alpha_pos = "ALLOW_NEW", "EXECUTABLE"

    fs = build_fail_soft_permissions(
        execution_scope=str(scope),
        alpha_trade_permission=str(overrides.get("alpha_trade_permission") or alpha_trade),
        alpha_position_action=str(overrides.get("alpha_position_action") or alpha_pos),
        alpha_price_action=str(perms.get("alpha_price_action") or "ALPHA_OK"),
        core_price_gate_status=str((perms.get("gates") or {}).get("core_price_gate", "pass")),
        alpha_price_gate_status=str((perms.get("gates") or {}).get("alpha_price_gate", "pass")),
        health_gate=health_gate,
        data_gate=data_gate,
        portfolio_gate=portfolio_gate,
        alpha_data_gate=alpha_data_gate,
        allowed_capabilities=list(perms.get("allowed_capabilities") or []),
        blocked_capabilities=list(perms.get("blocked_capabilities") or []),
        policy_permissions=policy_permissions,
        sector_coverage=cov,
        candidate_count=alpha_candidates,
        actual_buy_allowed=0,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        policy_cap_active=policy_cap_active,
        alpha_sector_data_gate=str(perms.get("alpha_sector_data_gate") or alpha_data_gate),
    )

    core_perm = fs["core_etf_permission"]
    alpha_perm = fs["alpha_auto_buy_permission"]
    alpha_replace = str(policy_permissions.get("kr_alpha_replace") or perms.get("kr_alpha_replace") or "BLOCKED")

    if overrides.get("core_etf_unrestricted") and not target_guard_block:
        if data_gate != "RED" and portfolio_gate != "RED" and str(scope) != "NO_TRADE":
            core_perm = "ALLOWED"

    alpha_path_open = (
        alpha_perm == "ALLOWED"
        and shortlist_eligible > 0
        and alpha_candidates > 0
    )
    etf_path_open = core_perm == "ALLOWED" and eligible_etf > 0
    would_open = (alpha_path_open or etf_path_open) and not target_guard_block

    hypothetical = 0
    if not target_guard_block:
        if alpha_path_open:
            hypothetical += min(shortlist_eligible, alpha_candidates)
        if etf_path_open:
            hypothetical += eligible_etf

    remaining: list[str] = []
    if target_guard_block:
        remaining.append("target_portfolio_guard=FAIL")
    if policy_cap_active:
        remaining.append("policy_cap_active")
    if str(scope) in {"NO_TRADE", "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW"}:
        remaining.append(f"execution_scope={scope}")
    if data_gate != "GREEN":
        remaining.append(f"data_gate={data_gate}")
    if alpha_data_gate != "GREEN":
        remaining.append(f"alpha_data_gate={alpha_data_gate}")
    if core_perm != "ALLOWED":
        remaining.append(f"core_etf_permission={core_perm}")
    if alpha_perm != "ALLOWED":
        remaining.append(f"alpha_auto_buy_permission={alpha_perm}")
    if shortlist_eligible == 0:
        remaining.append("shortlist_eligible=0")
    if alpha_candidates == 0 and shortlist_eligible == 0:
        remaining.append("eligible_alpha_candidates=0")
    if eligible_etf == 0:
        remaining.append("eligible_etf_candidates=0")
    if dry_run_days < dry_run_required:
        remaining.append(f"dry_run={dry_run_days}/{dry_run_required}")

    scope_str = str(scope)
    residual_scope = scope_str if scope_str in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "NO_TRADE"} else None
    alpha_path_blocker = "none"
    if shortlist_eligible == 0:
        alpha_path_blocker = "shortlist_eligible=0"
    elif alpha_perm != "ALLOWED":
        alpha_path_blocker = f"alpha_auto_buy_permission={alpha_perm}"

    if etf_path_open:
        first_for_etf = "none_for_etf_path"
    elif remaining:
        first_for_etf = remaining[0]
    else:
        first_for_etf = "none"

    first_remaining = remaining[0] if remaining else "none"
    if etf_path_open and first_remaining.startswith("execution_scope="):
        first_remaining = first_for_etf

    explanation_parts = [
        f"scope={scope}",
        f"core_etf={core_perm}",
        f"alpha_auto={alpha_perm}",
        f"shortlist_eligible={shortlist_eligible}",
        f"hypothetical_buys={hypothetical}",
    ]

    return {
        "scenario_name": scenario_name,
        "assumed_changes": assumed_changes,
        "would_open_buy_path": would_open,
        "etf_path_open": etf_path_open,
        "alpha_path_open": alpha_path_open,
        "hypothetical_actual_buy_allowed": hypothetical,
        "remaining_blockers": remaining,
        "first_remaining_blocker": first_remaining,
        "first_remaining_blocker_for_etf_path": first_for_etf,
        "residual_scope_constraint": residual_scope,
        "alpha_path_blocker": alpha_path_blocker,
        "eligible_alpha_candidates_count": alpha_candidates if shortlist_eligible > 0 else 0,
        "shortlist_eligible_count": shortlist_eligible,
        "eligible_etf_candidates_count": eligible_etf,
        "core_etf_permission": core_perm,
        "alpha_auto_buy_permission": alpha_perm,
        "alpha_replace_permission": alpha_replace,
        "execution_scope": str(scope),
        "explanation": " · ".join(explanation_parts),
        "disclaimer": DISCLAIMER,
    }


def build_policy_cap_counterfactual(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    perms = final_doc.get("execution_permissions") or {}
    policy_cap = final_doc.get("policy_cap") or {}
    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc, acceptance_doc=acceptance)
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    metrics = count_executable_actions(final_doc)

    shadow = read_output_json(output_dir / "shadow_diagnostic.json") or {}
    dry_run_required = int((shadow.get("gates") or {}).get("dry_run_required") or 10)
    from src.execution_scope import count_dry_run_days

    dry_run_days = count_dry_run_days(output_dir)

    shortlist_summary = read_output_json(output_dir / "alpha_shortlist_summary.json") or {}
    shortlist_eligible = int(shortlist_summary.get("shortlist_eligible_count") or 0)
    alpha_candidates = int(shortlist_summary.get("shortlisted_count") or 0)
    gpt = read_output_json(output_dir / "gpt_context.json") or {}
    gpt_count = len(gpt.get("top_candidates") or [])
    if alpha_candidates == 0:
        alpha_candidates = gpt_count

    eligible_etf = _eligible_etf_candidates(final_doc)
    target_guard_block = _target_guard_blocks(output_dir)

    gates = perms.get("gates") or {}
    base = {
        "execution_scope": auth.get("execution_scope") or final_doc.get("execution_scope"),
        "technical_execution_scope": policy_cap.get("technical_execution_scope")
        or final_doc.get("execution_scope"),
        "data_gate": final_doc.get("data_gate") or gates.get("data_gate") or "YELLOW",
        "portfolio_gate": auth.get("portfolio_gate") or gates.get("portfolio_gate") or "GREEN",
        "health_gate": gates.get("health_gate") or "YELLOW",
        "alpha_data_gate": perms.get("alpha_sector_data_gate") or sector_gate or _alpha_gate_status(output_dir, perms),
        "policy_cap_active": bool(policy_cap.get("active")),
    }

    scenario_defs = [
        (
            "current_policy",
            ["none — observed production state"],
            {},
        ),
        (
            "policy_cap_removed_only",
            ["policy_cap_active=false", "technical_execution_scope restored"],
            {"policy_cap_active": False, "execution_scope": base["technical_execution_scope"]},
        ),
        (
            "policy_cap_removed_and_alpha_gate_green",
            [
                "policy_cap_active=false",
                "alpha_data_gate=GREEN assumed",
                "shortlist/pillar rules unchanged",
            ],
            {
                "policy_cap_active": False,
                "assume_alpha_gate_green": True,
                "alpha_data_gate": "GREEN",
                "execution_scope": base["technical_execution_scope"],
            },
        ),
        (
            "policy_cap_removed_and_core_etf_unrestricted",
            [
                "policy_cap_active=false",
                "policy_permissions.etf_new_buy=ALLOWED",
                "policy_permissions.etf_rebalance=ALLOWED",
            ],
            {
                "policy_cap_active": False,
                "core_etf_unrestricted": True,
                "execution_scope": base["technical_execution_scope"],
            },
        ),
        (
            "all_soft_blockers_cleared",
            [
                "policy_cap_active=false",
                "data_gate=GREEN",
                "portfolio_gate=GREEN",
                "health_gate=GREEN",
                "alpha_data_gate=GREEN",
                "core_etf_unrestricted",
                "sector_coverage OK (observed)",
                "target_guard/hard-stop rules unchanged",
            ],
            {
                "policy_cap_active": False,
                "assume_data_gate_green": True,
                "assume_alpha_gate_green": True,
                "data_gate": "GREEN",
                "portfolio_gate": "GREEN",
                "health_gate": "GREEN",
                "alpha_data_gate": "GREEN",
                "core_etf_unrestricted": True,
            },
        ),
    ]

    scenarios: dict[str, Any] = {}
    for name, changes, overrides in scenario_defs:
        scenarios[name] = _evaluate_scenario(
            scenario_name=name,
            assumed_changes=changes,
            final_doc=final_doc,
            perms=perms,
            base=base,
            cov=cov,
            shortlist_eligible=shortlist_eligible,
            alpha_candidates=alpha_candidates,
            eligible_etf=eligible_etf,
            dry_run_days=dry_run_days,
            dry_run_required=dry_run_required,
            target_guard_block=target_guard_block,
            overrides=overrides,
        )

    actual_buy = metrics["actual_buy_allowed_count"]
    primary_blocker = "none"
    if actual_buy == 0:
        if shortlist_eligible == 0:
            primary_blocker = "shortlist_eligible=0"
        elif scenarios["current_policy"]["core_etf_permission"] != "ALLOWED":
            primary_blocker = f"core_etf_permission={scenarios['current_policy']['core_etf_permission']}"
        elif base["policy_cap_active"]:
            primary_blocker = "policy_cap_active"

    recommended: list[str] = []
    if not scenarios["policy_cap_removed_only"]["would_open_buy_path"]:
        recommended.append(
            "policy_cap_removed_only does not open buy path — policy cap is not the sole primary blocker"
        )
    if scenarios["policy_cap_removed_and_alpha_gate_green"]["would_open_buy_path"] is False and shortlist_eligible == 0:
        recommended.append(
            "Alpha gate GREEN assumption still leaves shortlist_eligible=0 — improve QVM-SR pillar pass (see alpha_shortlist_summary.json)"
        )
    if scenarios["policy_cap_removed_and_core_etf_unrestricted"]["would_open_buy_path"]:
        recommended.append(
            "Core ETF unrestricted opens ETF buy path — review data_gate YELLOW and etf_new_buy REVIEW_ONLY as ETF bottlenecks"
        )
    elif eligible_etf > 0 and base["data_gate"] == "YELLOW":
        recommended.append(
            "ETF underweight candidates exist but data_gate=YELLOW keeps core_etf RESTRICTED even without policy cap"
        )
    if not recommended:
        recommended.append("Monitor gates; counterfactual paths remain blocked")

    # Top-level policy_cap required by diagnostics_cache.verify_diagnostics_outputs
    policy_cap_summary = {
        "active": bool(policy_cap.get("active")),
        "cap_regime": policy_cap.get("cap_regime"),
        "cap_source": policy_cap.get("cap_source"),
        "max_execution_scope": policy_cap.get("max_execution_scope")
        or policy_cap.get("capped_execution_scope"),
        "technical_execution_scope": policy_cap.get("technical_execution_scope"),
        "expiry_status": policy_cap.get("expiry_status"),
        "regime_expires_date": policy_cap.get("regime_expires_date"),
        "days_to_expiry": policy_cap.get("days_to_expiry"),
    }

    return {
        "schema_version": "1.0",
        "disclaimer": DISCLAIMER,
        "as_of": final_doc.get("as_of") or acceptance.get("as_of"),
        "run_id": final_doc.get("run_id") or acceptance.get("run_id"),
        "policy_cap": policy_cap_summary,
        "actual_state": {
            "actual_buy_allowed": actual_buy,
            "policy_cap_active": base["policy_cap_active"],
            "policy_cap_regime": policy_cap.get("cap_regime"),
            "execution_scope": base["execution_scope"],
            "technical_execution_scope": base["technical_execution_scope"],
            "data_gate": base["data_gate"],
            "alpha_data_gate": base["alpha_data_gate"],
            "shortlist_eligible_count": shortlist_eligible,
            "eligible_etf_candidates_count": eligible_etf,
            "target_guard_blocks": target_guard_block,
            "primary_blocker_estimate": primary_blocker,
        },
        "scenarios": scenarios,
        "recommended_next_action": recommended,
        "interpretation_guide": {
            "policy_cap_not_primary": not scenarios["policy_cap_removed_only"]["would_open_buy_path"],
            "shortlist_blocks_alpha": shortlist_eligible == 0,
            "etf_path_opens_when_unrestricted": scenarios["policy_cap_removed_and_core_etf_unrestricted"]["would_open_buy_path"],
            "all_soft_required_for_any_path": scenarios["all_soft_blockers_cleared"]["would_open_buy_path"],
        },
    }


def build_counterfactual_results_for_no_action(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Compact counterfactual map for no_action_diagnostics.json."""
    doc = build_policy_cap_counterfactual(data_dir, output_dir)
    scenarios = doc.get("scenarios") or {}
    compact = {name: scenarios[name] for name in scenarios if isinstance(scenarios[name], dict)}
    compact["disclaimer"] = DISCLAIMER
    compact["recommended_next_action"] = doc.get("recommended_next_action") or []
    compact["actual_state"] = doc.get("actual_state") or {}
    return compact


def write_policy_cap_counterfactual(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = build_policy_cap_counterfactual(data_dir, output_dir)
    path = output_dir / "policy_cap_counterfactual.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def format_policy_cap_counterfactual_report_lines(doc: dict[str, Any]) -> list[str]:
    actual = doc.get("actual_state") or {}
    scenarios = doc.get("scenarios") or {}
    cur = scenarios.get("current_policy") or {}
    removed = scenarios.get("policy_cap_removed_only") or {}
    etf_unres = scenarios.get("policy_cap_removed_and_core_etf_unrestricted") or {}
    all_soft = scenarios.get("all_soft_blockers_cleared") or {}
    rec = doc.get("recommended_next_action") or []

    return [
        "### No-action / Policy Cap Counterfactual",
        f"> **{DISCLAIMER}**",
        f"- **Actual Buy Allowed**: {actual.get('actual_buy_allowed', 0)} · "
        f"policy_cap={'active' if actual.get('policy_cap_active') else 'inactive'} "
        f"({actual.get('policy_cap_regime', '—')})",
        f"- **Current buy path (observed)**: `{cur.get('would_open_buy_path', False)}` · "
        f"blocker `{cur.get('first_remaining_blocker', '—')}`",
        f"- **policy_cap_removed_only**: buy_path=`{removed.get('would_open_buy_path')}` · "
        f"hypothetical_buys={removed.get('hypothetical_actual_buy_allowed', 0)} · "
        f"first_blocker=`{removed.get('first_remaining_blocker', '—')}`",
        f"- **core_etf_unrestricted**: buy_path=`{etf_unres.get('would_open_buy_path')}` · "
        f"hypothetical_buys={etf_unres.get('hypothetical_actual_buy_allowed', 0)}",
        f"- **all_soft_blockers_cleared**: buy_path=`{all_soft.get('would_open_buy_path')}` · "
        f"hypothetical_buys={all_soft.get('hypothetical_actual_buy_allowed', 0)} · "
        f"shortlist_eligible={actual.get('shortlist_eligible_count', 0)}",
        f"- **Recommended**: {rec[0] if rec else '—'}",
        f"- **Detail**: `{COUNTERFACTUAL_PATH}`",
        "",
    ]
