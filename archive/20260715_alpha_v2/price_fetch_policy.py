"""P1.6e — standard/deep/quick tier price refresh policy before alpha_v2."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.alpha_v2.cache_decision import load_committed_pipeline_input_snapshot
from src.alpha_v2.input_hash import (
    check_alpha_v2_price_coverage,
    compare_price_subset_drift,
    compute_prices_as_of_hash,
    write_price_hash_drift_debug,
)
from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash

ALLOWED_STANDARD_PRICE_REFRESH_REASONS: frozenset[str] = frozenset({
    "no_price_cache",
    "price_coverage_missing",
    "market_date_changed",
    "alpha_v2_universe_changed",
    "explicit_user_force_refresh",
    "deep_force_refresh",
    "price_hash_changed",
    "pytest_skip",
    "price_refresh_required",
})

ALLOWED_STANDARD_PRICE_CHECK_REASONS: frozenset[str] = frozenset({
    "coverage_check_only",
    "price_hash_unchanged",
    "no_write_no_network",
    "subset_unchanged",
    "quick_price_refresh_forbidden",
})


def _run_mode_value(run_mode: Any) -> str:
    if hasattr(run_mode, "value"):
        return str(run_mode.value).lower()
    return str(run_mode or "standard").lower()


def evaluate_standard_price_fetch(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_mode: Any,
    force_refresh: bool = False,
) -> tuple[bool, str]:
    """Return (should_skip_fetch, reason)."""
    mode = _run_mode_value(run_mode)
    as_of_s = as_of[:10]

    if mode == "quick":
        return True, "quick_price_refresh_forbidden"
    if force_refresh:
        return False, "explicit_user_force_refresh"
    if mode == "deep":
        return False, "deep_force_refresh"

    committed = load_committed_pipeline_input_snapshot(output_dir)
    if not committed:
        return False, "no_price_cache"

    committed_date = str(committed.get("as_of") or "")
    if committed_date and committed_date != as_of_s:
        return False, "market_date_changed"

    committed_universe = str(committed.get("universe_hash") or "")
    current_universe = compute_semantic_file_hash(data_dir / "universe.csv")
    if committed_universe and current_universe != committed_universe:
        return False, "alpha_v2_universe_changed"

    committed_hash = str(committed.get("price_hash") or "")
    current_hash = compute_prices_as_of_hash(data_dir, as_of_s)
    if committed_hash and committed_hash == current_hash:
        return True, "price_hash_unchanged"

    coverage = check_alpha_v2_price_coverage(data_dir, as_of_s)
    if not coverage["covered"]:
        return False, "price_coverage_missing"

    return False, "price_hash_changed"


def maybe_refresh_tier_prices_before_alpha(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_mode: Any,
    profiler: Any | None = None,
    force_refresh: bool = False,
    run_id: str = "",
    step_runner: Any | None = None,
) -> dict[str, Any]:
    """Run tier_b/tier_a only when policy allows; emit drift debug artifact."""
    mode = _run_mode_value(run_mode)
    as_of_s = as_of[:10]
    skip_fetch, reason = evaluate_standard_price_fetch(
        data_dir,
        output_dir,
        as_of=as_of_s,
        run_mode=run_mode,
        force_refresh=force_refresh,
    )

    committed = load_committed_pipeline_input_snapshot(output_dir)
    previous_hash = str(committed.get("price_hash") or "")
    drift_before = compare_price_subset_drift(
        data_dir,
        as_of_s,
        previous_hash=previous_hash,
    )

    price_fetch_executed = False
    price_write_executed = False
    price_network_fetch_executed = False
    price_check_only = False
    tier_b_result: dict[str, Any] | None = None
    tier_a_result: dict[str, Any] | None = None
    fetch_reason = reason

    if os.environ.get("PYTEST_CURRENT_TEST") is not None:
        skip_fetch = True
        fetch_reason = "pytest_skip"

    if mode == "quick":
        skip_fetch = True
        fetch_reason = "quick_price_refresh_forbidden"

    if skip_fetch:
        if step_runner is not None and hasattr(step_runner, "record_skip"):
            cache_hit = fetch_reason == "price_hash_unchanged"
            step_runner.record_skip(
                "tier_b_refresh",
                fetch_reason,
                cache_hit=cache_hit and mode == "standard",
                cache_source=fetch_reason if cache_hit else "",
            )
            step_runner.record_skip(
                "tier_a_refresh",
                fetch_reason,
                cache_hit=cache_hit,
                cache_source=fetch_reason if cache_hit else "",
            )
        if profiler is not None and hasattr(profiler, "add_note"):
            profiler.add_note(f"Tier price fetch skipped ({fetch_reason})")
    else:
        price_network_fetch_executed = True
        price_fetch_executed = True
        if mode == "standard":
            from src.data_refresh.tier_b_refresh import run_tier_b_if_due

            def _tier_b() -> None:
                nonlocal tier_b_result, price_write_executed
                tb = run_tier_b_if_due(data_dir, as_of=as_of_s)
                tier_b_result = {"ran": tb.ran, "reason": tb.reason, "prices_count": tb.prices_count}
                if tb.ran:
                    price_write_executed = True

            if step_runner is not None and hasattr(step_runner, "step"):
                with step_runner.step("tier_b_refresh"):
                    _tier_b()
            else:
                _tier_b()
        elif step_runner is not None and hasattr(step_runner, "record_skip"):
            step_runner.record_skip("tier_b_refresh", "deep_mode_tier_b_deferred")

        from src.data_refresh.prices_refresh import ensure_tier_a_prices
        from src.runtime.run_mode import RunMode

        refresh_existing = mode == "deep" or getattr(run_mode, "value", run_mode) == RunMode.DEEP

        def _tier_a() -> None:
            nonlocal tier_a_result, price_write_executed
            tier_a = ensure_tier_a_prices(
                data_dir,
                as_of_s,
                output_dir=output_dir,
                top_n=50,
                refresh_existing=refresh_existing,
            )
            tier_a_result = {
                "added": list(tier_a.added),
                "failed": list(tier_a.failed),
                "required_count": tier_a.required_count,
            }
            if tier_a.added:
                price_write_executed = True

        if step_runner is not None and hasattr(step_runner, "step"):
            with step_runner.step("tier_a_refresh"):
                _tier_a()
        else:
            _tier_a()

        if not price_write_executed and drift_before.get("price_hash_match"):
            price_fetch_executed = False
            price_network_fetch_executed = False
            price_check_only = True
            fetch_reason = (
                "coverage_check_only"
                if reason == "price_coverage_missing"
                else "no_write_no_network"
            )
        elif not price_write_executed:
            fetch_reason = "price_refresh_required"
        else:
            fetch_reason = (
                "deep_force_refresh" if mode == "deep" else "price_refresh_required"
            )

    drift_after = compare_price_subset_drift(
        data_dir,
        as_of_s,
        previous_hash=previous_hash,
    )
    drift_doc = {
        "market_date": as_of_s,
        "alpha_v2_universe_count": drift_after.get("alpha_v2_universe_count", 0),
        "previous_price_hash": previous_hash,
        "current_price_hash": drift_after.get("current_price_hash", ""),
        "price_hash_match": drift_after.get("price_hash_match", False),
        "changed_tickers": drift_after.get("changed_tickers", []),
        "changed_dates": drift_after.get("changed_dates", []),
        "missing_tickers": drift_after.get("missing_tickers", []),
        "extra_tickers_ignored": drift_after.get("extra_tickers_ignored", []),
        "unrelated_rows_ignored": drift_after.get("unrelated_rows_ignored", 0),
        "price_fetch_executed": price_fetch_executed,
        "price_write_executed": price_write_executed,
        "price_network_fetch_executed": price_network_fetch_executed,
        "price_check_only": price_check_only,
        "price_fetch_reason": fetch_reason,
        "tier_b": tier_b_result,
        "tier_a": tier_a_result,
        "pre_fetch_drift": {
            "price_hash_match": drift_before.get("price_hash_match", False),
            "current_price_hash": drift_before.get("current_price_hash", ""),
        },
    }
    write_price_hash_drift_debug(
        output_dir,
        drift_doc,
        run_id=run_id,
        run_mode=mode,
    )

    if profiler is not None:
        for key, val in (
            ("price_fetch_executed", price_fetch_executed),
            ("price_write_executed", price_write_executed),
            ("price_network_fetch_executed", price_network_fetch_executed),
            ("price_check_only", price_check_only),
            ("price_fetch_reason", drift_doc["price_fetch_reason"]),
            ("price_hash_match", bool(drift_after.get("price_hash_match"))),
            ("price_hash_current", str(drift_after.get("current_price_hash") or "")),
            ("price_hash_previous", previous_hash),
            ("price_hash_drift_reason", "subset_unchanged" if drift_after.get("price_hash_match") else ""),
        ):
            if hasattr(profiler, key):
                setattr(profiler, key, val)

    return drift_doc
