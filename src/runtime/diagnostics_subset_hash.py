"""P1.5 — per-diagnostic dependency subset hash."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HASH_MODE = "subset_semantic"
SUBSET_DEBUG_MANIFEST = "diagnostics_subset_hash_debug.json"

VOLATILE_KEYS: frozenset[str] = frozenset({
    "run_id", "generated_at", "created_at", "updated_at", "timestamp",
    "as_of_generated_at", "elapsed_seconds", "duration_seconds", "runtime_seconds",
    "profile", "step_timings", "slowest_steps", "cache_hit_count", "cache_miss_count",
    "diagnostics_cache_hit_count", "diagnostics_cache_miss_count",
    "bundle_reconcile_cache_hit_count", "bundle_reconcile_cache_miss_count",
    "source_mtime", "file_mtime", "health_snapshot_id", "reused_from_run_id",
    "last_compute_seconds", "last_checked_at", "last_successful_flow_refresh",
    "paths", "warnings", "cache_meta", "pykrx_call_count", "pykrx_failed_tickers",
})


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json_semantic(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return round(value, 10)
    if isinstance(value, str):
        return value.strip()
    return value


def normalize_for_semantic_hash(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key in sorted(obj.keys()):
            if key in VOLATILE_KEYS:
                continue
            out[key] = normalize_for_semantic_hash(obj[key])
        return out
    if isinstance(obj, list):
        return [normalize_for_semantic_hash(item) for item in obj]
    return _normalize_scalar(obj)


def _csv_semantic_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    text = path.read_text(encoding="utf-8")
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames:
            rows = sorted(reader, key=lambda r: tuple(r.get(c, "") for c in reader.fieldnames))
            payload = {"columns": list(reader.fieldnames), "rows": rows}
            return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]
    except Exception:
        pass
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def compute_semantic_file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    suffix = path.suffix.lower()
    if suffix == ".json":
        doc = load_json_semantic(path)
        if doc is None:
            return "invalid"
        return hashlib.sha256(_canonical_json(normalize_for_semantic_hash(doc)).encode("utf-8")).hexdigest()[:16]
    if suffix in {".yaml", ".yml"}:
        try:
            from src.config import load_yaml

            doc = load_yaml(path)
            return hashlib.sha256(_canonical_json(normalize_for_semantic_hash(doc)).encode("utf-8")).hexdigest()[:16]
        except Exception:
            return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    if suffix == ".csv":
        return _csv_semantic_hash(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]

HASH_MODE = "subset_semantic"
SUBSET_DEBUG_MANIFEST = "diagnostics_subset_hash_debug.json"

SAFETY_FIELD_PATHS: tuple[str, ...] = (
    "target_hash",
    "user_target_hash",
    "target_guard_severity",
    "changed_rows",
    "proposal_leak",
    "material",
    "actual_buy_allowed",
    "final_actual_buy_allowed",
    "execution_scope",
    "authoritative_execution_scope",
    "status_alignment_pass",
    "target_write_occurred",
    "policy_cap_active",
)


@dataclass
class LoadedDependencyInputs:
    data_dir: Path
    output_dir: Path
    paths: dict[str, Path] = field(default_factory=dict)
    final: dict[str, Any] = field(default_factory=dict)
    acceptance: dict[str, Any] = field(default_factory=dict)
    daily_brief: dict[str, Any] = field(default_factory=dict)
    alpha_v2: dict[str, Any] = field(default_factory=dict)
    flow: dict[str, Any] = field(default_factory=dict)
    portfolio_policy: dict[str, Any] = field(default_factory=dict)
    pmi_kr_manual: dict[str, Any] = field(default_factory=dict)
    tier2_provenance: dict[str, Any] = field(default_factory=dict)
    target_portfolio_hash: str = "missing"
    user_target_portfolio_hash: str = "missing"
    alpha_candidates_hash: str = "missing"
    alpha_signal_board_hash: str = "missing"
    actual_buy_allowed: int = 0


def _acceptance_guard(acceptance: dict[str, Any]) -> dict[str, Any]:
    for item in acceptance.get("items") or []:
        if isinstance(item, dict) and item.get("name") == "target_portfolio_guard":
            return item.get("detail") or {}
    return {}


def _acceptance_item_detail(acceptance: dict[str, Any], name: str) -> dict[str, Any]:
    for item in acceptance.get("items") or []:
        if isinstance(item, dict) and item.get("name") == name:
            return item.get("detail") or {}
    return {}


def _system_status(loaded: LoadedDependencyInputs) -> dict[str, Any]:
    return loaded.daily_brief.get("system_status") or {}


def _policy_cap(final: dict[str, Any], sys_status: dict[str, Any]) -> dict[str, Any]:
    cap = final.get("policy_cap") or {}
    return {
        "active": cap.get("active") if cap else sys_status.get("policy_cap_active"),
        "cap_regime": cap.get("cap_regime") or sys_status.get("policy_cap_regime"),
        "reason": cap.get("reason") or final.get("policy_cap_reason"),
    }


def _tier2_stale_signature(tier2: dict[str, Any]) -> list[dict[str, Any]]:
    fields = tier2.get("fields") or {}
    rows: list[dict[str, Any]] = []
    for name, meta in sorted(fields.items()):
        if not isinstance(meta, dict):
            continue
        rows.append({
            "field": name,
            "status": meta.get("status"),
            "value_date": meta.get("value_date"),
            "stale_days": meta.get("stale_business_days") or meta.get("stale_days"),
            "value": meta.get("value"),
        })
    return rows


def _pmi_kr_from_tier2(tier2: dict[str, Any]) -> dict[str, Any]:
    meta = (tier2.get("fields") or {}).get("pmi_kr") or {}
    if not isinstance(meta, dict):
        return {}
    return {
        "status": meta.get("status"),
        "value": meta.get("value"),
        "value_date": meta.get("value_date"),
        "stale_days": meta.get("stale_business_days") or meta.get("stale_days"),
    }


def _flow_operational(flow: dict[str, Any]) -> dict[str, Any]:
    return {
        "fresh_flow_count": flow.get("fresh_flow_count"),
        "stale_flow_count": flow.get("stale_flow_count"),
        "fresh_count": flow.get("fresh_count"),
        "stale_count": flow.get("stale_count"),
        "fresh_ratio": flow.get("fresh_ratio"),
        "stale_ratio": flow.get("stale_ratio"),
        "ticker_count": flow.get("ticker_count"),
    }


def _shortlist_summary_subset(output_dir: Path) -> dict[str, Any]:
    doc = load_json_semantic(output_dir / "alpha_shortlist_summary.json") or {}
    return {
        "shortlist_eligible_count": doc.get("shortlist_eligible_count"),
        "b_grade_count": doc.get("b_grade_count"),
        "shortlist_pool_empty": doc.get("shortlist_pool_empty"),
    }


def _signal_board_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"buy_ready_count": 0, "signal_board_rows": 0}
    text = path.read_text(encoding="utf-8")
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        buy_ready = sum(1 for r in rows if str(r.get("action_state") or "") == "Buy-ready")
        return {"buy_ready_count": buy_ready, "signal_board_rows": len(rows)}
    except Exception:
        return {"buy_ready_count": 0, "signal_board_rows": 0}


def _grade_b_count(output_dir: Path) -> int:
    path = output_dir / "alpha_scored_universe.csv"
    if not path.exists():
        return 0
    try:
        reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
        return sum(1 for r in reader if str(r.get("grade") or "").upper() == "B")
    except Exception:
        return 0


def _gpt_context_count(output_dir: Path) -> int:
    doc = load_json_semantic(output_dir / "gpt_context.json") or {}
    candidates = doc.get("candidates") or doc.get("alpha_candidates") or []
    if isinstance(candidates, list):
        return len(candidates)
    return int(doc.get("candidate_count") or 0)


def _policy_shortlist_rules(policy: dict[str, Any]) -> dict[str, Any]:
    alpha = policy.get("alpha") or policy.get("alpha_shortlist") or {}
    pillars = policy.get("pillar_thresholds") or alpha.get("pillar_thresholds") or {}
    return {
        "min_pillars_pass": alpha.get("min_pillars_pass") or policy.get("min_pillars_pass"),
        "pillar_thresholds": pillars,
    }


def extract_common_safety_subset(loaded: LoadedDependencyInputs) -> dict[str, Any]:
    guard = _acceptance_guard(loaded.acceptance)
    sys_status = _system_status(loaded)
    final = loaded.final
    policy_cap = _policy_cap(final, sys_status)
    return {
        "target_hash": guard.get("current_hash") or guard.get("target_hash"),
        "user_target_hash": guard.get("user_target_hash"),
        "target_guard_severity": guard.get("severity") or guard.get("target_portfolio_guard_severity"),
        "changed_rows": guard.get("changed_rows"),
        "proposal_leak": guard.get("system_proposal_leak_count"),
        "material": guard.get("unknown_material_count"),
        "actual_buy_allowed": loaded.actual_buy_allowed,
        "final_actual_buy_allowed": loaded.actual_buy_allowed,
        "execution_scope": final.get("execution_scope") or sys_status.get("execution_scope"),
        "authoritative_execution_scope": (
            loaded.acceptance.get("authoritative_execution_scope")
            or sys_status.get("execution_scope")
        ),
        "target_guard_conflict_detected": bool(final.get("target_guard_conflict_detected")),
        "target_write_occurred": bool(
            final.get("target_restore_occurred") or final.get("last_target_write_allowed"),
        ),
        "policy_cap_active": policy_cap.get("active"),
    }


def load_dependency_inputs(data_dir: Path, output_dir: Path) -> LoadedDependencyInputs:
    from src.alpha.target_portfolio_guard import user_target_portfolio_path
    from src.report.execution_metrics import count_executable_actions

    paths = {
        "target_portfolio": data_dir / "target_portfolio.csv",
        "user_target_portfolio": user_target_portfolio_path(data_dir),
        "final_execution_decision": output_dir / "final_execution_decision.json",
        "acceptance_report": output_dir / "acceptance_report.json",
        "daily_brief": output_dir / "daily_brief.json",
        "alpha_candidates": output_dir / "alpha_candidates.csv",
        "alpha_signal_board": output_dir / "alpha_signal_board.csv",
        "alpha_v2_summary": output_dir / "alpha_v2_summary.json",
        "flow_dashboard_summary": output_dir / "flow_dashboard_summary.json",
        "portfolio_policy": data_dir / "portfolio_policy.yaml",
        "pmi_kr_manual": data_dir / "tier2_kosis_manual.yaml",
        "tier2_provenance": data_dir / "tier2_provenance.json",
    }
    final = load_json_semantic(paths["final_execution_decision"]) or {}
    policy: dict[str, Any] = {}
    try:
        from src.config import load_yaml

        policy = load_yaml(paths["portfolio_policy"])
        manual = load_yaml(paths["pmi_kr_manual"])
    except Exception:
        manual = {}
    tier2_path = paths["tier2_provenance"]
    if not tier2_path.exists():
        tier2_path = output_dir / "tier2_provenance.json"
    loaded = LoadedDependencyInputs(
        data_dir=data_dir,
        output_dir=output_dir,
        paths=paths,
        final=final,
        acceptance=load_json_semantic(paths["acceptance_report"]) or {},
        daily_brief=load_json_semantic(paths["daily_brief"]) or {},
        alpha_v2=load_json_semantic(paths["alpha_v2_summary"]) or {},
        flow=load_json_semantic(paths["flow_dashboard_summary"]) or {},
        portfolio_policy=policy,
        pmi_kr_manual=manual if isinstance(manual, dict) else {},
        tier2_provenance=load_json_semantic(tier2_path) or {},
        target_portfolio_hash=compute_semantic_file_hash(paths["target_portfolio"]),
        user_target_portfolio_hash=compute_semantic_file_hash(paths["user_target_portfolio"]),
        alpha_candidates_hash=_csv_semantic_hash(paths["alpha_candidates"]) if paths["alpha_candidates"].exists() else "missing",
        alpha_signal_board_hash=_csv_semantic_hash(paths["alpha_signal_board"]) if paths["alpha_signal_board"].exists() else "missing",
        actual_buy_allowed=int(count_executable_actions(final).get("actual_buy_allowed_count") or 0),
    )
    return loaded


def _subset_no_action(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    sys_status = _system_status(loaded)
    policy_cap = _policy_cap(loaded.final, sys_status)
    perms = loaded.final.get("execution_permissions") or {}
    fields = list(SAFETY_FIELD_PATHS) + [
        "data_gate_status", "portfolio_gate_status", "alpha_gate_status",
        "core_etf_permission", "policy_cap_regime", "target_guard_conflict_detected",
    ]
    subset = {
        **extract_common_safety_subset(loaded),
        "data_gate_status": sys_status.get("unified_data_gate") or sys_status.get("data_gate"),
        "portfolio_gate_status": sys_status.get("portfolio_gate"),
        "alpha_gate_status": sys_status.get("alpha_sector_data_gate"),
        "core_etf_permission": perms.get("core_etf_permission") or perms.get("etf_new_buy_state"),
        "policy_cap": policy_cap,
    }
    return subset, fields


def _subset_alpha_gate(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    sys_status = _system_status(loaded)
    board = _signal_board_counts(loaded.paths["alpha_signal_board"])
    shortlist = _shortlist_summary_subset(loaded.output_dir)
    fields = list(SAFETY_FIELD_PATHS) + [
        "alpha_gate_status", "tier2_stale_signature", "b_grade_count",
        "shortlist_eligible_count", "buy_ready_count", "gpt_context_candidate_count",
    ]
    subset = {
        **extract_common_safety_subset(loaded),
        "alpha_gate_status": sys_status.get("alpha_sector_data_gate"),
        "tier2_stale_signature": _tier2_stale_signature(loaded.tier2_provenance),
        "b_grade_count": _grade_b_count(loaded.output_dir),
        "shortlist_eligible_count": shortlist.get("shortlist_eligible_count"),
        "buy_ready_count": board.get("buy_ready_count"),
        "gpt_context_candidate_count": _gpt_context_count(loaded.output_dir),
        "signal_board_rows": board.get("signal_board_rows"),
    }
    return subset, fields


def _subset_alpha_shortlist(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    fields = list(SAFETY_FIELD_PATHS) + [
        "alpha_candidates_hash", "alpha_signal_board_hash",
        "target_portfolio_hash", "user_target_portfolio_hash", "policy_shortlist_rules",
    ]
    subset = {
        **extract_common_safety_subset(loaded),
        "alpha_candidates_hash": loaded.alpha_candidates_hash,
        "alpha_signal_board_hash": loaded.alpha_signal_board_hash,
        "target_portfolio_hash": loaded.target_portfolio_hash,
        "user_target_portfolio_hash": loaded.user_target_portfolio_hash,
        "policy_shortlist_rules": _policy_shortlist_rules(loaded.portfolio_policy),
    }
    return subset, fields


def _subset_core_etf(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    sys_status = _system_status(loaded)
    perms = loaded.final.get("execution_permissions") or {}
    fields = list(SAFETY_FIELD_PATHS) + [
        "data_gate_status", "core_etf_permission", "etf_new_buy_state",
    ]
    subset = {
        **extract_common_safety_subset(loaded),
        "data_gate_status": sys_status.get("unified_data_gate") or sys_status.get("data_gate"),
        "core_etf_permission": perms.get("core_etf_permission"),
        "etf_new_buy_state": perms.get("etf_new_buy") or perms.get("ETF_REBALANCE"),
    }
    return subset, fields


def _subset_data_gate(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    sys_status = _system_status(loaded)
    uni = _acceptance_item_detail(loaded.acceptance, "unified_data_gate")
    fields = list(SAFETY_FIELD_PATHS) + [
        "data_gate_status", "portfolio_gate_status", "alpha_gate_status", "health_gate_status",
        "stale_fields", "pmi_kr", "flow_operational", "tier2_stale_signature",
    ]
    subset = {
        **extract_common_safety_subset(loaded),
        "data_gate_status": sys_status.get("unified_data_gate") or sys_status.get("data_gate") or uni.get("status"),
        "portfolio_gate_status": sys_status.get("portfolio_gate"),
        "alpha_gate_status": sys_status.get("alpha_sector_data_gate"),
        "health_gate_status": sys_status.get("health_gate"),
        "stale_fields": sorted(uni.get("stale_fields") or []),
        "pmi_kr": _pmi_kr_from_tier2(loaded.tier2_provenance),
        "flow_operational": _flow_operational(loaded.flow),
        "tier2_stale_signature": _tier2_stale_signature(loaded.tier2_provenance),
    }
    return subset, fields


def _subset_policy_cap(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    sys_status = _system_status(loaded)
    policy_cap = _policy_cap(loaded.final, sys_status)
    shortlist = _shortlist_summary_subset(loaded.output_dir)
    fields = list(SAFETY_FIELD_PATHS) + [
        "policy_cap", "data_gate_status", "alpha_gate_status",
        "shortlist_eligible_count", "b_grade_count",
    ]
    subset = {
        **extract_common_safety_subset(loaded),
        "policy_cap": policy_cap,
        "data_gate_status": sys_status.get("unified_data_gate") or sys_status.get("data_gate"),
        "alpha_gate_status": sys_status.get("alpha_sector_data_gate"),
        "shortlist_eligible_count": shortlist.get("shortlist_eligible_count"),
        "b_grade_count": shortlist.get("b_grade_count") or _grade_b_count(loaded.output_dir),
    }
    return subset, fields


def _subset_pmi_kr(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    fields = list(SAFETY_FIELD_PATHS) + ["pmi_kr", "data_gate_status"]
    subset = {
        **extract_common_safety_subset(loaded),
        "pmi_kr": _pmi_kr_from_tier2(loaded.tier2_provenance),
        "data_gate_status": _system_status(loaded).get("unified_data_gate"),
    }
    return subset, fields


def _subset_green_preflight(loaded: LoadedDependencyInputs) -> tuple[dict[str, Any], list[str]]:
    fields = list(SAFETY_FIELD_PATHS) + ["data_gate_status", "pmi_kr", "portfolio_gate_status"]
    subset = {
        **extract_common_safety_subset(loaded),
        "data_gate_status": _system_status(loaded).get("unified_data_gate"),
        "portfolio_gate_status": _system_status(loaded).get("portfolio_gate"),
        "pmi_kr": _pmi_kr_from_tier2(loaded.tier2_provenance),
    }
    return subset, fields


SUBSET_EXTRACTORS: dict[str, Callable[[LoadedDependencyInputs], tuple[dict[str, Any], list[str]]]] = {
    "no_action_diagnostics": _subset_no_action,
    "alpha_gate_diagnostics": _subset_alpha_gate,
    "alpha_shortlist_diagnostics": _subset_alpha_shortlist,
    "core_etf_permission_diagnostics": _subset_core_etf,
    "data_gate_diagnostics": _subset_data_gate,
    "policy_cap_counterfactual": _subset_policy_cap,
    "pmi_kr_source_policy": _subset_pmi_kr,
    "data_gate_green_preflight": _subset_green_preflight,
}


def extract_dependency_subset(
    diagnostic_name: str,
    loaded: LoadedDependencyInputs,
) -> tuple[dict[str, Any], list[str]]:
    extractor = SUBSET_EXTRACTORS.get(diagnostic_name)
    if extractor is None:
        raise KeyError(f"unknown diagnostic subset: {diagnostic_name}")
    subset, fields = extractor(loaded)
    return normalize_for_semantic_hash(subset), fields


def compute_subset_dependency_hash(
    diagnostic_name: str,
    loaded: LoadedDependencyInputs,
) -> tuple[str, dict[str, Any], list[str]]:
    subset, fields = extract_dependency_subset(diagnostic_name, loaded)
    digest = hashlib.sha256(_canonical_json(subset).encode("utf-8")).hexdigest()[:16]
    return digest, subset, fields


def explain_subset_hash_changes(previous_subset: dict[str, Any], current_subset: dict[str, Any]) -> list[str]:
    changed: list[str] = []

    def _walk(path: str, prev: Any, curr: Any) -> None:
        if prev == curr:
            return
        if isinstance(prev, dict) and isinstance(curr, dict):
            keys = set(prev.keys()) | set(curr.keys())
            for key in sorted(keys):
                _walk(f"{path}.{key}" if path else key, prev.get(key), curr.get(key))
            return
        if isinstance(prev, list) and isinstance(curr, list):
            if prev != curr:
                changed.append(path or "root")
            return
        changed.append(path or "root")

    _walk("", previous_subset, current_subset)
    return changed


def write_subset_hash_debug_manifest(
    output_dir: Path,
    *,
    run_id: str,
    entries: dict[str, Any],
) -> None:
    doc = {
        "schema_version": "1.0",
        "hash_mode": HASH_MODE,
        "run_id": run_id,
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "entries": entries,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / SUBSET_DEBUG_MANIFEST).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
