"""Bundle reconcile incremental cache — reuse per-file validation when unchanged."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_JSON = "bundle_reconcile_manifest.json"
BUNDLE_RECONCILE_VERSION = "0.1"

# Outputs whose deep consistency checks can be reused when hash unchanged.
TRACKED_OUTPUT_FILES: tuple[str, ...] = (
    "system_health.json",
    "acceptance_report.json",
    "ai_export_bundle.json",
    "final_execution_decision.json",
    "daily_report.md",
    "daily_brief.json",
    "no_action_diagnostics.json",
    "bundle_consistency_validation.json",
    "alpha_v2_summary.json",
    "flow_dashboard_summary.json",
    "data_gate_diagnostics.json",
    "report_clarity_validation.json",
)

ALWAYS_CHECK_NAMES: tuple[str, ...] = (
    "target_guard",
    "target_hash_alignment",
    "target_write_audit",
    "actual_buy_allowed",
    "authoritative_status",
    "no_action_trace",
    "report_clarity_validation",
)


def _content_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]


def scan_tracked_files(output_dir: Path) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for name in TRACKED_OUTPUT_FILES:
        path = output_dir / name
        rel = f"outputs/{name}"
        if not path.exists():
            files[rel] = {"hash": "missing", "size": 0, "mtime": 0, "exists": False}
            continue
        stat = path.stat()
        files[rel] = {
            "hash": _content_hash(path),
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "exists": True,
        }
    return files


def load_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / MANIFEST_JSON
    if not path.exists():
        return {"bundle_reconcile_version": BUNDLE_RECONCILE_VERSION, "files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"bundle_reconcile_version": BUNDLE_RECONCILE_VERSION, "files": {}}


def run_always_safety_checks(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Lightweight safety checks — never cached."""
    from src.alpha.target_portfolio_guard import user_target_portfolio_path
    from src.alpha.target_write_audit import get_last_target_write_audit
    from src.report.authoritative_status import resolve_authoritative_execution
    from src.report.execution_metrics import count_executable_actions, validate_report_clarity
    from src.report.io_utils import read_output_json
    from src.runtime.diagnostics_cache import verify_no_action_cached
    from src.validation.system_health import run_input_health_checks

    checks: dict[str, Any] = {"pass": True, "failures": []}

    mi_path = data_dir / "market_indicators.csv"
    as_of = None
    if mi_path.exists():
        import pandas as pd

        df = pd.read_csv(mi_path, dtype=str, nrows=1)
        if not df.empty and "date" in df.columns:
            as_of = str(df.iloc[0]["date"])

    health = run_input_health_checks(data_dir, as_of=as_of, output_dir=output_dir)
    guard = next((c for c in health.checks if c.name == "target_portfolio_guard"), None)
    guard_status = str(getattr(guard, "status", "") or "").lower()
    guard_detail = getattr(guard, "detail", None) or {}
    checks["target_guard"] = {
        "status": guard_status,
        "severity": guard_detail.get("severity"),
    }
    if guard_status not in {"pass", "ok"} and guard_detail.get("severity") != "PASS":
        checks["pass"] = False
        checks["failures"].append(f"target_guard={guard_status}")

    curr_hash = str(guard_detail.get("current_hash") or guard_detail.get("target_hash") or "")
    user_hash = str(guard_detail.get("user_target_hash") or "")
    if user_target_portfolio_path(data_dir).exists() and curr_hash and user_hash and curr_hash != user_hash:
        checks["pass"] = False
        checks["failures"].append("target_hash != user_target_hash")

    audit = get_last_target_write_audit(output_dir)
    checks["target_write_audit"] = {
        "allowed": audit.get("target_write_allowed"),
        "source": audit.get("target_write_source"),
    }
    if audit.get("target_write_allowed") is True and str(audit.get("run_id") or "") == run_id:
        checks["pass"] = False
        checks["failures"].append("target_write_allowed in current run")

    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    ab = int(count_executable_actions(final).get("actual_buy_allowed_count") or 0)
    checks["actual_buy_allowed"] = ab

    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final)
    checks["authoritative_status"] = {
        "execution_scope": auth.get("execution_scope"),
        "unified_data_gate": auth.get("unified_data_gate"),
    }

    ok_na, na_reason = verify_no_action_cached(data_dir, output_dir)
    checks["no_action_trace"] = {"ok": ok_na, "reason": na_reason}
    if not ok_na and (output_dir / "no_action_diagnostics.json").exists():
        checks["pass"] = False
        checks["failures"].append(f"no_action_verify:{na_reason}")

    clarity = validate_report_clarity(output_dir)
    checks["report_clarity_validation"] = {"pass": clarity.get("pass")}
    if clarity.get("pass") is False:
        checks["pass"] = False
        checks["failures"].append("report_clarity_validation fail")

    return checks


@dataclass
class ReconcileCacheResult:
    cache_hit: bool = False
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    reused_files: list[str] = field(default_factory=list)
    rechecked_files: list[str] = field(default_factory=list)
    saved_seconds_estimate: float = 0.0
    always_checks: dict[str, Any] = field(default_factory=dict)
    full_reconcile_ran: bool = False


def _partition_files(
    current: dict[str, dict[str, Any]],
    prev_files: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], float]:
    reused: list[str] = []
    rechecked: list[str] = []
    saved = 0.0
    for rel, state in current.items():
        prev = prev_files.get(rel) or {}
        if (
            state.get("exists")
            and prev.get("hash") == state.get("hash")
            and prev.get("reconcile_status") == "pass"
            and state.get("hash") != "missing"
        ):
            reused.append(rel)
            saved += float(prev.get("last_check_seconds") or 30)
        else:
            rechecked.append(rel)
    return reused, rechecked, saved


def write_manifest(
    output_dir: Path,
    *,
    run_id: str,
    file_states: dict[str, dict[str, Any]],
    reused: list[str],
    rechecked: list[str],
    reconcile_pass: bool,
    always_checks: dict[str, Any],
    saved_estimate: float,
    reused_from_run_id: str = "",
) -> None:
    files_doc: dict[str, Any] = {}
    for rel, state in file_states.items():
        hit = rel in reused
        files_doc[rel] = {
            **state,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
            "reconcile_status": "pass" if reconcile_pass and state.get("exists") else "fail",
            "cache_hit": hit,
            "reused_from_run_id": reused_from_run_id if hit else "",
            "last_check_seconds": 0 if hit else float(state.get("last_check_seconds") or 0),
        }
    doc = {
        "run_id": run_id,
        "bundle_reconcile_version": BUNDLE_RECONCILE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": files_doc,
        "cache_hit_count": len(reused),
        "cache_miss_count": len(rechecked),
        "rechecked_files": rechecked,
        "reused_files": reused,
        "always_checked": list(ALWAYS_CHECK_NAMES),
        "always_checks_pass": always_checks.get("pass"),
        "saved_seconds_estimate": round(saved_estimate, 2),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MANIFEST_JSON).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record_profiler(profiler: Any | None, result: ReconcileCacheResult) -> None:
    if profiler is None:
        return
    if hasattr(profiler, "bundle_reconcile_cache_hit_count"):
        profiler.bundle_reconcile_cache_hit_count = result.cache_hit_count
        profiler.bundle_reconcile_cache_miss_count = result.cache_miss_count
        profiler.bundle_reconcile_reused_files = list(result.reused_files)
        profiler.bundle_reconcile_rechecked_files = list(result.rechecked_files)
        profiler.bundle_reconcile_saved_seconds_estimate = result.saved_seconds_estimate
    if result.cache_hit and hasattr(profiler, "add_note"):
        profiler.add_note(
            f"Bundle reconcile cache hit: {result.cache_hit_count} files reused, "
            f"~{result.saved_seconds_estimate:.0f}s saved",
        )


def reconcile_bundle_artifacts_with_cache(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    as_of: str,
    target_restore_meta: dict[str, Any] | None = None,
    profiler: Any | None = None,
) -> dict[str, Any]:
    """Incremental bundle reconcile — fast path when tracked files unchanged."""
    from src.decision_logger import append_decision_log
    from src.validation.bundle_consistency import (
        clear_snapshot_stale_marker,
        detect_snapshot_stale_after_target_write,
        verify_bundle_snapshot_alignment,
        write_bundle_consistency_validation,
    )

    result = ReconcileCacheResult()
    prev = load_manifest(output_dir)
    prev_files = prev.get("files") or {}

    stale_check = detect_snapshot_stale_after_target_write(output_dir)
    if stale_check.get("stale"):
        result.always_checks = run_always_safety_checks(data_dir, output_dir, run_id=run_id)
        result.full_reconcile_ran = True
        out = _full_reconcile(
            data_dir, output_dir, run_id=run_id, as_of=as_of,
            target_restore_meta=target_restore_meta, profiler=profiler, result=result,
        )
        _record_profiler(profiler, result)
        return out

    always = run_always_safety_checks(data_dir, output_dir, run_id=run_id)
    result.always_checks = always
    if not always.get("pass"):
        result.full_reconcile_ran = True
        out = _full_reconcile(
            data_dir, output_dir, run_id=run_id, as_of=as_of,
            target_restore_meta=target_restore_meta, profiler=profiler, result=result,
        )
        _record_profiler(profiler, result)
        return out

    file_states = scan_tracked_files(output_dir)
    reused, rechecked, saved_est = _partition_files(file_states, prev_files)
    result.reused_files = reused
    result.rechecked_files = rechecked
    result.cache_hit_count = len(reused)
    result.cache_miss_count = len(rechecked)
    result.saved_seconds_estimate = saved_est

    if rechecked:
        result.full_reconcile_ran = True
        out = _full_reconcile(
            data_dir, output_dir, run_id=run_id, as_of=as_of,
            target_restore_meta=target_restore_meta, profiler=profiler, result=result,
        )
        _record_profiler(profiler, result)
        return out

    t0 = time.perf_counter()
    alignment = verify_bundle_snapshot_alignment(output_dir)
    consistency_result = {
        "pass": bool(alignment.get("aligned")),
        "snapshot_stale": not alignment.get("aligned"),
        "issues": alignment.get("issues") or [],
        "hashes": alignment.get("hashes") or {},
        "target_hash": alignment.get("target_hash"),
        "cache_hit": True,
    }
    write_bundle_consistency_validation(output_dir, consistency_result)
    if alignment.get("aligned"):
        clear_snapshot_stale_marker(output_dir)

    elapsed = time.perf_counter() - t0
    write_manifest(
        output_dir,
        run_id=run_id,
        file_states=file_states,
        reused=reused,
        rechecked=rechecked,
        reconcile_pass=consistency_result["pass"],
        always_checks=always,
        saved_estimate=saved_est,
        reused_from_run_id=str(prev.get("run_id") or ""),
    )

    append_decision_log(
        output_dir / "decision_log.jsonl",
        {
            "event": "bundle_reconciliation",
            "run_id": run_id,
            "as_of": as_of,
            "cache_hit": True,
            "reused_files_count": len(reused),
            "snapshot_alignment": alignment.get("aligned"),
            "always_checks_pass": always.get("pass"),
        },
    )

    result.cache_hit = True
    _record_profiler(profiler, result)
    return {
        "health": {},
        "acceptance": {},
        "alignment": alignment,
        "consistency": consistency_result,
        "cache_hit": True,
        "reused_files": reused,
        "rechecked_files": rechecked,
        "always_checks": always,
        "incremental_seconds": round(elapsed, 4),
    }


def _full_reconcile(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    as_of: str,
    target_restore_meta: dict[str, Any] | None,
    profiler: Any | None,
    result: ReconcileCacheResult,
) -> dict[str, Any]:
    from src.validation.bundle_consistency import reconcile_bundle_artifacts

    t0 = time.perf_counter()
    if not result.always_checks:
        result.always_checks = run_always_safety_checks(data_dir, output_dir, run_id=run_id)
    out = reconcile_bundle_artifacts(
        data_dir,
        output_dir,
        run_id=run_id,
        as_of=as_of,
        target_restore_meta=target_restore_meta,
        profiler=profiler,
    )
    elapsed = time.perf_counter() - t0

    file_states = scan_tracked_files(output_dir)
    alignment = out.get("alignment") or {}
    rechecked = [rel for rel in file_states if rel not in result.reused_files]
    for rel in rechecked:
        file_states[rel]["last_check_seconds"] = round(elapsed / max(len(rechecked), 1), 2)

    write_manifest(
        output_dir,
        run_id=run_id,
        file_states=file_states,
        reused=result.reused_files,
        rechecked=rechecked,
        reconcile_pass=bool(alignment.get("aligned")),
        always_checks=result.always_checks,
        saved_estimate=0.0,
    )

    out["full_reconcile_ran"] = True
    out["reconcile_seconds"] = round(elapsed, 2)
    return out
