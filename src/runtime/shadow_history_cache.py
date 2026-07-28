"""P3c — shadow history semantic snapshot cache / delta append."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash, normalize_for_semantic_hash
from src.runtime.final_decision_core import validate_final_decision_safety
from src.shadow.history_ledger import (
    HISTORY_SUBDIR,
    append_shadow_history_ledger,
    evaluate_candidate_outcomes,
)

MANIFEST_JSON = "shadow_history_manifest.json"

REQUIRED_HISTORY_OUTPUTS: tuple[str, ...] = (
    f"{HISTORY_SUBDIR}/alpha_v2_shadow_history.csv",
    f"{HISTORY_SUBDIR}/flow_dashboard_history.csv",
    f"{HISTORY_SUBDIR}/alpha_v2_candidate_outcomes.csv",
    f"{HISTORY_SUBDIR}/flow_signal_outcomes.csv",
    f"{HISTORY_SUBDIR}/shadow_daily_summary.csv",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _flow_stale_count(output_dir: Path) -> int:
    dash = _read_json(output_dir / "flow_dashboard_summary.json")
    stale = dash.get("stale_count")
    if stale is not None:
        try:
            return int(stale)
        except (TypeError, ValueError):
            pass
    rows = dash.get("rows") or []
    if isinstance(rows, list):
        return sum(1 for r in rows if str((r or {}).get("fresh_or_stale")) == "stale")
    return 0


def compute_semantic_snapshot_payload(
    data_dir: Path,
    output_dir: Path,
    *,
    market_date: str,
) -> dict[str, Any]:
    from src.alpha.target_portfolio_guard import user_target_portfolio_path
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json

    v2_summary = read_output_json(output_dir / "alpha_v2_summary.json") or {}
    flow_summary = read_output_json(output_dir / "flow_dashboard_summary.json") or {}
    shortlist = read_output_json(output_dir / "alpha_shortlist_summary.json") or {}
    gate_diag = read_output_json(output_dir / "alpha_gate_diagnostics.json") or {}
    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}

    actual_buy = int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0)
    coverage = v2_summary.get("coverage") or {}
    fresh_ratio = flow_summary.get("fresh_ratio") or coverage.get("fresh_flow_ratio")

    return {
        "market_date": market_date[:10],
        "alpha_v2_summary_hash": compute_semantic_file_hash(output_dir / "alpha_v2_summary.json"),
        "flow_dashboard_summary_hash": compute_semantic_file_hash(output_dir / "flow_dashboard_summary.json"),
        "target_hash": compute_semantic_file_hash(data_dir / "target_portfolio.csv"),
        "user_target_hash": compute_semantic_file_hash(user_target_portfolio_path(data_dir)),
        "policy_hash": compute_semantic_file_hash(data_dir / "portfolio_policy.yaml"),
        "execution_scope": str(final_doc.get("execution_scope") or v2_summary.get("execution_context", {}).get("execution_scope") or ""),
        "actual_buy_allowed": actual_buy,
        "alpha_gate_status": str(gate_diag.get("alpha_gate_status") or gate_diag.get("status") or ""),
        "data_gate_status": str(final_doc.get("data_gate") or ""),
        "flow_fresh_ratio": fresh_ratio,
        "flow_stale_count": _flow_stale_count(output_dir),
        "shortlist_eligible_count": int(shortlist.get("shortlist_eligible") or shortlist.get("shortlist_eligible_count") or 0),
        "candidate_count": int(coverage.get("candidate_count") or v2_summary.get("candidate_count") or 0),
    }


def compute_semantic_snapshot_key(payload: dict[str, Any]) -> str:
    normalized = normalize_for_semantic_hash(payload)
    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()[:16]


def _required_outputs_present(output_dir: Path) -> tuple[bool, list[str]]:
    missing = [rel for rel in REQUIRED_HISTORY_OUTPUTS if not (output_dir / rel).exists()]
    return not missing, missing


def load_shadow_history_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / MANIFEST_JSON
    return _read_json(path)


def write_shadow_history_manifest(output_dir: Path, doc: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MANIFEST_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _build_safety_check(output_dir: Path, data_dir: Path) -> dict[str, Any]:
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    safety: dict[str, Any] = {
        "actual_buy_allowed": int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0),
        "target_write_count": 0,
        "target_guard_status": "unknown",
        "execution_scope": str(final_doc.get("execution_scope") or ""),
    }
    try:
        safety.update(validate_final_decision_safety(output_dir, data_dir))
    except Exception:
        pass
    return safety


def _last_ledger_summary(output_dir: Path) -> dict[str, Any]:
    last = _read_json(output_dir / HISTORY_SUBDIR / "shadow_history_last.json")
    if last.get("last_summary"):
        return dict(last["last_summary"])
    prev = load_shadow_history_manifest(output_dir)
    if prev.get("last_ledger_summary"):
        return dict(prev["last_ledger_summary"])
    return {
        "alpha_v2_shadow_history_updated": False,
        "flow_dashboard_history_updated": False,
        "target_write_occurred": False,
        "skipped_semantic_snapshot_duplicate": True,
    }


def evaluate_shadow_history_cache(
    data_dir: Path,
    output_dir: Path,
    *,
    market_date: str,
    run_mode: str = "standard",
    force_full_rebuild: bool = False,
) -> dict[str, Any]:
    payload = compute_semantic_snapshot_payload(data_dir, output_dir, market_date=market_date)
    semantic_key = compute_semantic_snapshot_key(payload)
    prev = load_shadow_history_manifest(output_dir)
    prev_key = str(prev.get("semantic_snapshot_key") or prev.get("latest_semantic_snapshot_key") or "")
    key_match = bool(prev_key and prev_key == semantic_key)
    outputs_ok, missing = _required_outputs_present(output_dir)
    mode = str(run_mode).lower()
    blockers: list[str] = []

    if mode == "quick":
        cache_hit = outputs_ok
        skip_reason = "quick_verify_only" if cache_hit else "quick_outputs_missing"
        append_allowed = False
    elif mode == "bundle_only":
        cache_hit = outputs_ok
        skip_reason = "bundle_only_verify" if cache_hit else "bundle_only_missing_outputs"
        append_allowed = False
    elif not outputs_ok and not force_full_rebuild:
        cache_hit = False
        skip_reason = "required_outputs_missing"
        append_allowed = True
        blockers.append("outputs_missing")
    elif key_match and not force_full_rebuild:
        cache_hit = True
        skip_reason = "semantic_snapshot_unchanged"
        append_allowed = False
    elif mode == "deep" and force_full_rebuild:
        cache_hit = False
        skip_reason = "deep_full_rebuild"
        append_allowed = not key_match
        if key_match:
            blockers.append("semantic_duplicate_append_prevented")
    else:
        cache_hit = False
        skip_reason = "semantic_snapshot_changed"
        append_allowed = True

    return {
        "cache_hit": cache_hit,
        "skip_reason": skip_reason,
        "semantic_snapshot_key": semantic_key,
        "previous_semantic_snapshot_key": prev_key,
        "snapshot_key_match": key_match,
        "append_allowed": append_allowed,
        "semantic_payload": payload,
        "required_outputs_present": outputs_ok,
        "missing_outputs": missing,
        "blockers": blockers,
        "run_mode": mode,
        "previous_elapsed_seconds": float(prev.get("elapsed_seconds") or 0.0),
    }


@dataclass
class ShadowHistoryResult:
    cache_hit: bool = False
    skip_reason: str = ""
    append_executed: bool = False
    appended_rows: int = 0
    outcome_recomputed: bool = False
    outcome_recomputed_rows: int = 0
    summary_rebuilt: bool = False
    semantic_snapshot_key: str = ""
    snapshot_key_match: bool = False
    elapsed_seconds: float = 0.0
    ledger_summary: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)
    reused_outputs: list[str] = field(default_factory=list)
    recomputed_outputs: list[str] = field(default_factory=list)


def maybe_append_shadow_history(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    run_date: str,
    run_mode: str = "standard",
    force_full_rebuild: bool = False,
    profiler: Any | None = None,
) -> ShadowHistoryResult:
    """Semantic-snapshot cache-first shadow history append."""
    t0 = time.perf_counter()
    decision = evaluate_shadow_history_cache(
        data_dir,
        output_dir,
        market_date=run_date,
        run_mode=run_mode,
        force_full_rebuild=force_full_rebuild,
    )
    safety = _build_safety_check(output_dir, data_dir)
    mode = str(run_mode).lower()

    if decision["cache_hit"]:
        elapsed = time.perf_counter() - t0
        prev_elapsed = float(decision.get("previous_elapsed_seconds") or 0.0)
        saved = max(prev_elapsed, 30.0) if prev_elapsed > 0 else 35.0
        ledger_summary = _last_ledger_summary(output_dir)
        ledger_summary["skipped_semantic_snapshot_duplicate"] = True
        ledger_summary["semantic_snapshot_key"] = decision["semantic_snapshot_key"]
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "run_mode": run_mode,
            "generated_at": _utc_now(),
            "cache_hit": True,
            "skip_reason": decision["skip_reason"],
            "semantic_snapshot_key": decision["semantic_snapshot_key"],
            "previous_semantic_snapshot_key": decision["previous_semantic_snapshot_key"],
            "latest_semantic_snapshot_key": decision["semantic_snapshot_key"],
            "snapshot_key_match": True,
            "append_executed": False,
            "appended_rows": 0,
            "outcome_recomputed": False,
            "outcome_recomputed_rows": 0,
            "summary_rebuilt": False,
            "reused_outputs": list(REQUIRED_HISTORY_OUTPUTS),
            "recomputed_outputs": [],
            "elapsed_seconds": round(elapsed, 4),
            "saved_seconds_estimate": round(saved, 2),
            "safety_check": safety,
            "last_ledger_summary": ledger_summary,
        }
        write_shadow_history_manifest(output_dir, manifest)
        result = ShadowHistoryResult(
            cache_hit=True,
            skip_reason=str(decision["skip_reason"]),
            semantic_snapshot_key=decision["semantic_snapshot_key"],
            snapshot_key_match=True,
            elapsed_seconds=elapsed,
            ledger_summary=ledger_summary,
            safety=safety,
            reused_outputs=list(REQUIRED_HISTORY_OUTPUTS),
        )
        _apply_profiler(profiler, result, saved_seconds=saved)
        return result

    if mode in {"quick", "bundle_only"}:
        elapsed = time.perf_counter() - t0
        ledger_summary = _last_ledger_summary(output_dir)
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "run_mode": run_mode,
            "generated_at": _utc_now(),
            "cache_hit": decision["required_outputs_present"],
            "skip_reason": decision["skip_reason"],
            "semantic_snapshot_key": decision["semantic_snapshot_key"],
            "previous_semantic_snapshot_key": decision["previous_semantic_snapshot_key"],
            "latest_semantic_snapshot_key": decision["semantic_snapshot_key"],
            "snapshot_key_match": decision["snapshot_key_match"],
            "append_executed": False,
            "appended_rows": 0,
            "outcome_recomputed": False,
            "outcome_recomputed_rows": 0,
            "summary_rebuilt": False,
            "reused_outputs": list(REQUIRED_HISTORY_OUTPUTS) if decision["required_outputs_present"] else [],
            "recomputed_outputs": [],
            "elapsed_seconds": round(elapsed, 4),
            "safety_check": safety,
            "last_ledger_summary": ledger_summary,
        }
        write_shadow_history_manifest(output_dir, manifest)
        result = ShadowHistoryResult(
            cache_hit=decision["required_outputs_present"],
            skip_reason=str(decision["skip_reason"]),
            semantic_snapshot_key=decision["semantic_snapshot_key"],
            snapshot_key_match=decision["snapshot_key_match"],
            elapsed_seconds=elapsed,
            ledger_summary=ledger_summary,
            safety=safety,
        )
        _apply_profiler(profiler, result)
        return result

    incremental = mode == "standard" and not force_full_rebuild
    ledger_summary = append_shadow_history_ledger(
        data_dir,
        output_dir,
        run_id=run_id,
        run_date=run_date,
        evaluate_outcomes=not incremental,
        run_id_filter=run_id if incremental else None,
    )

    outcome_rows = 0
    outcome_recomputed = False
    if incremental:
        v2_out, flow_out = evaluate_candidate_outcomes(
            data_dir, output_dir, as_of=run_date, run_id_filter=run_id,
        )
        outcome_rows = len(v2_out) + len(flow_out)
        outcome_recomputed = outcome_rows > 0
    elif mode == "deep" and force_full_rebuild:
        v2_out, flow_out = evaluate_candidate_outcomes(data_dir, output_dir, as_of=run_date)
        outcome_rows = len(v2_out) + len(flow_out)
        outcome_recomputed = True

    appended_rows = int(ledger_summary.get("alpha_v2_rows_appended") or 0) + int(
        ledger_summary.get("flow_rows_appended") or 0,
    )
    append_executed = bool(
        ledger_summary.get("alpha_v2_shadow_history_updated")
        or ledger_summary.get("flow_dashboard_history_updated"),
    )
    if ledger_summary.get("skipped_duplicate_run_id"):
        append_executed = False

    elapsed = time.perf_counter() - t0
    safety = _build_safety_check(output_dir, data_dir)
    recomputed = []
    if append_executed:
        recomputed.append("shadow_history_append")
    if outcome_recomputed:
        recomputed.append("outcome_eval")

    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_mode": run_mode,
        "generated_at": _utc_now(),
        "cache_hit": False,
        "skip_reason": decision["skip_reason"],
        "semantic_snapshot_key": decision["semantic_snapshot_key"],
        "previous_semantic_snapshot_key": decision["previous_semantic_snapshot_key"],
        "latest_semantic_snapshot_key": decision["semantic_snapshot_key"],
        "snapshot_key_match": False,
        "append_executed": append_executed,
        "appended_rows": appended_rows,
        "outcome_recomputed": outcome_recomputed,
        "outcome_recomputed_rows": outcome_rows,
        "summary_rebuilt": append_executed,
        "reused_outputs": [],
        "recomputed_outputs": recomputed,
        "elapsed_seconds": round(elapsed, 4),
        "safety_check": safety,
        "last_ledger_summary": ledger_summary,
    }
    write_shadow_history_manifest(output_dir, manifest)

    result = ShadowHistoryResult(
        cache_hit=False,
        skip_reason=str(decision["skip_reason"]),
        append_executed=append_executed,
        appended_rows=appended_rows,
        outcome_recomputed=outcome_recomputed,
        outcome_recomputed_rows=outcome_rows,
        summary_rebuilt=append_executed,
        semantic_snapshot_key=decision["semantic_snapshot_key"],
        snapshot_key_match=False,
        elapsed_seconds=elapsed,
        ledger_summary=ledger_summary,
        safety=safety,
        recomputed_outputs=recomputed,
    )
    _apply_profiler(profiler, result)
    return result


def _apply_profiler(profiler: Any | None, result: ShadowHistoryResult, *, saved_seconds: float = 0.0) -> None:
    if profiler is None:
        return
    mapping = {
        "shadow_history_cache_hit": result.cache_hit,
        "shadow_history_append_executed": result.append_executed,
        "shadow_history_appended_rows": result.appended_rows,
        "shadow_history_outcome_recomputed_rows": result.outcome_recomputed_rows,
        "shadow_history_snapshot_key_match": result.snapshot_key_match,
    }
    for key, val in mapping.items():
        if hasattr(profiler, key):
            setattr(profiler, key, val)
    if result.cache_hit and saved_seconds > 0 and hasattr(profiler, "shadow_history_saved_seconds_estimate"):
        prev = float(getattr(profiler, "shadow_history_saved_seconds_estimate", 0.0) or 0.0)
        profiler.shadow_history_saved_seconds_estimate = round(prev + saved_seconds, 2)
        if hasattr(profiler, "record_cache_hit"):
            profiler.record_cache_hit()
