"""Run-mode hooks — KOSDAQ sync, flow refresh policy."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.runtime.profiler import RuntimeProfiler
from src.runtime.run_mode import RunModeConfig


def run_deep_data_hooks(
    data_dir: Path,
    output_dir: Path,
    cfg: RunModeConfig,
    *,
    as_of: str,
    profiler: RuntimeProfiler | None = None,
) -> dict[str, Any]:
    """Optional pre-pipeline refresh steps for deep / cache-first modes."""
    meta: dict[str, Any] = {"kosdaq_sync": None, "flow_refresh": None}

    if cfg.kosdaq_universe_sync:
        with _prof_step(profiler, "kosdaq_universe_sync"):
            try:
                from src.data_refresh.pykrx_bulk import run_kosdaq_universe_sync

                meta["kosdaq_sync"] = run_kosdaq_universe_sync(data_dir, as_of=as_of[:10])
                if profiler:
                    profiler.kosdaq_sync_executed = True
                    profiler.record_cache_miss()
            except Exception as exc:
                meta["kosdaq_sync"] = {"error": str(exc)}
                if profiler:
                    profiler.add_note(f"kosdaq_universe_sync failed: {exc}")

    if cfg.flow_refresh_mode in {"cache_first", "full"} and cfg.run_flow_dashboard:
        with _prof_step(profiler, "flow_dashboard"):
            meta["flow_refresh"] = _run_flow_refresh_policy(
                data_dir,
                output_dir,
                as_of=as_of,
                mode=cfg.flow_refresh_mode,
                profiler=profiler,
            )

    return meta


def _prof_step(profiler: RuntimeProfiler | None, name: str):
    if profiler is not None:
        return profiler.step(name)
    from contextlib import nullcontext

    return nullcontext()


def _run_flow_refresh_policy(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    mode: str,
    profiler: RuntimeProfiler | None,
) -> dict[str, Any]:
    from src.runtime.run_mode_contract import (
        _record_flow_run,
        _record_flow_skip,
        investor_flows_covers_as_of,
    )

    use_cache = mode != "full"
    if mode == "cache_first" and investor_flows_covers_as_of(data_dir, as_of[:10]):
        _record_flow_skip(profiler, "investor_flows_unchanged")
        return {"skipped": True, "reason": "investor_flows_unchanged", "mode": mode}
    try:
        from src.alpha.flow_refresh import run_flow_refresh
        from src.alpha_v2_gate import resolve_watched_universe_tickers

        tickers = resolve_watched_universe_tickers(data_dir, output_dir, max_tickers=80)
        if not tickers:
            return {"skipped": True, "reason": "no watched tickers"}

        result = run_flow_refresh(
            data_dir,
            output_dir,
            as_of=as_of[:10],
            tickers=tickers,
            use_cache=use_cache,
        )
        if profiler:
            profiler.record_cache_hit(int(result.cache_hit_count or 0))
            profiler.record_cache_miss(int(result.cache_miss_count or 0))
            for _ in range(int(result.pykrx_call_count or 0)):
                profiler.record_pykrx_call()
            for tk in result.failed_tickers or []:
                profiler.record_pykrx_failure(str(tk))
        _record_flow_run(
            profiler,
            executed=True,
            reason="cache_miss" if result.pykrx_call_count else "cache_hit",
            full_refresh=not use_cache,
            cache_hits=int(result.cache_hit_count or 0),
            cache_misses=int(result.cache_miss_count or 0),
        )
        if not use_cache and profiler:
            profiler.add_note("flow refresh: full mode (cache bypass for investor_flows)")
        return {
            "mode": mode,
            "use_cache": use_cache,
            "refreshed_count": result.refreshed_count,
            "cache_hit_count": result.cache_hit_count,
            "cache_miss_count": result.cache_miss_count,
            "pykrx_call_count": result.pykrx_call_count,
        }
    except Exception as exc:
        if profiler:
            profiler.add_note(f"flow refresh hook failed: {exc}")
        return {"error": str(exc), "mode": mode}
