"""P3d — report / export hash skip (cache-first reuse)."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.runtime.diagnostics_subset_hash import (
    compute_semantic_file_hash,
    normalize_for_semantic_hash,
)
from src.runtime.final_decision_core import compute_final_decision_core_hash, validate_final_decision_safety

MANIFEST_JSON = "report_export_manifest.json"

REQUIRED_REPORT_OUTPUTS: tuple[str, ...] = (
    "daily_report.md",
    "daily_brief.json",
    "ai_export_bundle.json",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def compute_report_export_dependency_hashes(data_dir: Path, output_dir: Path) -> dict[str, str]:
    """Stable dependency tokens for report/export reuse."""
    from src.alpha.target_portfolio_guard import user_target_portfolio_path
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    sys_health = read_output_json(output_dir / "system_health.json") or {}
    gate_diag = read_output_json(output_dir / "alpha_gate_diagnostics.json") or {}
    actual_buy = int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0)

    research_manifest = _read_json(output_dir / "research_outputs_manifest.json")
    shadow_manifest = _read_json(output_dir / "shadow_history_manifest.json")
    user_target = user_target_portfolio_path(data_dir)

    return {
        "final_decision_core_hash": compute_final_decision_core_hash(output_dir),
        "system_health_hash": compute_semantic_file_hash(output_dir / "system_health.json"),
        "alpha_v2_summary_hash": compute_semantic_file_hash(output_dir / "alpha_v2_summary.json"),
        "flow_dashboard_summary_hash": compute_semantic_file_hash(output_dir / "flow_dashboard_summary.json"),
        "research_outputs_dependency_hash": str(research_manifest.get("dependency_hash") or ""),
        "shadow_history_snapshot_key": str(
            shadow_manifest.get("semantic_snapshot_key")
            or shadow_manifest.get("latest_semantic_snapshot_key")
            or "",
        ),
        "target_hash": compute_semantic_file_hash(data_dir / "target_portfolio.csv"),
        "user_target_hash": compute_semantic_file_hash(user_target),
        "execution_scope": str(final_doc.get("execution_scope") or ""),
        "actual_buy_allowed": str(actual_buy),
        "data_gate": str(final_doc.get("data_gate") or sys_health.get("unified_data_gate") or ""),
        "alpha_gate_status": str(gate_diag.get("alpha_gate_status") or gate_diag.get("status") or ""),
        "portfolio_gate_status": str(sys_health.get("portfolio_gate") or ""),
        "policy_cap_hash": compute_semantic_file_hash(output_dir / "policy_cap_counterfactual.json"),
    }


def compute_dependency_hash(hashes: dict[str, str]) -> str:
    payload = normalize_for_semantic_hash({k: hashes[k] for k in sorted(hashes)})
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def _changed_dependency_files(
    current: dict[str, str],
    previous: dict[str, str] | None,
) -> list[str]:
    if not previous:
        return list(current.keys())
    changed: list[str] = []
    for key, val in current.items():
        prev_val = previous.get(key)
        if prev_val is None or prev_val != val:
            changed.append(key)
    return changed


def _required_outputs_present(output_dir: Path) -> tuple[bool, list[str]]:
    missing = [rel for rel in REQUIRED_REPORT_OUTPUTS if not (output_dir / rel).exists()]
    return not missing, missing


def load_report_export_manifest(output_dir: Path) -> dict[str, Any]:
    return _read_json(output_dir / MANIFEST_JSON)


def write_report_export_manifest(output_dir: Path, doc: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MANIFEST_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def evaluate_report_export_cache(
    data_dir: Path,
    output_dir: Path,
    *,
    run_mode: str = "standard",
    force_refresh: bool = False,
) -> dict[str, Any]:
    hashes = compute_report_export_dependency_hashes(data_dir, output_dir)
    dependency_hash = compute_dependency_hash(hashes)
    prev = load_report_export_manifest(output_dir)
    prev_hash = str(prev.get("dependency_hash") or "")
    prev_file_hashes = prev.get("dependency_file_hashes") or {}
    outputs_ok, missing = _required_outputs_present(output_dir)
    hash_match = bool(prev_hash and prev_hash == dependency_hash)
    changed_files = _changed_dependency_files(
        hashes,
        prev_file_hashes if prev_file_hashes else None,
    )
    blockers: list[str] = []
    mode = str(run_mode).lower()

    if mode == "bundle_only":
        cache_hit = outputs_ok
        skip_reason = "bundle_only_verify" if cache_hit else "bundle_only_missing_outputs"
        if not outputs_ok:
            blockers.append("outputs_missing")
    elif mode == "quick":
        cache_hit = outputs_ok
        skip_reason = "quick_reuse" if cache_hit else "quick_missing_outputs"
        if not outputs_ok:
            blockers.append("outputs_missing")
    elif mode == "deep" and (force_refresh or not hash_match):
        cache_hit = False
        skip_reason = "deep_recompute"
        if not hash_match:
            blockers.append("dependency_hash_changed")
    elif mode == "deep" and hash_match and outputs_ok:
        cache_hit = True
        skip_reason = "deep_cache_reuse"
    elif not outputs_ok:
        cache_hit = False
        skip_reason = "required_outputs_missing"
        blockers.append("outputs_missing")
    elif not hash_match:
        cache_hit = False
        skip_reason = "dependency_hash_changed"
        blockers.append("dependency_hash_changed")
    else:
        cache_hit = True
        skip_reason = "dependency_unchanged"

    return {
        "cache_hit": cache_hit,
        "skip_reason": skip_reason,
        "dependency_hash": dependency_hash,
        "previous_dependency_hash": prev_hash,
        "dependency_hash_changed": bool(prev_hash and prev_hash != dependency_hash),
        "dependency_file_hashes": hashes,
        "changed_dependency_files": changed_files if not hash_match else [],
        "required_outputs_present": outputs_ok,
        "missing_outputs": missing,
        "blockers": blockers,
        "run_mode": mode,
        "previous_elapsed_seconds": float(prev.get("elapsed_seconds") or 0.0),
    }


def _build_safety_check(output_dir: Path, data_dir: Path) -> dict[str, Any]:
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    actual_buy = int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0)
    clarity_doc = read_output_json(output_dir / "report_clarity_validation.json") or {}
    safety: dict[str, Any] = {
        "actual_buy_allowed": actual_buy,
        "target_write_count": 0,
        "target_guard_status": "unknown",
        "execution_scope": str(final_doc.get("execution_scope") or ""),
        "report_clarity_pass": bool(clarity_doc.get("pass")) if clarity_doc else None,
        "final_decision_present": bool(final_doc),
    }
    try:
        safety.update(validate_final_decision_safety(output_dir, data_dir))
    except Exception:
        pass
    return safety


@dataclass
class ReportExportWriteContext:
    data_dir: Path
    output_dir: Path
    run_id: str
    as_of: str
    acceptance: Any
    data_gate: Any
    market: Any
    gap_rows: list[Any]
    alerts: list[Any]
    actions: list[Any]
    execution_level: int
    policy_gate: Any = None
    health_gate: Any = None
    theoretical_actions: list[Any] | None = None
    review_actions: list[Any] | None = None
    health_overall: str | None = None
    execution_scope: str | None = None
    alpha_trade_permission: str | None = None
    alpha_position_action: str | None = None
    hard_stops_detail: dict[str, Any] | None = None
    exposure_lookthrough: dict[str, Any] | None = None
    shadow_history_summary: dict[str, Any] | None = None


def _load_daily_brief(output_dir: Path) -> dict[str, Any]:
    from src.report.io_utils import read_output_json

    return read_output_json(output_dir / "daily_brief.json") or {}


def _run_report_exports(ctx: ReportExportWriteContext) -> tuple[dict[str, Any], list[str]]:
    from src.report.authoritative_status import patch_alpha_v2_execution_context
    from src.report.export_daily_brief import write_daily_brief
    from src.report.publish import patch_acceptance_and_sync_exports, publish_report_exports
    from src.report_writer import write_daily_report

    recomputed: list[str] = []
    daily_brief, _bundle = publish_report_exports(
        ctx.output_dir,
        ctx.data_dir,
        as_of=ctx.as_of,
        run_id=ctx.run_id,
        include_health=False,
    )
    recomputed.extend(["publish_report_exports", "daily_brief.json", "ai_export_bundle.json"])

    daily_brief = patch_acceptance_and_sync_exports(
        ctx.output_dir,
        ctx.acceptance,
        as_of=ctx.as_of,
        run_id=ctx.run_id,
        data_dir=ctx.data_dir,
    )
    recomputed.append("acceptance_sync_exports")

    if ctx.shadow_history_summary is not None:
        daily_brief["shadow_history"] = ctx.shadow_history_summary
        write_daily_brief(ctx.output_dir / "daily_brief.json", daily_brief)
        recomputed.append("shadow_history_brief_patch")

    patch_alpha_v2_execution_context(ctx.data_dir, ctx.output_dir)
    recomputed.append("patch_alpha_v2_execution_context")

    write_daily_report(
        ctx.output_dir / "daily_report.md",
        data_gate=ctx.data_gate,
        market=ctx.market,
        gap_rows=ctx.gap_rows,
        alerts=ctx.alerts,
        actions=ctx.actions,
        execution_level=ctx.execution_level,
        policy_gate=ctx.policy_gate,
        health_gate=ctx.health_gate,
        theoretical_actions=ctx.theoretical_actions,
        review_actions=ctx.review_actions,
        health_overall=ctx.health_overall,
        execution_scope=ctx.execution_scope,
        alpha_trade_permission=ctx.alpha_trade_permission,
        alpha_position_action=ctx.alpha_position_action,
        data_dir=ctx.data_dir,
        output_dir=ctx.output_dir,
        hard_stops_detail=ctx.hard_stops_detail,
        exposure_lookthrough=ctx.exposure_lookthrough,
        daily_brief=daily_brief,
    )
    recomputed.append("daily_report.md")
    return daily_brief, recomputed


@dataclass
class ReportExportResult:
    cache_hit: bool = False
    reused: bool = False
    recomputed: list[str] = field(default_factory=list)
    skip_reason: str = ""
    elapsed_seconds: float = 0.0
    dependency_hash: str = ""
    dependency_hash_changed: bool = False
    safety: dict[str, Any] = field(default_factory=dict)
    daily_brief: dict[str, Any] = field(default_factory=dict)
    reused_outputs: list[str] = field(default_factory=list)
    missing_outputs: list[str] = field(default_factory=list)


def maybe_run_report_exports(
    ctx: ReportExportWriteContext,
    *,
    run_mode: str = "standard",
    force_refresh: bool = False,
    profiler: Any | None = None,
) -> ReportExportResult:
    """Cache-first wrapper for report_exports step."""
    t0 = time.perf_counter()
    decision = evaluate_report_export_cache(
        ctx.data_dir,
        ctx.output_dir,
        run_mode=run_mode,
        force_refresh=force_refresh,
    )
    safety = _build_safety_check(ctx.output_dir, ctx.data_dir)
    mode = str(run_mode).lower()

    if mode == "bundle_only":
        elapsed = time.perf_counter() - t0
        manifest = _build_manifest(
            ctx,
            decision=decision,
            safety=safety,
            elapsed=elapsed,
            cache_hit=decision["cache_hit"],
            reused_outputs=list(REQUIRED_REPORT_OUTPUTS) if decision["cache_hit"] else [],
            recomputed_outputs=[],
        )
        write_report_export_manifest(ctx.output_dir, manifest)
        result = ReportExportResult(
            cache_hit=decision["cache_hit"],
            reused=decision["cache_hit"],
            skip_reason=decision["skip_reason"],
            elapsed_seconds=elapsed,
            dependency_hash=decision["dependency_hash"],
            dependency_hash_changed=decision["dependency_hash_changed"],
            safety=safety,
            daily_brief=_load_daily_brief(ctx.output_dir),
            reused_outputs=list(REQUIRED_REPORT_OUTPUTS) if decision["cache_hit"] else [],
            missing_outputs=list(decision["missing_outputs"]),
        )
        _apply_profiler(profiler, result, decision)
        return result

    if decision["cache_hit"]:
        elapsed = time.perf_counter() - t0
        prev_elapsed = float(decision.get("previous_elapsed_seconds") or 0.0)
        saved = max(prev_elapsed, 1.0) if prev_elapsed > 0 else 1.0
        manifest = _build_manifest(
            ctx,
            decision=decision,
            safety=safety,
            elapsed=elapsed,
            cache_hit=True,
            reused_outputs=list(REQUIRED_REPORT_OUTPUTS),
            recomputed_outputs=[],
            saved_seconds=saved,
        )
        write_report_export_manifest(ctx.output_dir, manifest)
        result = ReportExportResult(
            cache_hit=True,
            reused=True,
            recomputed=[],
            skip_reason=str(decision["skip_reason"]),
            elapsed_seconds=elapsed,
            dependency_hash=decision["dependency_hash"],
            dependency_hash_changed=False,
            safety=safety,
            daily_brief=_load_daily_brief(ctx.output_dir),
            reused_outputs=list(REQUIRED_REPORT_OUTPUTS),
        )
        _apply_profiler(profiler, result, decision, saved_seconds=saved)
        return result

    daily_brief, recomputed = _run_report_exports(ctx)
    elapsed = time.perf_counter() - t0
    safety = _build_safety_check(ctx.output_dir, ctx.data_dir)
    outputs_ok, missing = _required_outputs_present(ctx.output_dir)
    manifest = _build_manifest(
        ctx,
        decision=decision,
        safety=safety,
        elapsed=elapsed,
        cache_hit=False,
        reused_outputs=[],
        recomputed_outputs=recomputed,
    )
    write_report_export_manifest(ctx.output_dir, manifest)
    result = ReportExportResult(
        cache_hit=False,
        reused=False,
        recomputed=recomputed,
        skip_reason="recomputed" if outputs_ok else str(decision["skip_reason"]),
        elapsed_seconds=elapsed,
        dependency_hash=decision["dependency_hash"],
        dependency_hash_changed=decision["dependency_hash_changed"],
        safety=safety,
        daily_brief=daily_brief,
        missing_outputs=missing,
    )
    _apply_profiler(profiler, result, decision)
    return result


def _build_manifest(
    ctx: ReportExportWriteContext,
    *,
    decision: dict[str, Any],
    safety: dict[str, Any],
    elapsed: float,
    cache_hit: bool,
    reused_outputs: list[str],
    recomputed_outputs: list[str],
    saved_seconds: float = 0.0,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": ctx.run_id,
        "run_mode": decision.get("run_mode") or "standard",
        "generated_at": _utc_now(),
        "cache_hit": cache_hit,
        "skip_reason": decision["skip_reason"] if cache_hit else (
            "recomputed" if recomputed_outputs else decision["skip_reason"]
        ),
        "dependency_hash": decision["dependency_hash"],
        "previous_dependency_hash": decision["previous_dependency_hash"],
        "dependency_file_hashes": decision.get("dependency_file_hashes") or {},
        "changed_dependency_files": decision["changed_dependency_files"] if not cache_hit else [],
        "required_outputs_present": decision["required_outputs_present"],
        "missing_outputs": decision["missing_outputs"],
        "reused_outputs": reused_outputs,
        "recomputed_outputs": recomputed_outputs,
        "elapsed_seconds": round(elapsed, 4),
        "safety_check": safety,
    }
    if saved_seconds > 0:
        doc["saved_seconds_estimate"] = round(saved_seconds, 2)
    return doc


def _apply_profiler(
    profiler: Any | None,
    result: ReportExportResult,
    decision: dict[str, Any],
    *,
    saved_seconds: float = 0.0,
) -> None:
    if profiler is None:
        return
    mapping = {
        "report_export_cache_hit": result.cache_hit,
        "report_export_reused": result.reused,
        "report_export_recomputed": list(result.recomputed),
        "report_export_dependency_hash_changed": bool(decision.get("dependency_hash_changed")),
    }
    for key, val in mapping.items():
        if hasattr(profiler, key):
            setattr(profiler, key, val)
    if result.cache_hit and hasattr(profiler, "report_export_saved_seconds_estimate"):
        prev = float(getattr(profiler, "report_export_saved_seconds_estimate", 0.0) or 0.0)
        profiler.report_export_saved_seconds_estimate = round(prev + saved_seconds, 2)


__all__ = [
    "MANIFEST_JSON",
    "REQUIRED_REPORT_OUTPUTS",
    "ReportExportResult",
    "ReportExportWriteContext",
    "compute_dependency_hash",
    "compute_report_export_dependency_hashes",
    "evaluate_report_export_cache",
    "load_report_export_manifest",
    "maybe_run_report_exports",
    "write_report_export_manifest",
]
