"""Common Flow API — load, stale policy, streaks, dashboard inputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.alpha.investor_flows import load_investor_flows
from src.alpha_flow.flow_classifier import (
    STALE_STALENESS_DAYS_THRESHOLD,
    apply_execution_gates,
    apply_stale_policy,
    classify_flow_state,
    count_fresh_stale,
    is_flow_record_stale,
)
from src.alpha_flow.flow_cache import load_cached_flow_row, read_flow_cache_meta


@dataclass
class FlowDashboardInputs:
    as_of: str
    flow_records: dict[str, dict[str, Any]]
    institutional: dict[str, Any]
    execution_context: dict[str, Any]
    freshness: dict[str, int]
    cache_meta: dict[str, Any]
    warnings: list[str]


def load_flow_data(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Unified investor flow rows with normalized stale_flag."""
    raw = load_investor_flows(data_dir)
    out: dict[str, dict[str, Any]] = {}
    for ticker, rec in raw.items():
        row = dict(rec)
        row["stale_flag"] = is_flow_record_stale(row)
        row["ticker"] = str(ticker).zfill(6)
        out[str(ticker).zfill(6)] = apply_stale_policy(row)
    return out


def load_institutional_flow_map(data_dir: Path) -> dict[str, Any]:
    """InstitutionalFlowRow map via shared stale classifier."""
    from src.alpha_v2.institutional_flow_loader import load_institutional_flows

    return load_institutional_flows(data_dir)


def load_daily_flow_timeseries(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    max_tickers: int = 80,
) -> list[dict[str, Any]]:
    from src.alpha_flow.flow_analytics import run_flow_dashboard_outputs

    result = run_flow_dashboard_outputs(
        data_dir, output_dir, as_of=as_of, max_tickers=max_tickers,
    )
    path = output_dir / "flow_daily_timeseries.csv"
    if not path.exists():
        return []
    import pandas as pd

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.to_dict(orient="records")


def calculate_flow_to_market_cap(net_amount: float | None, market_cap: float | None) -> float | None:
    if net_amount is None or market_cap is None or market_cap <= 0:
        return None
    return net_amount / market_cap


def calculate_flow_to_turnover(net_amount: float | None, turnover: float | None) -> float | None:
    if net_amount is None or turnover is None or turnover <= 0:
        return None
    return net_amount / turnover


def calculate_streaks(amounts: list[float], direction: str) -> int:
    from src.alpha_flow.flow_analytics import consecutive_days

    return consecutive_days(amounts, direction)


def build_flow_coverage_meta(
    records: list[dict[str, Any]],
    *,
    as_of: str,
    data_dir: Path | None = None,
    source: str = "alpha_flow",
    cache_hit_count: int = 0,
    cache_miss_count: int = 0,
    pykrx_call_count: int = 0,
    pykrx_failed_tickers: list[str] | None = None,
    stale_reason_summary: dict[str, int] | None = None,
    last_successful_flow_refresh: str = "",
    coverage_scope: str = "watched_universe",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    from src.alpha_flow.flow_classifier import summarize_stale_reasons

    counts = count_fresh_stale(records)
    total = counts["total_flow_count"]
    stale = counts["stale_flow_count"]
    fresh = counts["fresh_flow_count"]
    cache_meta = read_flow_cache_meta(data_dir) if data_dir else {}
    reasons = stale_reason_summary or summarize_stale_reasons([
        "fresh" if not is_flow_record_stale(r) else "flow_signal_stale" for r in records
    ])
    return {
        "as_of": as_of[:10],
        "source": source,
        "coverage_scope": coverage_scope,
        "stale_threshold_days": STALE_STALENESS_DAYS_THRESHOLD,
        "fresh_flow_count": fresh,
        "stale_flow_count": stale,
        "fresh_count": fresh,
        "stale_count": stale,
        "total_flow_count": total,
        "fresh_ratio": round(fresh / total, 4) if total else 0.0,
        "stale_ratio": round(stale / total, 4) if total else 0.0,
        "cache_hit_count": cache_hit_count,
        "cache_miss_count": cache_miss_count,
        "pykrx_call_count": pykrx_call_count,
        "pykrx_failed_tickers": pykrx_failed_tickers or [],
        "pykrx_failed_ticker_count": len(pykrx_failed_tickers or []),
        "stale_reason_summary": reasons,
        "last_successful_flow_refresh": last_successful_flow_refresh or f"{as_of[:10]}T00:00:00+09:00",
        "cache_files": cache_meta.get("cache_files", 0),
        "warnings": (warnings or [])[:20],
        "policy": "stale flow → no Buy/Trim Watch; LOW confidence warning only",
    }


def get_flow_dashboard_inputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
) -> FlowDashboardInputs:
    from src.alpha_flow.dashboard_data import load_execution_context

    ctx = load_execution_context(output_dir)
    flows = load_flow_data(data_dir)
    institutional = load_institutional_flow_map(data_dir)
    records = list(flows.values())
    freshness = count_fresh_stale(records)
    dash_summary_path = output_dir / "flow_dashboard_summary.json"
    warnings: list[str] = []
    cache_meta = read_flow_cache_meta(data_dir)
    resolved_as_of = as_of or ""
    if dash_summary_path.exists():
        import json

        try:
            dash = json.loads(dash_summary_path.read_text(encoding="utf-8"))
            resolved_as_of = resolved_as_of or str(dash.get("as_of") or "")
            warnings = list(dash.get("warnings") or [])
            if dash.get("cache_meta"):
                cache_meta = {**cache_meta, **dash["cache_meta"]}
        except (json.JSONDecodeError, OSError):
            pass
    if not resolved_as_of:
        resolved_as_of = str(list(flows.values())[0].get("date", "")) if flows else ""

    return FlowDashboardInputs(
        as_of=resolved_as_of,
        flow_records=flows,
        institutional=institutional,
        execution_context=ctx,
        freshness=freshness,
        cache_meta=cache_meta,
        warnings=warnings,
    )


def get_flow_for_ticker_unified(data_dir: Path, ticker: str) -> dict[str, Any]:
    """v1 Signal Board read path — classifier stale; decision logic unchanged downstream."""
    flows = load_flow_data(data_dir)
    tk = str(ticker).zfill(6)
    if tk in flows:
        return flows[tk]
    return apply_stale_policy({
        "ticker": tk,
        "flow_signal": "STALE",
        "flow_score": 0.0,
        "staleness_days": 999,
        "source": "missing",
        "stale_flag": True,
    })


__all__ = [
    "FlowDashboardInputs",
    "apply_execution_gates",
    "apply_stale_policy",
    "build_flow_coverage_meta",
    "calculate_flow_to_market_cap",
    "calculate_flow_to_turnover",
    "calculate_streaks",
    "classify_flow_state",
    "count_fresh_stale",
    "get_flow_dashboard_inputs",
    "get_flow_for_ticker_unified",
    "load_daily_flow_timeseries",
    "load_flow_data",
    "load_institutional_flow_map",
    "load_cached_flow_row",
    "is_flow_record_stale",
]
