"""P1.6c — shadow flow dashboard refresh cache decision."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.alpha_v2.cache_decision import compute_flow_hash
from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash

DECISION_JSON = "shadow_flow_cache_decision.json"

FLOW_REQUIRED_OUTPUTS: tuple[str, ...] = (
    "flow_daily_timeseries.csv",
    "flow_dashboard_summary.json",
)

ALLOWED_STANDARD_SHADOW_FLOW_REFRESH_REASONS: frozenset[str] = frozenset({
    "no_previous_flow_cache",
    "flow_required_outputs_missing",
    "flow_hash_changed",
    "flow_as_of_not_covered",
    "explicit_user_force_refresh",
    "deep_force_refresh",
    "alpha_v2_full_refresh",
})


def _investor_flows_covers_as_of(data_dir: Path, as_of: str) -> bool:
    path = data_dir / "investor_flows.csv"
    if not path.exists():
        return False
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str, usecols=["date"], keep_default_na=False)
        if df.empty:
            return False
        return str(df["date"].max())[:10] >= as_of[:10]
    except Exception:
        return False


def _flow_timeseries_covers_as_of(output_dir: Path, as_of: str) -> bool:
    path = output_dir / "flow_daily_timeseries.csv"
    if not path.exists():
        return False
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str, usecols=["date"], keep_default_na=False)
        if df.empty:
            return False
        return str(df["date"].max())[:10] >= as_of[:10]
    except Exception:
        return False


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_flow_dependency_hash(data_dir: Path, output_dir: Path) -> str:
    parts = [
        compute_flow_hash(data_dir),
        compute_semantic_file_hash(output_dir / "flow_daily_timeseries.csv"),
        compute_semantic_file_hash(output_dir / "flow_dashboard_summary.json"),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def load_previous_shadow_flow_decision(output_dir: Path) -> dict[str, Any]:
    path = output_dir / DECISION_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _flow_outputs_present(output_dir: Path) -> tuple[bool, list[str]]:
    missing = [name for name in FLOW_REQUIRED_OUTPUTS if not (output_dir / name).exists()]
    return not missing, missing


def _alpha_v2_reused(output_dir: Path, profiler: Any | None) -> bool:
    if profiler is not None and getattr(profiler, "alpha_v2_reused_from_cache", False):
        return True
    path = output_dir / "alpha_v2_cache_decision.json"
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("decision") == "reuse_cache" or doc.get("alpha_v2_reused_from_cache"):
                return True
        except Exception:
            pass
    return False


def evaluate_shadow_flow_cache_decision(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_mode: str = "standard",
    run_id: str = "",
    force_refresh: bool = False,
    profiler: Any | None = None,
    pykrx_before: int = 0,
) -> dict[str, Any]:
    as_of_req = as_of[:10]
    alpha_reused = _alpha_v2_reused(output_dir, profiler)
    flow_dep_current = compute_flow_dependency_hash(data_dir, output_dir)
    prev = load_previous_shadow_flow_decision(output_dir)
    flow_dep_previous = str(prev.get("flow_dependency_hash_current") or "")
    outputs_ok, missing = _flow_outputs_present(output_dir)
    flow_as_of_avail = ""
    if _investor_flows_covers_as_of(data_dir, as_of_req):
        try:
            import pandas as pd

            df = pd.read_csv(data_dir / "investor_flows.csv", dtype=str, usecols=["date"], keep_default_na=False)
            if not df.empty:
                flow_as_of_avail = str(df["date"].max())[:10]
        except Exception:
            flow_as_of_avail = as_of_req
    elif _flow_timeseries_covers_as_of(output_dir, as_of_req):
        try:
            import pandas as pd

            df = pd.read_csv(output_dir / "flow_daily_timeseries.csv", dtype=str, usecols=["date"], keep_default_na=False)
            if not df.empty:
                flow_as_of_avail = str(df["date"].max())[:10]
        except Exception:
            pass
    flow_as_of_covered = flow_as_of_avail >= as_of_req if flow_as_of_avail else _flow_timeseries_covers_as_of(output_dir, as_of_req)
    flow_hash_match = bool(flow_dep_previous and flow_dep_previous == flow_dep_current)
    blockers: list[str] = []
    mode = str(run_mode).lower()

    if mode == "deep" and (force_refresh or not alpha_reused):
        skip = False
        refresh_reason = "deep_force_refresh"
    elif mode == "quick":
        skip = outputs_ok and flow_as_of_covered
        refresh_reason = "shadow_flow_cache_reuse" if skip else "quick_cache_only"
        if not outputs_ok:
            blockers.append("flow_required_outputs_missing")
        if not flow_as_of_covered:
            blockers.append("flow_as_of_not_covered")
    elif force_refresh:
        skip = False
        refresh_reason = "explicit_user_force_refresh"
    elif not outputs_ok:
        skip = False
        refresh_reason = "flow_required_outputs_missing"
        blockers.append("flow_required_outputs_missing")
    elif not flow_as_of_covered:
        skip = False
        refresh_reason = "flow_as_of_not_covered"
        blockers.append("flow_as_of_not_covered")
    elif mode == "standard" and alpha_reused and flow_hash_match:
        skip = True
        refresh_reason = "alpha_v2_cache_reuse"
    elif mode == "standard" and alpha_reused and flow_as_of_covered:
        skip = True
        refresh_reason = "alpha_v2_cache_reuse"
    elif not prev and mode == "standard":
        skip = False
        refresh_reason = "no_previous_flow_cache"
        blockers.append("no_previous_flow_cache")
    elif flow_dep_previous and not flow_hash_match:
        skip = False
        refresh_reason = "flow_hash_changed"
        blockers.append("flow_hash_changed")
    elif mode == "standard" and alpha_reused:
        skip = True
        refresh_reason = "alpha_v2_cache_reuse"
    else:
        skip = False
        refresh_reason = "flow_refresh_required"

    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "alpha_v2_reused_from_cache": alpha_reused,
        "shadow_flow_refresh_executed": not skip,
        "shadow_flow_reused_from_cache": skip,
        "flow_as_of_required": as_of_req,
        "flow_as_of_available": flow_as_of_avail,
        "flow_as_of_covered": flow_as_of_covered,
        "flow_dependency_hash_current": flow_dep_current,
        "flow_dependency_hash_previous": flow_dep_previous,
        "flow_hash_match": flow_hash_match,
        "refresh_reason": refresh_reason,
        "cache_blockers": blockers,
        "required_outputs_present": outputs_ok,
        "missing_outputs": missing,
        "pykrx_call_count_before": pykrx_before,
        "pykrx_call_count_after": pykrx_before,
    }
    return doc


def write_shadow_flow_cache_decision(output_dir: Path, doc: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / DECISION_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def apply_shadow_flow_decision_to_profiler(profiler: Any | None, doc: dict[str, Any]) -> None:
    if profiler is None:
        return
    mapping = {
        "shadow_flow_refresh_executed": bool(doc.get("shadow_flow_refresh_executed")),
        "shadow_flow_reused_from_cache": bool(doc.get("shadow_flow_reused_from_cache")),
        "shadow_flow_refresh_reason": str(doc.get("refresh_reason") or ""),
        "shadow_flow_cache_blockers": list(doc.get("cache_blockers") or []),
        "shadow_flow_as_of_covered": bool(doc.get("flow_as_of_covered")),
    }
    for key, val in mapping.items():
        if hasattr(profiler, key):
            setattr(profiler, key, val)
    if doc.get("shadow_flow_reused_from_cache"):
        if hasattr(profiler, "flow_refresh_executed"):
            profiler.flow_refresh_executed = False
        if hasattr(profiler, "flow_refresh_reason"):
            profiler.flow_refresh_reason = "shadow_flow_cache_reuse"
        if hasattr(profiler, "add_note"):
            profiler.add_note("Shadow flow dashboard: reused from cache (alpha_v2 cache reuse)")


def finalize_shadow_flow_pykrx(profiler: Any | None, doc: dict[str, Any]) -> dict[str, Any]:
    after = int(getattr(profiler, "pykrx_call_count", 0) or 0) if profiler else int(doc.get("pykrx_call_count_before") or 0)
    doc["pykrx_call_count_after"] = after
    return doc


def maybe_run_shadow_flow_dashboard(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_mode: str,
    run_id: str,
    force_refresh: bool,
    refresh_mode: str,
    max_tickers: int = 80,
    profiler: Any | None = None,
) -> dict[str, Any]:
    """Run or skip shadow flow dashboard based on cache decision."""
    pykrx_before = int(getattr(profiler, "pykrx_call_count", 0) or 0) if profiler else 0
    doc = evaluate_shadow_flow_cache_decision(
        data_dir,
        output_dir,
        as_of=as_of,
        run_mode=run_mode,
        run_id=run_id,
        force_refresh=force_refresh,
        profiler=profiler,
        pykrx_before=pykrx_before,
    )
    apply_shadow_flow_decision_to_profiler(profiler, doc)

    if doc.get("shadow_flow_reused_from_cache"):
        from src.alpha_flow.flow_analytics import reuse_flow_dashboard_outputs

        reuse_flow_dashboard_outputs(
            data_dir,
            output_dir,
            as_of=as_of,
            max_tickers=max_tickers,
            profiler=profiler,
            stale_flow_warning=not doc.get("flow_as_of_covered"),
        )
        doc = finalize_shadow_flow_pykrx(profiler, doc)
        write_shadow_flow_cache_decision(output_dir, doc)
        return doc

    from src.alpha_flow.flow_analytics import run_flow_dashboard_outputs

    run_flow_dashboard_outputs(
        data_dir,
        output_dir,
        as_of=as_of,
        max_tickers=max_tickers,
        refresh_mode=refresh_mode,
        profiler=profiler,
    )
    doc["shadow_flow_refresh_executed"] = True
    doc["shadow_flow_reused_from_cache"] = False
    doc = finalize_shadow_flow_pykrx(profiler, doc)
    write_shadow_flow_cache_decision(output_dir, doc)
    return doc
