"""P1.6b — Alpha v2 cache decision before refresh execution."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.alpha_v2.input_hash import (
    PRICE_HASH_MODE,
    compute_alpha_v2_input_hash,
    compute_flow_hash,
    compute_prices_as_of_hash,
    compute_stable_input_hash,
    load_price_hash_drift_debug,
)
from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash

DECISION_JSON = "alpha_v2_cache_decision.json"
HASH_DOC = "alpha_v2_input_hash.json"

REQUIRED_OUTPUTS: tuple[str, ...] = (
    "alpha_v2_scored.csv",
    "alpha_v2_summary.json",
    "alpha_v2_top30.csv",
    "alpha_v2_final_candidates.csv",
)

ALLOWED_STANDARD_REFRESH_REASONS: frozenset[str] = frozenset({
    "no_previous_alpha_v2_cache",
    "required_outputs_missing",
    "input_hash_changed",
    "as_of_not_covered",
    "explicit_user_force_refresh",
    "deep_force_refresh",
    "previous_run_failed",
})


def _canonical_json(obj: Any) -> str:
    import json as _json

    return _json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_previous_decision(output_dir: Path) -> dict[str, Any]:
    path = output_dir / DECISION_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_stored_hash(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / HASH_DOC
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _required_outputs_status(output_dir: Path) -> tuple[bool, list[str]]:
    missing = [name for name in REQUIRED_OUTPUTS if not (output_dir / name).exists()]
    return not missing, missing


def _as_of_available(data_dir: Path) -> str:
    path = data_dir / "market_indicators.csv"
    if not path.exists():
        return ""
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str, nrows=1)
        if not df.empty and "date" in df.columns:
            return str(df.iloc[0]["date"])[:10]
    except Exception:
        pass
    return ""


def _previous_run_ok(prev: dict[str, Any], output_dir: Path) -> bool:
    if prev.get("decision") == "reuse_cache":
        return True
    summary_path = output_dir / "alpha_v2_summary.json"
    if not summary_path.exists():
        return False
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    failures = list(summary.get("kosdaq_validation_failures") or [])
    fatal = [f for f in failures if "buy_permission" in str(f)]
    return not fatal


SNAPSHOT_JSON = "pipeline_stable_input_snapshot.json"
COMMITTED_SNAPSHOT_JSON = "pipeline_stable_input_snapshot_committed.json"


def write_pipeline_input_snapshot(
    output_dir: Path,
    data_dir: Path,
    *,
    as_of: str,
    run_id: str,
) -> dict[str, Any]:
    as_of_s = as_of[:10]
    doc = {
        "run_id": run_id,
        "as_of": as_of_s,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stable_input_hash": compute_stable_input_hash(data_dir, as_of=as_of_s),
        "flow_hash": compute_flow_hash(data_dir),
        "universe_hash": compute_semantic_file_hash(data_dir / "universe.csv"),
        "price_hash": compute_prices_as_of_hash(data_dir, as_of_s),
        "prices_history_hash": compute_semantic_file_hash(data_dir / "prices_history.csv"),
        "fundamentals_pit_hash": compute_semantic_file_hash(data_dir / "fundamentals_pit.csv"),
        "fundamentals_hash": compute_semantic_file_hash(data_dir / "fundamentals.csv"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / SNAPSHOT_JSON).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def load_pipeline_input_snapshot(output_dir: Path) -> dict[str, Any]:
    path = output_dir / SNAPSHOT_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_committed_pipeline_input_snapshot(output_dir: Path) -> dict[str, Any]:
    path = output_dir / COMMITTED_SNAPSHOT_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def commit_pipeline_input_snapshot(
    output_dir: Path,
    data_dir: Path,
    *,
    as_of: str,
    run_id: str = "",
) -> dict[str, Any]:
    """Persist post-pipeline stable inputs for the next run's cache comparison."""
    doc = write_pipeline_input_snapshot(output_dir, data_dir, as_of=as_of, run_id=run_id or "committed")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / COMMITTED_SNAPSHOT_JSON).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return doc


def sync_decision_from_snapshot(doc: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Align cache decision fields with a stable-input snapshot."""
    stable = str(snapshot.get("stable_input_hash") or "")
    if stable:
        doc["input_hash_current"] = stable
        doc["stable_input_hash_at_refresh"] = stable
    for key in (
        "universe_hash",
        "price_hash",
        "prices_history_hash",
        "fundamentals_pit_hash",
        "fundamentals_hash",
        "flow_hash",
    ):
        if snapshot.get(key):
            target = "flow_hash_current" if key == "flow_hash" else key
            doc[target] = snapshot[key]
    return doc


def commit_alpha_v2_cache_state(
    output_dir: Path,
    data_dir: Path,
    decision_doc: dict[str, Any],
    *,
    as_of: str,
    run_id: str,
) -> dict[str, Any]:
    """Write committed snapshot + input hash doc and sync decision fields."""
    snapshot = commit_pipeline_input_snapshot(
        output_dir, data_dir, as_of=as_of, run_id=run_id,
    )
    store_input_hash(output_dir, data_dir, as_of=as_of)
    return sync_decision_from_snapshot(decision_doc, snapshot)


def evaluate_alpha_v2_cache_decision(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_mode: str = "standard",
    run_id: str = "",
    force_refresh: bool = False,
    cache_reuse: bool = False,
    pykrx_before: int = 0,
) -> dict[str, Any]:
    from src.runtime.run_mode_contract import investor_flows_covers_as_of

    as_of_req = as_of[:10]
    as_of_avail = _as_of_available(data_dir) or as_of_req
    snapshot = load_pipeline_input_snapshot(output_dir)
    committed = load_committed_pipeline_input_snapshot(output_dir)
    stable_current = str(snapshot.get("stable_input_hash") or "") or compute_stable_input_hash(data_dir, as_of=as_of_req)
    flow_current = str(snapshot.get("flow_hash") or "") or compute_flow_hash(data_dir)
    prev_decision = load_previous_decision(output_dir)
    prev_hash_doc = load_stored_hash(output_dir) or {}
    stable_previous = str(
        committed.get("stable_input_hash")
        or prev_decision.get("stable_input_hash_at_refresh")
        or prev_decision.get("input_hash_current")
        or prev_hash_doc.get("stable_input_hash")
        or "",
    )
    flow_previous = str(
        committed.get("flow_hash")
        or prev_decision.get("flow_hash_current")
        or prev_hash_doc.get("flow_hash")
        or "",
    )
    outputs_ok, missing = _required_outputs_status(output_dir)
    as_of_covered = as_of_avail >= as_of_req
    flow_covers = investor_flows_covers_as_of(data_dir, as_of_req)
    flow_hash_match = bool(flow_previous and flow_previous == flow_current)
    stable_match = bool(stable_previous and stable_previous == stable_current)
    prev_ok = _previous_run_ok(prev_decision, output_dir)
    has_previous = bool(prev_decision or prev_hash_doc)

    blockers: list[str] = []
    mode = str(run_mode).lower()

    if mode == "deep" and force_refresh:
        decision = "full_refresh"
        refresh_reason = "deep_force_refresh"
    elif mode == "quick":
        if outputs_ok and stable_match and as_of_covered:
            decision = "reuse_cache"
            refresh_reason = "input_hash_unchanged"
        else:
            decision = "blocked_no_cache"
            refresh_reason = "quick_cache_only"
            if not outputs_ok:
                blockers.append("required_outputs_missing")
            if not stable_match:
                blockers.append("input_hash_changed")
            if not as_of_covered:
                blockers.append("as_of_not_covered")
    elif force_refresh:
        decision = "full_refresh"
        refresh_reason = "explicit_user_force_refresh"
    elif not has_previous:
        decision = "full_refresh"
        refresh_reason = "no_previous_alpha_v2_cache"
        blockers.append("no_previous_alpha_v2_cache")
    elif not outputs_ok:
        decision = "full_refresh"
        refresh_reason = "required_outputs_missing"
        blockers.append("required_outputs_missing")
    elif not as_of_covered:
        decision = "full_refresh"
        refresh_reason = "as_of_not_covered"
        blockers.append("as_of_not_covered")
    elif not stable_match:
        decision = "full_refresh"
        refresh_reason = "input_hash_changed"
        blockers.append("input_hash_changed")
        snap = snapshot or {}
        prev_doc = committed or prev_decision or prev_hash_doc
        for label, key in (
            ("universe_changed", "universe_hash"),
            ("prices_changed", "price_hash"),
            ("prices_history_changed", "prices_history_hash"),
            ("fundamentals_pit_changed", "fundamentals_pit_hash"),
            ("fundamentals_changed", "fundamentals_hash"),
        ):
            cur_v = str(snap.get(key) or "")
            prev_v = str(prev_doc.get(key) or prev_hash_doc.get(key) or "")
            if cur_v and prev_v and cur_v != prev_v:
                blockers.append(label)
    elif not prev_ok:
        decision = "full_refresh"
        refresh_reason = "previous_run_failed"
        blockers.append("previous_run_failed")
    elif cache_reuse or mode == "standard":
        decision = "reuse_cache"
        refresh_reason = "input_hash_unchanged"
    else:
        decision = "full_refresh"
        refresh_reason = "full_scoring"

    reuse = decision == "reuse_cache"
    if not flow_hash_match and not flow_covers and decision == "reuse_cache":
        pass  # stale flow is warning only — does not block reuse

    price_hash_current = str(snapshot.get("price_hash") or "") or compute_prices_as_of_hash(data_dir, as_of_req)
    price_hash_previous = str(
        committed.get("price_hash")
        or prev_decision.get("price_hash_current")
        or prev_decision.get("price_hash")
        or prev_hash_doc.get("price_hash")
        or "",
    )
    price_hash_match = bool(price_hash_previous and price_hash_previous == price_hash_current)
    drift_debug = load_price_hash_drift_debug(output_dir)
    price_hash_drift_reason = ""
    if not price_hash_match and price_hash_previous:
        if "prices_changed" in blockers:
            price_hash_drift_reason = "subset_values_changed"
        else:
            price_hash_drift_reason = "subset_hash_mismatch"
    elif price_hash_match:
        price_hash_drift_reason = "subset_unchanged"

    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "alpha_v2_reused_from_cache": reuse,
        "alpha_v2_full_refresh_executed": not reuse,
        "force_refresh": force_refresh,
        "input_hash_current": stable_current,
        "input_hash_previous": stable_previous,
        "input_hash_match": stable_match,
        "composite_input_hash": compute_alpha_v2_input_hash(data_dir, as_of=as_of_req),
        "required_outputs_present": outputs_ok,
        "missing_outputs": missing,
        "as_of_required": as_of_req,
        "as_of_available": as_of_avail,
        "as_of_covered": as_of_covered,
        "flow_hash_current": flow_current,
        "flow_hash_previous": flow_previous,
        "flow_hash_match": flow_hash_match,
        "flow_covers_as_of": flow_covers,
        "refresh_reason": refresh_reason,
        "cache_blockers": blockers,
        "pykrx_call_count_before": pykrx_before,
        "pykrx_call_count_after": pykrx_before,
        "snapshot_run_id": str(snapshot.get("run_id") or ""),
        "universe_hash": str(snapshot.get("universe_hash") or ""),
        "price_hash": price_hash_current,
        "price_hash_mode": PRICE_HASH_MODE,
        "price_hash_previous": price_hash_previous,
        "price_hash_current": price_hash_current,
        "price_hash_match": price_hash_match,
        "price_hash_drift_reason": price_hash_drift_reason,
        "price_fetch_executed_before_alpha_v2": bool(drift_debug.get("price_fetch_executed")),
        "price_write_executed_before_alpha_v2": bool(drift_debug.get("price_write_executed")),
        "prices_history_hash": str(snapshot.get("prices_history_hash") or ""),
        "fundamentals_pit_hash": str(snapshot.get("fundamentals_pit_hash") or ""),
        "fundamentals_hash": str(snapshot.get("fundamentals_hash") or ""),
    }
    return doc


def write_alpha_v2_cache_decision(output_dir: Path, doc: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / DECISION_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def store_input_hash(
    output_dir: Path,
    data_dir: Path,
    *,
    as_of: str,
    input_hash: str | None = None,
) -> None:
    as_of_s = as_of[:10]
    stable = compute_stable_input_hash(data_dir, as_of=as_of_s)
    flow_h = compute_flow_hash(data_dir)
    composite = input_hash or compute_alpha_v2_input_hash(data_dir, as_of=as_of_s)
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "as_of": as_of_s,
        "input_hash": composite,
        "stable_input_hash": stable,
        "flow_hash": flow_h,
        "universe_hash": compute_semantic_file_hash(data_dir / "universe.csv"),
        "price_hash": compute_prices_as_of_hash(data_dir, as_of_s),
        "fundamental_hash": compute_semantic_file_hash(data_dir / "fundamentals_pit.csv"),
        "flow_hash_note": "flow_hash excluded from stable_input_hash; stale flow does not force refresh",
    }
    (output_dir / HASH_DOC).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_decision_to_profiler(profiler: Any | None, doc: dict[str, Any]) -> None:
    if profiler is None:
        return
    mapping = {
        "alpha_v2_cache_decision": doc.get("decision"),
        "alpha_v2_cache_blockers": list(doc.get("cache_blockers") or []),
        "alpha_v2_input_hash_match": bool(doc.get("input_hash_match")),
        "alpha_v2_required_outputs_present": bool(doc.get("required_outputs_present")),
        "alpha_v2_as_of_covered": bool(doc.get("as_of_covered")),
        "alpha_v2_refresh_reason": str(doc.get("refresh_reason") or ""),
        "alpha_v2_reused_from_cache": bool(doc.get("alpha_v2_reused_from_cache")),
        "alpha_v2_full_refresh_executed": bool(doc.get("alpha_v2_full_refresh_executed")),
    }
    for key, val in mapping.items():
        if hasattr(profiler, key):
            setattr(profiler, key, val)


def finalize_decision_pykrx_after(profiler: Any | None, doc: dict[str, Any]) -> dict[str, Any]:
    after = int(getattr(profiler, "pykrx_call_count", 0) or 0) if profiler else int(doc.get("pykrx_call_count_before") or 0)
    doc["pykrx_call_count_after"] = after
    return doc
