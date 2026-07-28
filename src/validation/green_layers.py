"""Technical / Operational / Market / Full GREEN layer evaluation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from src.report.execution_metrics import count_executable_actions
from src.report.io_utils import read_output_json
from src.validation.bundle_consistency import verify_bundle_snapshot_alignment

LayerStatus = Literal["GREEN", "YELLOW", "RED"]

EXECUTION_SCOPE_EXPLANATION = (
    "ETF_ONLY is scope restriction, not ETF buy permission. "
    "Actual Buy Allowed=0 means no new buys including ETF."
)
TECHNICAL_GREEN_NOTE = (
    "Technical GREEN means system integrity is restored. It does not mean buy permission."
)


def _tg_detail(health_doc: dict[str, Any] | None) -> dict[str, Any]:
    if not health_doc:
        return {}
    for chk in health_doc.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == "target_portfolio_guard":
            return chk.get("detail") or {}
    return {}


def _run_restore_occurred(output_dir: Path, run_id: str | None) -> bool:
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    if final.get("target_restore_occurred"):
        return True
    if not run_id:
        return False
    log_path = output_dir / "decision_log.jsonl"
    if not log_path.exists():
        return False
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("run_id") != run_id:
            continue
        if ev.get("event") == "target_restore":
            return True
        if ev.get("event") == "bundle_reconciliation" and ev.get("restore_occurred"):
            return True
    return False


def _target_write_audit_status(output_dir: Path, run_id: str | None) -> str:
    from src.alpha.target_write_audit import get_last_target_write_audit

    audit = get_last_target_write_audit(output_dir)
    if run_id and audit.get("run_id") and audit.get("run_id") != run_id:
        audit = {}
    log_path = output_dir / "decision_log.jsonl"
    if run_id and log_path.exists():
        for line in log_path.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("run_id") != run_id:
                continue
            if ev.get("event") == "target_write_audit" and ev.get("target_write_allowed") is False:
                return "FAIL"
    if audit.get("target_write_allowed") is False:
        return "FAIL"
    if not audit:
        return "PASS"
    return "PASS"


def _status_from_flags(*, green: bool, red: bool) -> LayerStatus:
    if red:
        return "RED"
    if green:
        return "GREEN"
    return "YELLOW"


def evaluate_green_layers(
    data_dir: Path,
    output_dir: Path,
    *,
    health_doc: dict[str, Any] | None = None,
    acceptance_doc: dict[str, Any] | None = None,
    final_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    health_doc = health_doc or read_output_json(output_dir / "system_health.json") or {}
    acceptance_doc = acceptance_doc or read_output_json(output_dir / "acceptance_report.json") or {}
    final_doc = final_doc or read_output_json(output_dir / "final_execution_decision.json") or {}

    tg = _tg_detail(health_doc)
    alignment = verify_bundle_snapshot_alignment(output_dir)
    metrics = count_executable_actions(final_doc)
    alignment = verify_bundle_snapshot_alignment(output_dir)
    if final_doc.get("target_guard_conflict_detected"):
        metrics["actual_buy_allowed_count"] = 0
    if final_doc.get("snapshot_stale") or not alignment.get("aligned"):
        metrics["actual_buy_allowed_count"] = 0

    run_id = (
        final_doc.get("run_id")
        or acceptance_doc.get("run_id")
        or (read_output_json(output_dir / "run_manifest.json") or {}).get("run_id")
    )
    restore_occurred = _run_restore_occurred(output_dir, run_id) or bool(final_doc.get("target_restore_occurred"))
    conflict_detected = bool(final_doc.get("target_guard_conflict_detected"))
    audit_status = _target_write_audit_status(output_dir, run_id)

    target_hash = str(tg.get("current_hash") or "")
    user_hash = str(tg.get("user_target_hash") or "")
    hash_match = bool(target_hash and user_hash and target_hash == user_hash)

    technical_reasons: list[str] = []
    technical_blockers: list[str] = []

    if health_doc.get("overall") == "pass":
        technical_reasons.append("health_overall=pass")
    else:
        technical_blockers.append(f"health_overall={health_doc.get('overall')}")

    if tg.get("severity") == "PASS":
        technical_reasons.append("target_guard=PASS")
    else:
        technical_blockers.append(f"target_guard={tg.get('severity')}")

    if hash_match:
        technical_reasons.append("target_hash=user_target_hash")
    else:
        technical_blockers.append("target_hash!=user_target_hash")

    for label, val in (
        ("changed_rows", tg.get("changed_rows", 0)),
        ("proposal_leak", tg.get("system_proposal_leak_count", 0)),
        ("material", tg.get("unknown_material_count", 0)),
    ):
        if int(val or 0) == 0:
            technical_reasons.append(f"{label}=0")
        else:
            technical_blockers.append(f"{label}={val}")

    if not restore_occurred:
        technical_reasons.append("restore_occurred=False")
    else:
        technical_blockers.append("restore_occurred=True")

    if not conflict_detected:
        technical_reasons.append("conflict_detected=False")
    else:
        technical_blockers.append("conflict_detected=True")

    if alignment.get("aligned"):
        technical_reasons.append("snapshot_alignment=True")
    else:
        technical_blockers.append("snapshot_alignment=False")

    if audit_status == "PASS":
        technical_reasons.append("target_write_audit=PASS")
    else:
        technical_blockers.append(f"target_write_audit={audit_status}")

    technical_red = (
        tg.get("severity") == "FAIL"
        or health_doc.get("overall") == "fail"
        or audit_status == "FAIL"
        or conflict_detected
        or bool(final_doc.get("snapshot_stale"))
        or not alignment.get("aligned")
    )
    technical_green = (
        not technical_blockers
        and not technical_red
        and not restore_occurred
        and alignment.get("aligned")
        and not final_doc.get("snapshot_stale")
    )
    if restore_occurred and not technical_red:
        technical_status: LayerStatus = "YELLOW"
    else:
        technical_status = _status_from_flags(green=technical_green, red=technical_red)

    acceptance_overall = str(acceptance_doc.get("overall") or final_doc.get("system_status") or "YELLOW")
    actual_buy = int(metrics.get("actual_buy_allowed_count") or 0)
    risk_reduce_only = actual_buy == 0 and int(metrics.get("risk_reduce_trim_count") or 0) > 0

    from src.report.authoritative_status import _acceptance_gate, _gate_is_red

    unified_gate = _acceptance_gate(acceptance_doc, ac_id="AC-02", name="unified_data_gate")
    portfolio_gate = _acceptance_gate(acceptance_doc, ac_id="AC-03", name="portfolio_gate")
    acceptance_scope = str(acceptance_doc.get("execution_scope") or "")
    final_scope = str(final_doc.get("execution_scope") or "")
    force_no_trade = (
        acceptance_overall.upper() == "RED"
        or _gate_is_red(unified_gate)
        or _gate_is_red(portfolio_gate)
    )
    if force_no_trade:
        execution_scope = "NO_TRADE"
    elif acceptance_scope:
        execution_scope = acceptance_scope
    else:
        execution_scope = final_scope
    policy_cap = final_doc.get("policy_cap") or {}
    no_trade = execution_scope == "NO_TRADE" or acceptance_overall == "RED"

    operational_blockers: list[str] = []
    if acceptance_overall != "GREEN":
        operational_blockers.append(f"acceptance_overall={acceptance_overall}")
    if actual_buy <= 0:
        operational_blockers.append("Actual Buy Allowed=0")
    if restore_occurred:
        operational_blockers.append("restore_occurred=True")
    if conflict_detected:
        operational_blockers.append("target_guard_conflict_detected=True")
    if final_doc.get("snapshot_stale") or not alignment.get("aligned"):
        operational_blockers.append("snapshot_stale=True")
    if no_trade:
        operational_blockers.append(f"execution_scope={execution_scope}")
    if policy_cap.get("active"):
        operational_blockers.append(f"policy_cap_active={policy_cap.get('cap_regime')}")
    if risk_reduce_only:
        operational_blockers.append("risk_reduce_only")

    operational_red = no_trade or acceptance_overall == "RED"
    operational_green = (
        acceptance_overall == "GREEN"
        and actual_buy > 0
        and not restore_occurred
        and not conflict_detected
        and not no_trade
        and not policy_cap.get("active")
    )
    operational_status = _status_from_flags(green=operational_green, red=operational_red)

    from src.validation.market_gate import collect_market_gate_inputs, evaluate_market_layer

    market_inputs = collect_market_gate_inputs(
        data_dir,
        output_dir,
        final_doc=final_doc,
        acceptance_doc=acceptance_doc,
    )
    market_eval = evaluate_market_layer(
        market_inputs,
        actual_buy_allowed=actual_buy,
        conflict_detected=conflict_detected,
    )
    market_status = market_eval["market_status"]
    market_blockers = market_eval["market_blockers"]
    market_green = market_status == "GREEN"
    market_red = market_status == "RED"

    full_green = technical_green and operational_green and market_green
    if technical_status == "RED" or operational_status == "RED" or market_status == "RED":
        full_status: LayerStatus = "RED"
    elif full_green:
        full_status = "GREEN"
    else:
        full_status = "YELLOW"

    buy_permission = actual_buy > 0 and operational_green

    return {
        "technical_status": technical_status,
        "operational_status": operational_status,
        "market_status": market_status,
        "full_status": full_status,
        "technical_green": technical_green,
        "operational_green": operational_green,
        "market_green": market_green,
        "full_green": full_green,
        "technical_green_reasons": technical_reasons,
        "operational_blockers": operational_blockers,
        "market_blockers": market_blockers,
        "market_blocker_count": market_eval.get("market_blocker_count", len(market_blockers)),
        "market_unknowns": market_eval.get("market_unknowns", []),
        "market_red_flags": market_eval.get("market_red_flags", []),
        "market_yellow_flags": market_eval.get("market_yellow_flags", []),
        "market_green_reasons": market_eval.get("market_green_reasons", []),
        "market_gate_detail": market_eval.get("market_gate_detail", {}),
        "market_reason_compact": market_eval.get("market_reason_compact", ""),
        "saa_restart_readiness": market_eval.get("saa_restart_readiness", "NOT_READY"),
        "kr_alpha_restart_readiness": market_eval.get("kr_alpha_restart_readiness", "NOT_READY"),
        "market_notes": market_eval.get("market_notes", []),
        "buy_permission_status": "ALLOWED" if buy_permission else "BLOCKED",
        "risk_reduce_only": risk_reduce_only,
        "etf_only_is_buy_permission": False,
        "actual_buy_allowed": actual_buy,
        "acceptance_overall": acceptance_overall,
        "target_write_audit_status": audit_status,
        "execution_scope": execution_scope,
        "execution_scope_explanation": EXECUTION_SCOPE_EXPLANATION,
        "technical_green_note": TECHNICAL_GREEN_NOTE,
        "green_layer_summary": {
            "technical": {"status": technical_status, "reasons": technical_reasons, "blockers": technical_blockers},
            "operational": {"status": operational_status, "blockers": operational_blockers},
            "market": {
                "status": market_status,
                "blockers": market_blockers,
                "unknowns": market_eval.get("market_unknowns", []),
                "reason_compact": market_eval.get("market_reason_compact", ""),
            },
            "full": {"status": full_status, "green": full_green},
        },
    }


def stamp_green_layers_onto_docs(
    docs: dict[str, dict[str, Any]],
    green: dict[str, Any],
) -> None:
    """Merge green layer fields into acceptance / final / bundle dicts in-place."""
    layer_keys = (
        "technical_status",
        "operational_status",
        "market_status",
        "full_status",
        "technical_green",
        "operational_green",
        "market_green",
        "full_green",
        "technical_green_reasons",
        "operational_blockers",
        "market_blockers",
        "market_blocker_count",
        "market_unknowns",
        "market_red_flags",
        "market_yellow_flags",
        "market_green_reasons",
        "market_gate_detail",
        "market_reason_compact",
        "saa_restart_readiness",
        "kr_alpha_restart_readiness",
        "market_notes",
        "buy_permission_status",
        "risk_reduce_only",
        "etf_only_is_buy_permission",
        "actual_buy_allowed",
        "target_write_audit_status",
        "execution_scope_explanation",
        "green_layer_summary",
    )
    acceptance = docs.get("acceptance")
    if acceptance is not None:
        for k in layer_keys:
            if k in green:
                acceptance[k] = green[k]

    final = docs.get("final")
    if final is not None:
        final["green_layers"] = {
            "technical": green.get("technical_status"),
            "operational": green.get("operational_status"),
            "market": green.get("market_status"),
            "full": green.get("full_status"),
        }
        if green.get("execution_scope"):
            final["execution_scope"] = green.get("execution_scope")
        if green.get("full_status"):
            final["system_status"] = green.get("full_status")
        for k in (
            "technical_green",
            "operational_green",
            "market_green",
            "full_green",
            "technical_green_reasons",
            "operational_blockers",
            "market_blockers",
            "market_blocker_count",
            "market_unknowns",
            "market_red_flags",
            "market_yellow_flags",
            "market_green_reasons",
            "market_gate_detail",
            "market_reason_compact",
            "saa_restart_readiness",
            "kr_alpha_restart_readiness",
            "market_notes",
            "buy_permission_status",
            "risk_reduce_only",
            "etf_only_is_buy_permission",
            "actual_buy_allowed",
            "target_write_audit_status",
            "execution_scope_explanation",
            "green_layer_summary",
        ):
            if k in green:
                final[k] = green[k]

    bundle = docs.get("bundle")
    if bundle is not None:
        summary = dict(green.get("green_layer_summary") or {})
        summary["market_blockers"] = green.get("market_blockers", [])
        bundle["green_layer_summary"] = summary
        bundle["technical_green"] = green.get("technical_green")
        bundle["operational_green"] = green.get("operational_green")
        bundle["market_green"] = green.get("market_green")
        bundle["full_green"] = green.get("full_green")
        bundle["actual_buy_allowed"] = green.get("actual_buy_allowed")
        bundle["risk_reduce_only"] = green.get("risk_reduce_only")
        bundle["execution_scope_explanation"] = green.get("execution_scope_explanation")
        bundle["technical_green_note"] = green.get("technical_green_note")
        bundle["market_gate_detail"] = green.get("market_gate_detail")
        bundle["saa_restart_readiness"] = green.get("saa_restart_readiness")
        bundle["kr_alpha_restart_readiness"] = green.get("kr_alpha_restart_readiness")


def format_green_layer_table_lines(green: dict[str, Any]) -> list[str]:
    """Markdown table for daily_report authoritative section."""
    summary = green.get("green_layer_summary") or {}

    def _reason(layer: str) -> str:
        if layer == "technical":
            reasons = green.get("technical_green_reasons") or []
            blockers = (summary.get("technical") or {}).get("blockers") or []
            return ", ".join(blockers[:3]) if blockers else ", ".join(reasons[:4]) or "—"
        blockers = green.get(f"{layer}_blockers") or (summary.get(layer) or {}).get("blockers") or []
        if layer == "market":
            compact = green.get("market_reason_compact")
            if compact:
                return compact
        return "; ".join(blockers[:8]) if blockers else "conditions met"

    lines = [
        "",
        "### GREEN Layer Status",
        "",
        "| Layer | Status | Reason |",
        "|-------|--------|--------|",
        f"| Technical | **{green.get('technical_status', '—')}** | {_reason('technical')} |",
        f"| Operational | **{green.get('operational_status', '—')}** | {_reason('operational')} |",
        f"| Market | **{green.get('market_status', '—')}** | {_reason('market')} |",
        f"| Full | **{green.get('full_status', '—')}** | composite |",
        f"- **Actual Buy Allowed**: {green.get('actual_buy_allowed', 0)}",
        f"- **risk_reduce_only**: {green.get('risk_reduce_only', False)}",
        f"- **buy_permission_status**: {green.get('buy_permission_status', 'BLOCKED')}",
        f"> {green.get('technical_green_note', TECHNICAL_GREEN_NOTE)}",
        f"> {green.get('execution_scope_explanation', EXECUTION_SCOPE_EXPLANATION)}",
    ]
    from src.validation.market_gate import BUY_ALLOWED_OVERRIDE_NOTE, MARKET_YELLOW_NOTE, PULLBACK_WATCH_NOTE

    for note in green.get("market_notes") or [PULLBACK_WATCH_NOTE, MARKET_YELLOW_NOTE, BUY_ALLOWED_OVERRIDE_NOTE]:
        lines.append(f"> {note}")
    lines.append("")
    return lines
