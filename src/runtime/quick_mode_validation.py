"""P4d — quick mode contract validation artifact."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

QUICK_VALIDATION_JSON = "quick_mode_validation.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def write_quick_mode_validation(
    output_dir: Path,
    data_dir: Path,
    *,
    run_id: str,
    profiler: Any | None = None,
    total_seconds: float = 0.0,
    actual_buy_allowed: int = 0,
    target_guard_status: str = "unknown",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Write outputs/quick_mode_validation.json after quick run."""
    from src.alpha.target_write_audit import get_last_target_write_audit

    prof = profiler
    audit = get_last_target_write_audit(output_dir)
    target_writes = int(audit.get("target_write_count") or 0) if audit else 0

    research_manifest = _read_json(output_dir / "research_outputs_manifest.json")
    shadow_manifest = _read_json(output_dir / "shadow_history_manifest.json")
    report_manifest = _read_json(output_dir / "report_export_manifest.json")

    research_recomputed = (
        research_manifest.get("run_id") == run_id
        and bool(research_manifest.get("recomputed_outputs"))
    )
    shadow_append = (
        shadow_manifest.get("run_id") == run_id
        and bool(shadow_manifest.get("append_executed"))
    )
    report_recomputed = (
        report_manifest.get("run_id") == run_id
        and bool(report_manifest.get("recomputed_outputs"))
    )

    pykrx = int(getattr(prof, "pykrx_call_count", 0) or 0) if prof else 0
    alpha_full = bool(getattr(prof, "alpha_v2_full_refresh_executed", False)) if prof else False
    shadow_flow = bool(getattr(prof, "shadow_flow_refresh_executed", False)) if prof else False
    kosis = bool(getattr(prof, "kosis_refresh_executed", False)) if prof else False
    network_refresh = bool(getattr(prof, "price_network_fetch_executed", False)) if prof else False
    if not network_refresh and prof:
        network_refresh = bool(getattr(prof, "price_fetch_executed", False))

    contract = _read_json(output_dir / "run_mode_contract_validation.json")
    clarity = _read_json(output_dir / "report_clarity_validation.json")

    blockers: list[str] = []
    if pykrx != 0:
        blockers.append("pykrx_calls_nonzero")
    if alpha_full:
        blockers.append("alpha_v2_full_refresh")
    if shadow_flow:
        blockers.append("shadow_flow_refresh")
    if kosis:
        blockers.append("kosis_refresh")
    if research_recomputed:
        blockers.append("research_outputs_recomputed")
    if shadow_append:
        blockers.append("shadow_history_append")
    if report_recomputed:
        blockers.append("report_exports_recomputed")
    if target_writes != 0:
        blockers.append("target_write_nonzero")
    if actual_buy_allowed != 0:
        blockers.append("actual_buy_allowed_nonzero")

    quick_contract_pass = not blockers

    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "total_seconds": round(total_seconds, 4),
        "quick_contract_pass": quick_contract_pass,
        "pykrx_call_count": pykrx,
        "network_refresh_executed": network_refresh,
        "alpha_v2_full_refresh_executed": alpha_full,
        "shadow_flow_refresh_executed": shadow_flow,
        "kosis_refresh_executed": kosis,
        "research_outputs_recomputed": research_recomputed,
        "shadow_history_append_executed": shadow_append,
        "report_exports_recomputed": report_recomputed,
        "actual_buy_allowed": actual_buy_allowed,
        "target_write_count": target_writes,
        "target_guard_status": target_guard_status,
        "report_clarity_pass": clarity.get("pass") if clarity else None,
        "run_mode_contract_pass": contract.get("contract_pass") if contract else None,
        "blockers": blockers,
        "warnings": list(warnings or []),
        "generated_at": _utc_now(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / QUICK_VALIDATION_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


__all__ = ["QUICK_VALIDATION_JSON", "write_quick_mode_validation"]
