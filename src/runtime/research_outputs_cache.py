"""P3b — research_outputs cache-first incremental reuse."""
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
    extract_common_safety_subset,
    load_dependency_inputs,
    normalize_for_semantic_hash,
)
from src.runtime.final_decision_core import compute_final_decision_core_hash, validate_final_decision_safety

MANIFEST_JSON = "research_outputs_manifest.json"

REQUIRED_RESEARCH_OUTPUTS: tuple[str, ...] = (
    "early_alpha_decision.json",
    "early_alpha_signals.csv",
    "early_alpha_brief.md",
    "opportunity_decision.json",
    "opportunity_signals.csv",
    "opportunity_brief.md",
    "opportunity_analytics.json",
    "opportunity_failure_database.json",
    "opportunity_post_analysis.csv",
    "alpha_performance_dashboard.json",
    "alpha_performance_dashboard.csv",
)

DEPENDENCY_FILES: tuple[tuple[str, str], ...] = (
    ("alpha_v2_summary", "alpha_v2_summary.json"),
    ("alpha_v2_scored", "alpha_v2_scored.csv"),
    ("alpha_v2_final_candidates", "alpha_v2_final_candidates.csv"),
    ("alpha_v2_top30", "alpha_v2_top30.csv"),
    ("flow_dashboard_summary", "flow_dashboard_summary.json"),
    ("alpha_shortlist_summary", "alpha_shortlist_summary.json"),
    ("alpha_gate_diagnostics", "alpha_gate_diagnostics.json"),
    ("policy_cap_counterfactual", "policy_cap_counterfactual.json"),
    ("core_etf_permission_diagnostics", "core_etf_permission_diagnostics.json"),
    ("target_portfolio", "data:target_portfolio.csv"),
    ("user_target_portfolio", "data:user_target_portfolio"),
    ("portfolio_policy", "data:portfolio_policy.yaml"),
    ("market_data_provenance", "data:market_data_provenance.json"),
    ("tier2_provenance", "data:tier2_provenance.json"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _resolve_dependency_path(data_dir: Path, output_dir: Path, spec: str) -> Path:
    if spec.startswith("data:"):
        rel = spec[5:]
        if rel == "user_target_portfolio":
            from src.alpha.target_portfolio_guard import user_target_portfolio_path

            return user_target_portfolio_path(data_dir)
        if rel == "tier2_provenance.json":
            p = data_dir / rel
            return p if p.exists() else output_dir / rel
        return data_dir / rel
    return output_dir / spec


def compute_research_dependency_hashes(data_dir: Path, output_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {
        "final_decision_core_hash": compute_final_decision_core_hash(output_dir),
    }
    for key, spec in DEPENDENCY_FILES:
        path = _resolve_dependency_path(data_dir, output_dir, spec)
        hashes[key] = compute_semantic_file_hash(path)
    try:
        loaded = load_dependency_inputs(data_dir, output_dir)
        safety = extract_common_safety_subset(loaded)
        perms = loaded.final.get("execution_permissions") or {}
        sys_status = loaded.final.get("operating") or {}
        safety.update(
            {
                "data_gate_status": loaded.final.get("data_gate")
                or sys_status.get("unified_data_gate"),
                "alpha_gate_status": loaded.final.get("alpha_execution_status")
                or (loaded.final.get("alpha_approval")),
            },
        )
        if perms:
            safety["core_etf_permission"] = perms.get("core_etf_permission") or perms.get(
                "etf_new_buy_state",
            )
        hashes["safety_subset"] = hashlib.sha256(
            _canonical_json(normalize_for_semantic_hash(safety)).encode("utf-8"),
        ).hexdigest()[:16]
    except Exception:
        hashes["safety_subset"] = "unavailable"
    return hashes


def compute_dependency_hash(hashes: dict[str, str]) -> str:
    payload = {k: hashes[k] for k in sorted(hashes)}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def _required_outputs_present(output_dir: Path) -> tuple[bool, list[str]]:
    missing = [name for name in REQUIRED_RESEARCH_OUTPUTS if not (output_dir / name).exists()]
    return not missing, missing


def _changed_dependency_files(
    current: dict[str, str],
    previous: dict[str, str] | None,
) -> list[str]:
    if not previous:
        return list(current.keys())
    changed: list[str] = []
    for key, val in current.items():
        if key == "safety_subset":
            continue
        prev_val = previous.get(key)
        if prev_val is None or prev_val != val:
            changed.append(key)
    return changed


def load_research_outputs_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / MANIFEST_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_research_outputs_manifest(output_dir: Path, doc: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MANIFEST_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def evaluate_research_outputs_cache(
    data_dir: Path,
    output_dir: Path,
    *,
    run_mode: str = "standard",
    force_refresh: bool = False,
) -> dict[str, Any]:
    hashes = compute_research_dependency_hashes(data_dir, output_dir)
    dependency_hash = compute_dependency_hash(hashes)
    prev = load_research_outputs_manifest(output_dir)
    prev_hash = str(prev.get("dependency_hash") or "")
    prev_file_hashes = prev.get("dependency_file_hashes") or {}
    outputs_ok, missing = _required_outputs_present(output_dir)
    hash_match = bool(prev_hash and prev_hash == dependency_hash)
    changed_files = _changed_dependency_files(hashes, prev_file_hashes if prev_file_hashes else None)
    blockers: list[str] = []
    mode = str(run_mode).lower()

    if mode == "bundle_only":
        cache_hit = outputs_ok
        skip_reason = "bundle_only_verify" if cache_hit else "bundle_only_missing_outputs"
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
    safety: dict[str, Any] = {
        "actual_buy_allowed": actual_buy,
        "target_write_count": 0,
        "target_guard_status": "unknown",
        "execution_scope": str(final_doc.get("execution_scope") or ""),
        "final_decision_present": bool(final_doc),
    }
    try:
        safety.update(validate_final_decision_safety(output_dir, data_dir))
    except Exception:
        pass
    return safety


def _run_research_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_id: str,
) -> list[str]:
    from src.alpha.early_alpha_engine import write_early_alpha_outputs
    from src.alpha.opportunity_analytics import write_opportunity_analytics
    from src.alpha.opportunity_engine import write_opportunity_outputs
    from src.alpha.performance_dashboard import write_alpha_performance_outputs

    recomputed: list[str] = []
    write_early_alpha_outputs(data_dir, output_dir, as_of=as_of)
    recomputed.append("early_alpha_outputs")
    opp_decision = write_opportunity_outputs(data_dir, output_dir, as_of=as_of)
    recomputed.append("opportunity_outputs")
    write_opportunity_analytics(data_dir, output_dir, opp_decision, as_of=as_of)
    recomputed.append("opportunity_analytics")
    write_alpha_performance_outputs(data_dir, output_dir, as_of=as_of, run_id=run_id)
    recomputed.append("alpha_performance_outputs")
    return recomputed


@dataclass
class ResearchOutputsResult:
    cache_hit: bool = False
    reused: bool = False
    recomputed: list[str] = field(default_factory=list)
    skip_reason: str = ""
    elapsed_seconds: float = 0.0
    dependency_hash: str = ""
    dependency_hash_changed: bool = False
    safety: dict[str, Any] = field(default_factory=dict)
    reused_outputs: list[str] = field(default_factory=list)
    missing_outputs: list[str] = field(default_factory=list)


def maybe_run_research_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_id: str,
    run_mode: str = "standard",
    force_refresh: bool = False,
    profiler: Any | None = None,
) -> ResearchOutputsResult:
    """Cache-first wrapper for research_outputs step."""
    t0 = time.perf_counter()
    decision = evaluate_research_outputs_cache(
        data_dir,
        output_dir,
        run_mode=run_mode,
        force_refresh=force_refresh,
    )
    safety = _build_safety_check(output_dir, data_dir)
    mode = str(run_mode).lower()

    if mode == "bundle_only":
        elapsed = time.perf_counter() - t0
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "run_mode": run_mode,
            "generated_at": _utc_now(),
            "cache_hit": decision["cache_hit"],
            "skip_reason": decision["skip_reason"],
            "dependency_hash": decision["dependency_hash"],
            "previous_dependency_hash": decision["previous_dependency_hash"],
            "changed_dependency_files": decision["changed_dependency_files"],
            "required_outputs_present": decision["required_outputs_present"],
            "missing_outputs": decision["missing_outputs"],
            "reused_outputs": list(REQUIRED_RESEARCH_OUTPUTS) if decision["cache_hit"] else [],
            "recomputed_outputs": [],
            "elapsed_seconds": round(elapsed, 4),
            "safety_check": safety,
        }
        write_research_outputs_manifest(output_dir, manifest)
        result = ResearchOutputsResult(
            cache_hit=decision["cache_hit"],
            reused=decision["cache_hit"],
            skip_reason=decision["skip_reason"],
            elapsed_seconds=elapsed,
            dependency_hash=decision["dependency_hash"],
            dependency_hash_changed=decision["dependency_hash_changed"],
            safety=safety,
            reused_outputs=list(REQUIRED_RESEARCH_OUTPUTS) if decision["cache_hit"] else [],
            missing_outputs=list(decision["missing_outputs"]),
        )
        _apply_profiler(profiler, result, decision)
        return result

    if decision["cache_hit"]:
        elapsed = time.perf_counter() - t0
        prev_elapsed = float(decision.get("previous_elapsed_seconds") or 0.0)
        saved = max(prev_elapsed, 60.0) if prev_elapsed > 0 else 60.0
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "run_mode": run_mode,
            "generated_at": _utc_now(),
            "cache_hit": True,
            "skip_reason": decision["skip_reason"],
            "dependency_hash": decision["dependency_hash"],
            "previous_dependency_hash": decision["previous_dependency_hash"],
            "changed_dependency_files": [],
            "required_outputs_present": True,
            "missing_outputs": [],
            "reused_outputs": list(REQUIRED_RESEARCH_OUTPUTS),
            "recomputed_outputs": [],
            "elapsed_seconds": round(elapsed, 4),
            "saved_seconds_estimate": round(saved, 2),
            "safety_check": safety,
        }
        write_research_outputs_manifest(output_dir, manifest)
        result = ResearchOutputsResult(
            cache_hit=True,
            reused=True,
            recomputed=[],
            skip_reason=str(decision["skip_reason"]),
            elapsed_seconds=elapsed,
            dependency_hash=decision["dependency_hash"],
            dependency_hash_changed=False,
            safety=safety,
            reused_outputs=list(REQUIRED_RESEARCH_OUTPUTS),
        )
        _apply_profiler(profiler, result, decision, saved_seconds=saved)
        return result

    recomputed = _run_research_outputs(data_dir, output_dir, as_of=as_of, run_id=run_id)
    elapsed = time.perf_counter() - t0
    safety = _build_safety_check(output_dir, data_dir)
    outputs_ok, missing = _required_outputs_present(output_dir)
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_mode": run_mode,
        "generated_at": _utc_now(),
        "cache_hit": False,
        "skip_reason": decision["skip_reason"] if not outputs_ok else "recomputed",
        "dependency_hash": decision["dependency_hash"],
        "previous_dependency_hash": decision["previous_dependency_hash"],
        "changed_dependency_files": decision["changed_dependency_files"],
        "required_outputs_present": outputs_ok,
        "missing_outputs": missing,
        "reused_outputs": [],
        "recomputed_outputs": recomputed,
        "elapsed_seconds": round(elapsed, 4),
        "safety_check": safety,
    }
    write_research_outputs_manifest(output_dir, manifest)
    result = ResearchOutputsResult(
        cache_hit=False,
        reused=False,
        recomputed=recomputed,
        skip_reason="recomputed",
        elapsed_seconds=elapsed,
        dependency_hash=decision["dependency_hash"],
        dependency_hash_changed=decision["dependency_hash_changed"],
        safety=safety,
        missing_outputs=missing,
    )
    _apply_profiler(profiler, result, decision)
    return result


def _apply_profiler(
    profiler: Any | None,
    result: ResearchOutputsResult,
    decision: dict[str, Any],
    *,
    saved_seconds: float = 0.0,
) -> None:
    if profiler is None:
        return
    mapping = {
        "research_outputs_cache_hit": result.cache_hit,
        "research_outputs_reused": result.reused,
        "research_outputs_recomputed": list(result.recomputed),
        "research_outputs_dependency_hash_changed": bool(decision.get("dependency_hash_changed")),
    }
    for key, val in mapping.items():
        if hasattr(profiler, key):
            setattr(profiler, key, val)
    if result.cache_hit and hasattr(profiler, "research_outputs_saved_seconds_estimate"):
        prev = float(getattr(profiler, "research_outputs_saved_seconds_estimate", 0.0) or 0.0)
        profiler.research_outputs_saved_seconds_estimate = round(prev + saved_seconds, 2)
        if hasattr(profiler, "record_cache_hit"):
            profiler.record_cache_hit()
