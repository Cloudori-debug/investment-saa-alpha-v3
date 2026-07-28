"""Cross-artifact consistency — target_portfolio_guard snapshot alignment."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.report.io_utils import read_output_json
from src.validation.acceptance_check import run_acceptance_check, write_acceptance_report
from src.validation.system_health import SystemHealthReport, run_system_health, write_health_report

SNAPSHOT_STALE_MARKER = "snapshot_stale.json"


def _hash_matches(canonical: str, other: str) -> bool:
    if not other:
        return True
    if not canonical:
        return True
    c = canonical.lower()
    o = other.lower()
    if c == o:
        return True
    # daily_report renders truncated hash (12 chars) in target_portfolio_guard line
    prefix_len = min(len(c), len(o), 12)
    return c[:prefix_len] == o[:prefix_len]


def resolve_pipeline_run_id(output_dir: Path) -> str | None:
    manifest = read_output_json(output_dir / "run_manifest.json") or {}
    run_id = manifest.get("run_id")
    return str(run_id) if run_id else None

def _extract_daily_report_target_hash(report_text: str) -> str:
    """Parse target_portfolio_guard curr hash from daily_report.md."""
    if not report_text:
        return ""
    m = re.search(r"curr\s+`([0-9a-f]{8,})`", report_text)
    return m.group(1) if m else ""


def mark_snapshot_stale(
    output_dir: Path,
    *,
    reason: str,
    write_audit: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    """Record that bundle artifacts are stale after an operational target write."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "snapshot_stale": True,
        "reason": reason,
        "marked_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "target_hash_after": (write_audit or {}).get("target_hash_after"),
        "target_hash_before": (write_audit or {}).get("target_hash_before"),
    }
    (output_dir / SNAPSHOT_STALE_MARKER).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_snapshot_stale_marker(output_dir: Path) -> None:
    path = output_dir / SNAPSHOT_STALE_MARKER
    if path.exists():
        path.unlink()


def detect_snapshot_stale_after_target_write(output_dir: Path) -> dict[str, Any]:
    """True when post-write target hash is not reflected across bundle artifacts."""
    from src.alpha.target_write_audit import get_last_target_write_audit

    write_audit = get_last_target_write_audit(output_dir)
    marker = read_output_json(output_dir / SNAPSHOT_STALE_MARKER) or {}
    alignment = verify_bundle_snapshot_alignment(output_dir)
    if marker.get("snapshot_stale"):
        return {
            "stale": True,
            "reason": marker.get("reason") or "snapshot_stale marker",
            "write_audit": write_audit,
            "alignment": alignment,
        }
    if not write_audit.get("target_write_allowed"):
        return {"stale": False, "alignment": alignment}
    hash_after = str(write_audit.get("target_hash_after") or "")
    if not hash_after:
        return {"stale": False, "alignment": alignment}
    if not alignment.get("aligned"):
        return {
            "stale": True,
            "reason": "target_hash mismatch across bundle artifacts",
            "write_audit": write_audit,
            "alignment": alignment,
        }
    return {"stale": False, "alignment": alignment}


def apply_snapshot_stale_lock(final_doc: dict[str, Any], alignment: dict[str, Any]) -> dict[str, Any]:
    """Block buys and mark snapshot stale — guard PASS may remain; Technical GREEN forbidden."""
    out = dict(final_doc)
    out["snapshot_stale"] = True
    out["snapshot_alignment"] = False
    out["snapshot_alignment_issues"] = alignment.get("issues") or []
    buy_actions = frozenset({"Buy", "Buy-allowed", "Add", "Replace", "Rebalance"})

    patched_allowed: list[dict[str, Any]] = []
    for act in out.get("allowed_actions") or []:
        row = dict(act)
        if row.get("action") in buy_actions:
            continue
        if row.get("action") == "Trim":
            suffix = " — snapshot stale, 사람 승인·재확인"
            if suffix not in str(row.get("reason") or ""):
                row["reason"] = f"{row.get('reason', '')}{suffix}"
        patched_allowed.append(row)
    out["allowed_actions"] = patched_allowed
    out["final_trade_list"] = [
        dict(t) for t in (out.get("final_trade_list") or [])
        if t.get("action") not in buy_actions
    ]

    perms = dict(out.get("execution_permissions") or {})
    perms["snapshot_stale"] = True
    perms["snapshot_alignment"] = False
    perms["manual_review_required"] = True
    perms["main_block_reason"] = "snapshot_stale_after_target_write"
    blocked = list(perms.get("blocked_capabilities") or [])
    for cap in ("KR_ALPHA_NEW_BUY", "KR_ALPHA_ADD", "KR_ALPHA_REPLACE", "ETF_REBALANCE"):
        if cap not in blocked:
            blocked.append(cap)
    perms["blocked_capabilities"] = blocked
    perms["allowed_capabilities"] = [
        c for c in (perms.get("allowed_capabilities") or []) if c not in blocked
    ]
    out["execution_permissions"] = perms
    return out


def refresh_daily_report_authoritative(output_dir: Path, data_dir: Path) -> None:
    """Rebuild authoritative / GREEN / 운용 / SAA sections without full pipeline."""
    from src.report_writer import build_daily_report_status_summary

    report_path = output_dir / "daily_report.md"
    if not report_path.exists():
        return
    old = report_path.read_text(encoding="utf-8")
    auth_idx = old.find("## 최종 실행 권위")
    if auth_idx < 0:
        return
    header = old[:auth_idx]
    tail_idx = old.find("\n## 1.")
    tail = old[tail_idx:] if tail_idx >= 0 else ""

    exposure = read_output_json(output_dir / "exposure_lookthrough.json")
    middle = "\n".join(build_daily_report_status_summary(output_dir, exposure)) + "\n"
    saa_path = output_dir / "saa_restart_readiness_report.md"
    if saa_path.exists():
        middle += saa_path.read_text(encoding="utf-8") + "\n"
    report_path.write_text(header + middle + tail, encoding="utf-8")
    from src.report.execution_metrics import sync_daily_report_system_health_overall

    sync_daily_report_system_health_overall(output_dir)


def write_bundle_consistency_validation(output_dir: Path, result: dict[str, Any]) -> None:
    path = output_dir / "bundle_consistency_validation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_bundle_after_target_write(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str | None = None,
    write_audit: dict[str, Any] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Regenerate acceptance, green layers, SAA report, daily_report, ai_export after target write."""
    final_path = output_dir / "final_execution_decision.json"
    if not final_path.exists():
        mark_snapshot_stale(
            output_dir,
            reason="target write without final_execution_decision — refresh skipped",
            write_audit=write_audit,
            run_id=run_id,
        )
        return {"refreshed": False, "reason": "no final_execution_decision"}

    resolved_run_id = run_id or resolve_pipeline_run_id(output_dir)
    if not resolved_run_id:
        resolved_run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    final_doc = read_output_json(final_path) or {}
    as_of = as_of or str(final_doc.get("as_of") or datetime.now(timezone.utc).date())

    mark_snapshot_stale(
        output_dir,
        reason="target write pending bundle refresh",
        write_audit=write_audit,
        run_id=resolved_run_id,
    )

    result = reconcile_bundle_artifacts(
        data_dir,
        output_dir,
        run_id=resolved_run_id,
        as_of=as_of,
        target_restore_meta={"restored": False},
        post_target_write_refresh=True,
    )
    return {"refreshed": True, "reconcile": result}


def _target_guard_from_health_doc(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not doc:
        return {}
    for chk in doc.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == "target_portfolio_guard":
            return chk.get("detail") or {}
    return {}


def _target_guard_from_acceptance(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not doc:
        return {}
    for item in doc.get("items") or []:
        if isinstance(item, dict) and item.get("name") == "target_portfolio_guard":
            return item.get("detail") or {}
    return {}


def build_health_snapshot_id(
    *,
    run_id: str,
    target_hash: str,
    health_overall: str,
    guard_severity: str,
) -> str:
    payload = json.dumps(
        {
            "run_id": run_id,
            "target_hash": target_hash,
            "health_overall": health_overall,
            "guard_severity": guard_severity,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def detect_target_guard_conflict(
    output_dir: Path,
    *,
    health_doc: dict[str, Any] | None = None,
    acceptance_doc: dict[str, Any] | None = None,
    final_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect mismatched target_portfolio_guard snapshots across bundle artifacts."""
    health_doc = health_doc or read_output_json(output_dir / "system_health.json")
    acceptance_doc = acceptance_doc or read_output_json(output_dir / "acceptance_report.json")
    final_doc = final_doc or read_output_json(output_dir / "final_execution_decision.json")

    health_tg = _target_guard_from_health_doc(health_doc)
    acc_tg = _target_guard_from_acceptance(acceptance_doc)
    perms = (final_doc or {}).get("execution_permissions") or {}
    gates = perms.get("gates") or {}
    final_severity = str(gates.get("target_portfolio_guard", "PASS"))

    health_severity = str(health_tg.get("severity") or health_tg.get("target_portfolio_guard_severity") or "PASS")
    acc_severity = str(acc_tg.get("severity") or acc_tg.get("target_portfolio_guard_severity") or "PASS")

    health_hash = str(health_tg.get("current_hash") or "")
    acc_hash = str(acc_tg.get("current_hash") or "")

    severity_mismatch = len({health_severity, acc_severity, final_severity} - {"PASS"}) > 1 or (
        health_severity != acc_severity
    )
    hash_mismatch = bool(health_hash and acc_hash and health_hash != acc_hash)
    guard_fail = health_severity == "FAIL" or acc_severity == "FAIL"

    conflict_detected = severity_mismatch or hash_mismatch or (
        guard_fail and final_severity == "PASS"
    )

    health_snap = (health_doc or {}).get("meta", {}).get("health_snapshot_id", "")
    acc_snap = (acceptance_doc or {}).get("health_snapshot_id", "")
    bundle_path = output_dir / "ai_export_bundle.json"
    bundle_snap = ""
    if bundle_path.exists():
        bundle = read_output_json(bundle_path) or {}
        bundle_snap = str((bundle.get("health_report") or {}).get("meta", {}).get("health_snapshot_id", ""))

    snapshot_mismatch = bool(
        health_snap and acc_snap and health_snap != acc_snap
    ) or bool(health_snap and bundle_snap and health_snap != bundle_snap)

    return {
        "conflict_detected": conflict_detected or snapshot_mismatch,
        "guard_fail": guard_fail,
        "snapshot_mismatch": snapshot_mismatch,
        "health_severity": health_severity,
        "acceptance_severity": acc_severity,
        "final_severity": final_severity,
        "health_current_hash": health_hash,
        "acceptance_current_hash": acc_hash,
        "health_snapshot_id": health_snap,
        "acceptance_snapshot_id": acc_snap,
        "health_changed_rows": health_tg.get("changed_rows"),
        "acceptance_changed_rows": acc_tg.get("changed_rows"),
        "recommended_action": health_tg.get("recommended_action") or acc_tg.get("recommended_action"),
    }


def apply_target_guard_conflict_lock(final_doc: dict[str, Any], conflict: dict[str, Any]) -> dict[str, Any]:
    """Force NO BUY / human-only risk-reduce when guard conflict or FAIL."""
    if not conflict.get("conflict_detected") and not conflict.get("guard_fail"):
        out = dict(final_doc)
        out["target_guard_conflict_detected"] = False
        perms = dict(out.get("execution_permissions") or {})
        perms["target_guard_conflict_detected"] = False
        if perms.get("main_block_reason") == "target_guard_conflict_detected":
            perms.pop("main_block_reason", None)
        gates = dict(perms.get("gates") or {})
        if str(conflict.get("health_severity") or "PASS") == "PASS":
            gates["target_portfolio_guard"] = "PASS"
        perms["gates"] = gates
        trim = dict(perms.get("trim_policy") or {})
        if trim.get("target_guard_conflict"):
            trim["target_guard_conflict"] = False
            perms["trim_policy"] = trim
        cap = out.get("policy_cap") or {}
        capped = str(cap.get("capped_execution_scope") or cap.get("max_execution_scope") or "")
        if capped and out.get("execution_scope") == "NO_TRADE" and capped != "NO_TRADE":
            out["execution_scope"] = capped
        if capped and perms.get("execution_scope") == "NO_TRADE" and capped != "NO_TRADE":
            perms["execution_scope"] = capped
        if str(out.get("system_status", "")).upper() == "RED" and capped:
            out["system_status"] = "YELLOW"
        out["execution_permissions"] = perms
        return out

    out = dict(final_doc)
    out["target_guard_conflict_detected"] = True
    buy_actions = frozenset({"Buy", "Buy-allowed", "Add", "Replace", "Rebalance"})

    patched_allowed: list[dict[str, Any]] = []
    for act in out.get("allowed_actions") or []:
        row = dict(act)
        if row.get("action") in buy_actions:
            continue
        if row.get("action") == "Trim":
            row["reason"] = f"{row.get('reason', '')} — target_guard conflict, 사람 승인 시만"
        patched_allowed.append(row)
    out["allowed_actions"] = patched_allowed

    out["final_trade_list"] = [
        dict(t) for t in (out.get("final_trade_list") or [])
        if t.get("action") not in buy_actions
    ]

    perms = dict(out.get("execution_permissions") or {})
    perms["target_guard_conflict_detected"] = True
    perms["gates"] = dict(perms.get("gates") or {})
    perms["gates"]["target_portfolio_guard"] = conflict.get("health_severity") or "FAIL"
    blocked = list(perms.get("blocked_capabilities") or [])
    for cap in ("KR_ALPHA_NEW_BUY", "KR_ALPHA_ADD", "KR_ALPHA_REPLACE", "ETF_REBALANCE"):
        if cap not in blocked:
            blocked.append(cap)
    perms["blocked_capabilities"] = blocked
    allowed = [c for c in (perms.get("allowed_capabilities") or []) if c not in blocked]
    perms["allowed_capabilities"] = allowed
    perms["trim_policy"] = {
        "executable_trim_reasons": ["risk_reduce"],
        "blocked_trim_reasons": ["overweight_reduce", "replace_funding", "rebalance"],
        "target_guard_conflict": True,
    }
    perms["manual_review_required"] = True
    perms["main_block_reason"] = "target_guard_conflict_detected"
    out["execution_permissions"] = perms
    if conflict.get("guard_fail") or conflict.get("conflict_detected"):
        out["execution_scope"] = "NO_TRADE"
        out["system_status"] = "RED"
    return out


def resync_guard_lock_after_bundle_write(
    data_dir: Path,
    output_dir: Path,
    *,
    health_doc: dict[str, Any],
    acceptance_doc: dict[str, Any],
    final_doc: dict[str, Any],
    green: dict[str, Any],
    saa_report: dict[str, Any],
    as_of: str,
    run_id: str,
    target_hash: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Re-detect guard conflict after bundle write; clear transient pre-bundle locks."""
    from src.report.authoritative_status import (
        patch_alpha_v2_execution_context,
        refresh_daily_brief_authoritative,
        sync_acceptance_authoritative_scope_fields,
    )
    from src.validation.ai_export import build_ai_export_bundle, write_ai_export_json
    from src.validation.green_layers import evaluate_green_layers, stamp_green_layers_onto_docs
    from src.validation.saa_restart_readiness import stamp_saa_restart_onto_docs

    final_path = output_dir / "final_execution_decision.json"
    final_doc = read_output_json(final_path) or final_doc
    brief = read_output_json(output_dir / "daily_brief.json")
    bundle = build_ai_export_bundle(
        data_dir,
        output_dir,
        include_health=False,
        daily_brief=brief,
        health_report=health_doc,
    )
    bundle["health_snapshot_id"] = health_doc.get("health_snapshot_id")
    bundle["target_hash"] = target_hash
    stamp_green_layers_onto_docs({"bundle": bundle}, green)
    stamp_saa_restart_onto_docs({"bundle": bundle}, saa_report)
    write_ai_export_json(bundle, output_dir / "ai_export_bundle.json")

    conflict = detect_target_guard_conflict(
        output_dir,
        health_doc=health_doc,
        acceptance_doc=acceptance_doc,
        final_doc=final_doc,
    )
    final_doc = apply_target_guard_conflict_lock(final_doc, conflict)
    green = evaluate_green_layers(
        data_dir,
        output_dir,
        health_doc=health_doc,
        acceptance_doc=acceptance_doc,
        final_doc=final_doc,
    )
    stamp_green_layers_onto_docs({"acceptance": acceptance_doc, "final": final_doc}, green)
    stamp_saa_restart_onto_docs({"acceptance": acceptance_doc, "final": final_doc}, saa_report)
    (output_dir / "acceptance_report.json").write_text(
        json.dumps(acceptance_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    final_path.write_text(json.dumps(final_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sync_acceptance_authoritative_scope_fields(data_dir, output_dir)
    acceptance_doc = read_output_json(output_dir / "acceptance_report.json") or acceptance_doc
    refresh_daily_report_authoritative(output_dir, data_dir)
    refresh_daily_brief_authoritative(data_dir, output_dir, as_of=as_of, run_id=run_id)
    patch_alpha_v2_execution_context(data_dir, output_dir)
    brief = read_output_json(output_dir / "daily_brief.json")
    bundle = build_ai_export_bundle(
        data_dir,
        output_dir,
        include_health=False,
        daily_brief=brief,
        health_report=health_doc,
    )
    bundle["health_snapshot_id"] = health_doc.get("health_snapshot_id")
    bundle["target_hash"] = target_hash
    stamp_green_layers_onto_docs({"bundle": bundle}, green)
    stamp_saa_restart_onto_docs({"bundle": bundle}, saa_report)
    write_ai_export_json(bundle, output_dir / "ai_export_bundle.json")
    return final_doc, acceptance_doc, green, conflict


def apply_post_restore_conservative_lock(
    final_doc: dict[str, Any],
    restore_meta: dict[str, Any],
) -> dict[str, Any]:
    """Same-day restore → guard PASS possible but no auto-buy; YELLOW cap."""
    if not restore_meta.get("restored"):
        return final_doc

    out = dict(final_doc)
    out["target_restore_occurred"] = True
    buy_actions = frozenset({"Buy", "Buy-allowed", "Add", "Replace", "Rebalance"})
    out["allowed_actions"] = [
        dict(a) for a in (out.get("allowed_actions") or [])
        if a.get("action") not in buy_actions
    ]
    out["final_trade_list"] = [
        dict(t) for t in (out.get("final_trade_list") or [])
        if t.get("action") not in buy_actions
    ]
    for act in out["allowed_actions"]:
        if act.get("action") == "Trim":
            act["reason"] = f"{act.get('reason', '')} — same-day restore, 사람 승인 시만"

    perms = dict(out.get("execution_permissions") or {})
    perms["target_restore_occurred"] = True
    perms["manual_review_required"] = True
    perms["main_block_reason"] = "target_restored_same_day"
    for cap in ("KR_ALPHA_NEW_BUY", "KR_ALPHA_ADD", "KR_ALPHA_REPLACE", "ETF_REBALANCE"):
        blocked = list(perms.get("blocked_capabilities") or [])
        if cap not in blocked:
            blocked.append(cap)
        perms["blocked_capabilities"] = blocked
    out["execution_permissions"] = perms
    if str(out.get("system_status", "")).upper() == "GREEN":
        out["system_status"] = "YELLOW"
    return out


def cap_acceptance_after_restore(acceptance: Any, restore_meta: dict[str, Any]) -> Any:
    """Restore occurred same run — do not promote to GREEN."""
    if not restore_meta.get("restored"):
        return acceptance
    if acceptance.overall == "GREEN":
        acceptance.overall = "YELLOW"
    if acceptance.operational_overall == "GREEN":
        acceptance.operational_overall = "YELLOW"
    if acceptance.technical_overall == "GREEN":
        acceptance.technical_overall = "YELLOW"
    return acceptance


def stamp_health_snapshot_meta(
    health_doc: dict[str, Any],
    *,
    run_id: str,
    target_hash: str,
    restore_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tg = _target_guard_from_health_doc(health_doc)
    snap_id = build_health_snapshot_id(
        run_id=run_id,
        target_hash=str(target_hash or tg.get("current_hash") or ""),
        health_overall=str(health_doc.get("overall", "")),
        guard_severity=str(tg.get("severity") or "PASS"),
    )
    meta = dict(health_doc.get("meta") or {})
    meta["health_snapshot_id"] = snap_id
    meta["target_hash"] = target_hash or tg.get("current_hash")
    if restore_meta and restore_meta.get("restored"):
        meta["target_restore_occurred"] = True
    health_doc["meta"] = meta
    health_doc["health_snapshot_id"] = snap_id
    return health_doc


def verify_bundle_snapshot_alignment(output_dir: Path) -> dict[str, Any]:
    """Cross-check target_hash and health_snapshot_id across all bundle artifacts."""
    health = read_output_json(output_dir / "system_health.json") or {}
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    bundle = read_output_json(output_dir / "ai_export_bundle.json") or {}
    final = read_output_json(output_dir / "final_execution_decision.json") or {}

    h_tg = _target_guard_from_health_doc(health)
    a_tg = _target_guard_from_acceptance(acceptance)
    b_tg = _target_guard_from_health_doc(bundle.get("health_report") or {})

    h_hash = str(h_tg.get("current_hash") or health.get("meta", {}).get("target_hash") or "")
    a_hash = str(a_tg.get("current_hash") or acceptance.get("target_hash") or "")
    b_hash = str(b_tg.get("current_hash") or bundle.get("target_hash") or "")
    root_hash = str(bundle.get("target_hash") or "")
    ac01c_hash = ""
    for item in acceptance.get("items") or []:
        if isinstance(item, dict) and item.get("name") == "target_portfolio_guard":
            ac01c_hash = str((item.get("detail") or {}).get("current_hash") or "")
            break

    report_path = output_dir / "daily_report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    d_hash = _extract_daily_report_target_hash(report_text)
    bundle_report = ((bundle.get("reports") or {}).get("daily_report_md")) or ""
    bd_hash = _extract_daily_report_target_hash(bundle_report)

    h_snap = str(health.get("health_snapshot_id") or health.get("meta", {}).get("health_snapshot_id") or "")
    a_snap = str(acceptance.get("health_snapshot_id") or "")
    b_snap = str((bundle.get("health_report") or {}).get("health_snapshot_id") or bundle.get("health_snapshot_id") or "")

    hashes = {
        "system_health": h_hash,
        "health_report": b_hash,
        "acceptance": a_hash,
        "acceptance_ac01c": ac01c_hash,
        "daily_report": d_hash,
        "bundle_daily_report_md": bd_hash,
        "bundle_root": root_hash,
    }
    canonical = h_hash or a_hash or b_hash
    issues: list[str] = []
    for label, val in hashes.items():
        if not val or not canonical:
            continue
        if not _hash_matches(canonical, val):
            issues.append(f"target_hash mismatch: {label}={val[:12]} vs canonical={canonical[:12]}")
    if h_snap and a_snap and h_snap != a_snap:
        issues.append("health_snapshot_id mismatch: system_health vs acceptance")
    if h_snap and b_snap and h_snap != b_snap:
        issues.append("health_snapshot_id mismatch: system_health vs ai_export")

    return {
        "aligned": not issues,
        "issues": issues,
        "target_hash": canonical,
        "hashes": hashes,
        "health_snapshot_id": h_snap,
        "target_guard_conflict": detect_target_guard_conflict(
            output_dir, health_doc=health, acceptance_doc=acceptance, final_doc=final,
        ),
    }


def finalize_health_snapshot(data_dir: Path, output_dir: Path) -> SystemHealthReport:
    """Authoritative end-of-run health — single snapshot write."""
    health = run_system_health(data_dir, output_dir)
    write_health_report(health, output_dir / "system_health.json")
    return health


def reconcile_bundle_artifacts(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    as_of: str,
    target_restore_meta: dict[str, Any] | None = None,
    post_target_write_refresh: bool = False,
    profiler: object | None = None,
) -> dict[str, Any]:
    """Re-run health/acceptance, patch final_decision, sync ai_export health snapshot."""
    from src.decision_logger import append_decision_log
    from src.validation.ai_export import build_ai_export_bundle, write_ai_export_json

    restore_meta = target_restore_meta or {}

    stale_check = detect_snapshot_stale_after_target_write(output_dir)
    if stale_check.get("stale") and not post_target_write_refresh:
        final_path = output_dir / "final_execution_decision.json"
        final_doc = read_output_json(final_path) or {}
        final_doc = apply_snapshot_stale_lock(final_doc, stale_check.get("alignment") or {"issues": ["snapshot stale"]})
        final_path.write_text(json.dumps(final_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_bundle_consistency_validation(output_dir, {
            "pass": False,
            "snapshot_stale": True,
            "issues": (stale_check.get("alignment") or {}).get("issues") or [stale_check.get("reason")],
            "export_aborted": True,
        })
        return {
            "health": {},
            "acceptance": {},
            "conflict": stale_check.get("alignment", {}).get("target_guard_conflict", {}),
            "alignment": stale_check.get("alignment") or {"aligned": False, "issues": ["snapshot stale"]},
            "green_layers": {},
            "restore_meta": restore_meta,
            "final_patched": True,
            "export_aborted": True,
        }

    health = finalize_health_snapshot(data_dir, output_dir)
    acceptance = run_acceptance_check(data_dir, output_dir)
    acceptance = cap_acceptance_after_restore(acceptance, restore_meta)

    health_doc = health.to_dict()
    tg_detail = _target_guard_from_health_doc(health_doc)
    target_hash = str(tg_detail.get("current_hash") or "")
    health_doc = stamp_health_snapshot_meta(
        health_doc, run_id=run_id, target_hash=target_hash, restore_meta=restore_meta,
    )
    write_health_report(
        SystemHealthReport(
            as_of=health.as_of,
            overall=health.overall,
            checks=health.checks,
            summary=health.summary,
            meta=health_doc.get("meta") or {},
        ),
        output_dir / "system_health.json",
    )

    acceptance_doc = acceptance.to_dict()
    acceptance_doc["health_snapshot_id"] = health_doc["health_snapshot_id"]
    acceptance_doc["target_hash"] = target_hash
    if restore_meta.get("restored"):
        acceptance_doc["target_restore_occurred"] = True
    (output_dir / "acceptance_report.json").write_text(
        json.dumps(acceptance_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    final_path = output_dir / "final_execution_decision.json"
    final_doc = read_output_json(final_path) or {}
    from src.alpha.target_write_audit import detect_blocked_target_write_in_run, get_last_target_write_audit

    write_audit = get_last_target_write_audit(output_dir)
    blocked_write = detect_blocked_target_write_in_run(output_dir, run_id)
    conflict = detect_target_guard_conflict(
        output_dir,
        health_doc=health_doc,
        acceptance_doc=acceptance_doc,
        final_doc=final_doc,
    )
    if blocked_write:
        conflict = {
            **conflict,
            "conflict_detected": True,
            "guard_fail": True,
            "health_severity": "FAIL",
        }
    if write_audit:
        final_doc["target_write_audit_status"] = (
            "blocked" if write_audit.get("target_write_allowed") is False else "ok"
        )
        final_doc["last_target_write_source"] = write_audit.get("target_write_source")
        final_doc["last_target_write_allowed"] = write_audit.get("target_write_allowed")
        if write_audit.get("target_hash_after"):
            final_doc["last_target_write_hash"] = write_audit.get("target_hash_after")

    alignment_pre = {
        "aligned": str(acceptance_doc.get("target_hash") or "") == str(target_hash or ""),
        "issues": (
            []
            if str(acceptance_doc.get("target_hash") or "") == str(target_hash or "")
            else ["target_hash mismatch: health vs acceptance during reconcile"]
        ),
    }
    if conflict.get("conflict_detected") or conflict.get("guard_fail"):
        final_doc = apply_target_guard_conflict_lock(final_doc, conflict)
    elif not alignment_pre.get("aligned") or final_doc.get("snapshot_stale"):
        final_doc = apply_snapshot_stale_lock(final_doc, alignment_pre)
    elif restore_meta.get("restored"):
        final_doc = apply_post_restore_conservative_lock(final_doc, restore_meta)
    elif blocked_write:
        final_doc = apply_target_guard_conflict_lock(final_doc, conflict)
    elif final_doc.get("target_guard_conflict_detected"):
        final_doc = apply_target_guard_conflict_lock(final_doc, conflict)

    if alignment_pre.get("aligned"):
        final_doc["snapshot_stale"] = False
        final_doc["snapshot_alignment"] = True
    else:
        final_doc["snapshot_stale"] = True
        final_doc["snapshot_alignment"] = False

    if restore_meta.get("restored"):
        final_doc["target_restore_occurred"] = True

    from src.validation.green_layers import evaluate_green_layers, stamp_green_layers_onto_docs

    green = evaluate_green_layers(
        data_dir,
        output_dir,
        health_doc=health_doc,
        acceptance_doc=acceptance_doc,
        final_doc=final_doc,
    )
    stamp_green_layers_onto_docs({"acceptance": acceptance_doc, "final": final_doc}, green)

    from src.validation.saa_restart_readiness import (
        stamp_saa_restart_onto_docs,
        write_saa_restart_readiness_report,
    )

    saa_report = write_saa_restart_readiness_report(
        data_dir,
        output_dir,
        green=green,
        final_doc=final_doc,
    )
    stamp_saa_restart_onto_docs({"acceptance": acceptance_doc, "final": final_doc}, saa_report)

    (output_dir / "acceptance_report.json").write_text(
        json.dumps(acceptance_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    final_path.write_text(
        json.dumps(final_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    refresh_daily_report_authoritative(output_dir, data_dir)

    from src.report.authoritative_status import refresh_daily_brief_authoritative

    refresh_daily_brief_authoritative(data_dir, output_dir, as_of=as_of, run_id=run_id)

    from src.report.authoritative_status import patch_alpha_v2_execution_context

    patch_alpha_v2_execution_context(data_dir, output_dir)

    if restore_meta.get("restored"):
        append_decision_log(
            output_dir / "decision_log.jsonl",
            {
                "event": "target_restore",
                "run_id": run_id,
                "as_of": as_of,
                "restore_reason": restore_meta.get("restore_reason"),
                "pre_severity": restore_meta.get("pre_severity"),
                "post_severity": restore_meta.get("post_severity"),
                "operational_cap": "YELLOW",
                "actual_buy_allowed": 0,
            },
        )

    brief = read_output_json(output_dir / "daily_brief.json")
    bundle = build_ai_export_bundle(
        data_dir,
        output_dir,
        include_health=False,
        daily_brief=brief,
        health_report=health_doc,
    )
    bundle["health_snapshot_id"] = health_doc.get("health_snapshot_id")
    bundle["target_hash"] = target_hash
    stamp_green_layers_onto_docs({"bundle": bundle}, green)
    stamp_saa_restart_onto_docs({"bundle": bundle}, saa_report)
    write_ai_export_json(bundle, output_dir / "ai_export_bundle.json")

    alignment = verify_bundle_snapshot_alignment(output_dir)
    if not alignment.get("aligned"):
        final_doc = apply_snapshot_stale_lock(read_output_json(final_path) or final_doc, alignment)
        green = evaluate_green_layers(
            data_dir,
            output_dir,
            health_doc=health_doc,
            acceptance_doc=acceptance_doc,
            final_doc=final_doc,
        )
        stamp_green_layers_onto_docs({"acceptance": acceptance_doc, "final": final_doc}, green)
        stamp_saa_restart_onto_docs({"acceptance": acceptance_doc, "final": final_doc}, saa_report)
        (output_dir / "acceptance_report.json").write_text(
            json.dumps(acceptance_doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        final_path.write_text(json.dumps(final_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        refresh_daily_report_authoritative(output_dir, data_dir)
        refresh_daily_brief_authoritative(data_dir, output_dir, as_of=as_of, run_id=run_id)
        brief = read_output_json(output_dir / "daily_brief.json")
        bundle = build_ai_export_bundle(
            data_dir,
            output_dir,
            include_health=False,
            daily_brief=brief,
            health_report=health_doc,
        )
        bundle["health_snapshot_id"] = health_doc.get("health_snapshot_id")
        bundle["target_hash"] = target_hash
        stamp_green_layers_onto_docs({"bundle": bundle}, green)
        stamp_saa_restart_onto_docs({"bundle": bundle}, saa_report)
        write_ai_export_json(bundle, output_dir / "ai_export_bundle.json")
        alignment = verify_bundle_snapshot_alignment(output_dir)
    else:
        clear_snapshot_stale_marker(output_dir)

    acceptance_doc = acceptance.to_dict()
    acceptance_doc["health_snapshot_id"] = health_doc.get("health_snapshot_id")
    acceptance_doc["target_hash"] = target_hash
    if restore_meta.get("restored"):
        acceptance_doc["target_restore_occurred"] = True

    final_doc, acceptance_doc, green, conflict = resync_guard_lock_after_bundle_write(
        data_dir,
        output_dir,
        health_doc=health_doc,
        acceptance_doc=acceptance_doc,
        final_doc=final_doc,
        green=green,
        saa_report=saa_report,
        as_of=as_of,
        run_id=run_id,
        target_hash=target_hash,
    )
    alignment = verify_bundle_snapshot_alignment(output_dir)

    consistency_result = {
        "pass": bool(alignment.get("aligned")),
        "snapshot_stale": not alignment.get("aligned"),
        "issues": alignment.get("issues") or [],
        "hashes": alignment.get("hashes") or {},
        "target_hash": alignment.get("target_hash"),
    }

    from src.report.execution_metrics import validate_report_clarity

    clarity = validate_report_clarity(output_dir)
    if not alignment.get("aligned"):
        clarity["pass"] = False
        fails = list(clarity.get("failures") or [])
        for issue in alignment.get("issues") or []:
            msg = f"bundle_consistency: {issue}"
            if msg not in fails:
                fails.append(msg)
        clarity["failures"] = fails
    (output_dir / "report_clarity_validation.json").write_text(
        json.dumps(clarity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    from src.runtime.diagnostics_cache import (
        refresh_no_action_diagnostics_if_stale,
        verify_diagnostics_outputs,
    )

    refresh_no_action_diagnostics_if_stale(data_dir, output_dir, clarity=clarity)
    diag_verify = verify_diagnostics_outputs(data_dir, output_dir, run_id=run_id)
    consistency_result["diagnostics_verify"] = diag_verify
    if not diag_verify.get("diagnostics_ready"):
        consistency_result["pass"] = False
        for name in diag_verify.get("missing_outputs") or []:
            msg = f"diagnostics_missing:{name}"
            if msg not in consistency_result["issues"]:
                consistency_result["issues"].append(msg)
    elif diag_verify.get("warnings"):
        consistency_result["diagnostics_warnings"] = list(diag_verify.get("warnings") or [])
    write_bundle_consistency_validation(output_dir, consistency_result)

    try:
        from src.data_refresh.tier2_refresh import reconcile_tier2_provenance_staleness

        reconcile_tier2_provenance_staleness(data_dir, as_of=as_of)
    except Exception:
        pass

    append_decision_log(
        output_dir / "decision_log.jsonl",
        {
            "event": "bundle_reconciliation",
            "run_id": run_id,
            "as_of": as_of,
            "execution_scope": acceptance.execution_scope,
            "health_overall": health.overall,
            "acceptance_overall": acceptance.overall,
            "health_snapshot_id": health_doc.get("health_snapshot_id"),
            "target_hash": target_hash,
            "user_target_hash": tg_detail.get("user_target_hash"),
            "target_portfolio_guard_severity": conflict.get("health_severity"),
            "restore_occurred": bool(restore_meta.get("restored")),
            "conflict_detected": conflict.get("conflict_detected"),
            "changed_rows": tg_detail.get("changed_rows"),
            "proposal_leak": tg_detail.get("system_proposal_leak_count"),
            "material": tg_detail.get("unknown_material_count"),
            "snapshot_alignment": alignment.get("aligned"),
            "health_gate": "RED" if health.overall == "fail" else "YELLOW" if health.overall == "warn" else "GREEN",
            "technical_status": green.get("technical_status"),
            "operational_status": green.get("operational_status"),
            "market_status": green.get("market_status"),
            "full_status": green.get("full_status"),
        },
    )

    return {
        "health": health_doc,
        "acceptance": acceptance_doc,
        "conflict": conflict,
        "alignment": alignment,
        "green_layers": green,
        "restore_meta": restore_meta,
        "final_patched": bool(
            conflict.get("conflict_detected")
            or conflict.get("guard_fail")
            or restore_meta.get("restored")
        ),
    }
