"""P1.6a — run-mode refresh contract validation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.alpha_v2_gate import (
    ALLOWED_STANDARD_PRICE_CHECK_REASONS,
    ALLOWED_STANDARD_PRICE_REFRESH_REASONS,
    ALLOWED_STANDARD_REFRESH_REASONS,
    ALLOWED_STANDARD_SHADOW_FLOW_REFRESH_REASONS,
)

CONTRACT_JSON = "run_mode_contract_validation.json"
PYKRX_MASS_CALL_THRESHOLD = 20
ALLOWED_PRICE_DRIFT_REASONS: frozenset[str] = frozenset({
    "subset_unchanged",
    "unchanged",
    "",
})


def _standard_price_cache_hit_safe(
    *,
    alpha_reused: bool,
    price_hash_match: bool,
    price_write: bool,
    pykrx_calls: int,
    price_drift_reason: str,
) -> bool:
    if not alpha_reused:
        return False
    if not price_hash_match or price_write or pykrx_calls != 0:
        return False
    return price_drift_reason in ALLOWED_PRICE_DRIFT_REASONS


def investor_flows_covers_as_of(data_dir: Path, as_of: str) -> bool:
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


def flow_timeseries_covers_as_of(output_dir: Path, as_of: str) -> bool:
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


def _record_flow_skip(profiler: Any | None, reason: str) -> None:
    if profiler is None:
        return
    if hasattr(profiler, "flow_refresh_executed"):
        profiler.flow_refresh_executed = False
    if hasattr(profiler, "flow_refresh_reason"):
        profiler.flow_refresh_reason = reason
    if hasattr(profiler, "flow_full_refresh_executed"):
        profiler.flow_full_refresh_executed = False


def _record_flow_run(
    profiler: Any | None,
    *,
    executed: bool,
    reason: str,
    full_refresh: bool,
    cache_hits: int = 0,
    cache_misses: int = 0,
) -> None:
    if profiler is None:
        return
    if hasattr(profiler, "flow_refresh_executed"):
        profiler.flow_refresh_executed = executed
    if hasattr(profiler, "flow_refresh_reason"):
        profiler.flow_refresh_reason = reason
    if hasattr(profiler, "flow_full_refresh_executed"):
        profiler.flow_full_refresh_executed = full_refresh
    if hasattr(profiler, "flow_cache_hit_count"):
        profiler.flow_cache_hit_count = int(getattr(profiler, "flow_cache_hit_count", 0)) + cache_hits
    if hasattr(profiler, "flow_cache_miss_count"):
        profiler.flow_cache_miss_count = int(getattr(profiler, "flow_cache_miss_count", 0)) + cache_misses


def _record_alpha_v2_reuse(profiler: Any | None, *, reason: str) -> None:
    if profiler is None:
        return
    if hasattr(profiler, "alpha_v2_reused_from_cache"):
        profiler.alpha_v2_reused_from_cache = True
    if hasattr(profiler, "alpha_v2_refresh_reason"):
        profiler.alpha_v2_refresh_reason = reason
    if hasattr(profiler, "alpha_v2_full_refresh_executed"):
        profiler.alpha_v2_full_refresh_executed = False


def _record_alpha_v2_full(profiler: Any | None, *, reason: str) -> None:
    if profiler is None:
        return
    if hasattr(profiler, "alpha_v2_reused_from_cache"):
        profiler.alpha_v2_reused_from_cache = False
    if hasattr(profiler, "alpha_v2_refresh_reason"):
        profiler.alpha_v2_refresh_reason = reason
    if hasattr(profiler, "alpha_v2_full_refresh_executed"):
        profiler.alpha_v2_full_refresh_executed = True


def validate_run_mode_contract(
    cfg: Any,
    profiler: Any | None,
    *,
    hooks_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_mode = str(getattr(getattr(cfg, "run_mode", None), "value", getattr(cfg, "run_mode", "standard")))
    violations: list[str] = []
    allowed_reasons: list[str] = []

    pykrx_calls = int(getattr(profiler, "pykrx_call_count", 0) or 0) if profiler else 0
    alpha_full = bool(getattr(profiler, "alpha_v2_full_refresh_executed", False)) if profiler else False
    flow_full = bool(getattr(profiler, "flow_full_refresh_executed", False)) if profiler else False
    kosdaq_sync = bool((hooks_meta or {}).get("kosdaq_sync")) and not (hooks_meta or {}).get("kosdaq_sync", {}).get("skipped")
    kosis_exec = bool(getattr(profiler, "kosis_refresh_executed", False)) if profiler else False
    kosis_dep_changed = bool(getattr(profiler, "kosis_dependency_hash_changed", False)) if profiler else False
    flow_reason = str(getattr(profiler, "flow_refresh_reason", "") or "") if profiler else ""
    shadow_flow_exec = bool(getattr(profiler, "shadow_flow_refresh_executed", False)) if profiler else False
    shadow_flow_reason = str(getattr(profiler, "shadow_flow_refresh_reason", "") or "") if profiler else ""
    alpha_reused = bool(getattr(profiler, "alpha_v2_reused_from_cache", False)) if profiler else False
    price_fetch = bool(getattr(profiler, "price_fetch_executed", False)) if profiler else False
    price_write = bool(getattr(profiler, "price_write_executed", False)) if profiler else False
    price_fetch_reason = str(getattr(profiler, "price_fetch_reason", "") or "") if profiler else ""
    price_hash_match = bool(getattr(profiler, "price_hash_match", False)) if profiler else False
    price_check_only = bool(getattr(profiler, "price_check_only", False)) if profiler else False
    price_network_fetch = bool(getattr(profiler, "price_network_fetch_executed", price_fetch)) if profiler else False
    price_drift_reason = str(getattr(profiler, "price_hash_drift_reason", "") or "") if profiler else ""
    alpha_blockers = list(getattr(profiler, "alpha_v2_cache_blockers", []) or []) if profiler else []
    price_contract_reason = ""
    allowed_price_check_reason = ""

    if run_mode == "quick":
        if getattr(cfg, "refresh_network", False):
            violations.append("quick mode must not refresh network")
        if alpha_full:
            violations.append("quick mode must not run alpha_v2 full refresh")
        if flow_full or bool(getattr(profiler, "flow_refresh_executed", False)):
            violations.append("quick mode must not run flow refresh")
        if bool(getattr(profiler, "price_fetch_executed", False)):
            violations.append("quick mode must not fetch prices")

    alpha_reason = str(getattr(profiler, "alpha_v2_refresh_reason", "") or "") if profiler else ""

    if run_mode == "standard":
        price_cache_hit_safe = _standard_price_cache_hit_safe(
            alpha_reused=alpha_reused,
            price_hash_match=price_hash_match,
            price_write=price_write,
            pykrx_calls=pykrx_calls,
            price_drift_reason=price_drift_reason,
        )
        if price_cache_hit_safe:
            price_contract_reason = "standard_price_cache_hit"
            allowed_price_check_reason = price_fetch_reason or "subset_unchanged"
        elif price_check_only and price_fetch_reason in ALLOWED_STANDARD_PRICE_CHECK_REASONS:
            price_contract_reason = "price_check_only"
            allowed_price_check_reason = price_fetch_reason

        if alpha_full and alpha_reason == "input_hash_unchanged":
            violations.append("alpha_v2 full refresh contradicts cache reuse reason")
        if alpha_full and alpha_reason not in ALLOWED_STANDARD_REFRESH_REASONS:
            violations.append(f"unexpected alpha_v2 full refresh ({alpha_reason})")
        if flow_full:
            violations.append("unexpected full flow refresh")
        if kosdaq_sync:
            violations.append("unexpected KOSDAQ sync")
        if pykrx_calls >= PYKRX_MASS_CALL_THRESHOLD:
            violations.append(f"unexpected PyKRX mass calls ({pykrx_calls}, reason={alpha_reason})")
        if alpha_reused and pykrx_calls >= PYKRX_MASS_CALL_THRESHOLD:
            violations.append(f"pykrx mass calls during alpha_v2 cache reuse ({pykrx_calls})")
        if shadow_flow_exec and shadow_flow_reason not in ALLOWED_STANDARD_SHADOW_FLOW_REFRESH_REASONS:
            violations.append(f"unexpected shadow flow refresh ({shadow_flow_reason})")
        if (
            price_network_fetch
            and not price_cache_hit_safe
            and price_fetch_reason not in ALLOWED_STANDARD_PRICE_REFRESH_REASONS
            and not (price_check_only and price_fetch_reason in ALLOWED_STANDARD_PRICE_CHECK_REASONS)
        ):
            violations.append(f"unexpected price fetch ({price_fetch_reason})")
        if price_write and price_fetch_reason not in ALLOWED_STANDARD_PRICE_REFRESH_REASONS:
            violations.append(f"unexpected price write ({price_fetch_reason})")
        if price_write and not price_hash_match:
            violations.append("price write caused alpha_v2 price_hash drift")
        if not alpha_reused and "prices_changed" in alpha_blockers:
            violations.append("alpha_v2 prices_changed blocked cache reuse")
        if not alpha_reused and "prices_changed" in alpha_blockers and price_hash_match:
            violations.append("alpha_v2 prices_changed blocker despite unchanged price subset")
        if kosis_exec and not kosis_dep_changed and str(getattr(profiler, "kosis_refresh_skip_reason", "") or "") == "":
            allowed_reasons.append("kosis_allowed: dependency_changed_or_first_run")
        if alpha_reason == "input_hash_unchanged" or bool(getattr(profiler, "alpha_v2_reused_from_cache", False)):
            allowed_reasons.append("alpha_v2_reused")
        if flow_reason in {"investor_flows_unchanged", "flow_timeseries_unchanged", "shadow_flow_cache_reuse"}:
            allowed_reasons.append("flow_reused")
        if shadow_flow_reason == "alpha_v2_cache_reuse":
            allowed_reasons.append("shadow_flow_reused")
        if price_cache_hit_safe:
            allowed_reasons.append("price_cache_hit")
        if price_check_only and price_fetch_reason in ALLOWED_STANDARD_PRICE_CHECK_REASONS:
            allowed_reasons.append(f"price_check:{price_fetch_reason}")

    if run_mode == "deep":
        allowed_reasons.extend(["full_alpha_v2", "full_flow_refresh", "kosdaq_sync_allowed"])

    if run_mode == "bundle_only":
        if alpha_full or flow_full or pykrx_calls > 0:
            violations.append("bundle_only must not recompute alpha/flow")

    doc = {
        "schema_version": "1.0",
        "run_mode": run_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not violations,
        "violations": violations,
        "pykrx_call_count": pykrx_calls,
        "alpha_v2_full_refresh_executed": alpha_full,
        "alpha_v2_reused_from_cache": bool(getattr(profiler, "alpha_v2_reused_from_cache", False)) if profiler else False,
        "alpha_v2_refresh_reason": alpha_reason,
        "flow_refresh_executed": bool(getattr(profiler, "flow_refresh_executed", False)) if profiler else False,
        "flow_full_refresh_executed": flow_full,
        "flow_refresh_reason": flow_reason,
        "flow_cache_hit_count": int(getattr(profiler, "flow_cache_hit_count", 0) or 0) if profiler else 0,
        "flow_cache_miss_count": int(getattr(profiler, "flow_cache_miss_count", 0) or 0) if profiler else 0,
        "kosdaq_sync_executed": bool(kosdaq_sync),
        "kosis_refresh_executed": kosis_exec,
        "kosis_dependency_hash_changed": kosis_dep_changed,
        "shadow_flow_refresh_executed": shadow_flow_exec,
        "shadow_flow_reused_from_cache": bool(getattr(profiler, "shadow_flow_reused_from_cache", False)) if profiler else False,
        "shadow_flow_refresh_reason": shadow_flow_reason,
        "price_fetch_executed": price_fetch,
        "price_write_executed": price_write,
        "price_fetch_reason": price_fetch_reason,
        "price_hash_match": price_hash_match,
        "price_check_only": price_check_only,
        "price_network_fetch_executed": price_network_fetch,
        "price_contract_reason": price_contract_reason,
        "allowed_price_check_reason": allowed_price_check_reason,
        "allowed_reasons": allowed_reasons,
        "recommended_fix": (
            "No violations — standard cache-first contract satisfied."
            if not violations
            else "Review refresh triggers; ensure standard uses cache-first when inputs unchanged."
        ),
    }
    return doc


def write_run_mode_contract_validation(output_dir: Path, doc: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / CONTRACT_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
