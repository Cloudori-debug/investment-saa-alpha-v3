"""Alpha v2 / alpha_flow feature gate (cleanup phase 2).

ENABLE_ALPHA_V2=False by default after archive. Set env ENABLE_ALPHA_V2=1 to
re-enable when src.alpha_v2 / src.alpha_flow are restored from archive/.
Stubs keep kr_alpha price fetch, signal-board flow reads, and report headers
visible as intentionally disabled (same pattern as hakedaka_gate).
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

# Cleanup phase 2 default — packages live under archive/20260715_alpha_v2|alpha_flow.
ENABLE_ALPHA_V2 = False

_DISABLED_NOTE = (
    "Alpha v2 / Flow dashboard disabled "
    "(ENABLE_ALPHA_V2=False / alpha_v2·alpha_flow archived)."
)

# Contract reason sets (formerly in alpha_v2 / alpha_flow) — kept for run_mode_contract.
ALLOWED_STANDARD_REFRESH_REASONS: frozenset[str] = frozenset({
    "no_previous_alpha_v2_cache",
    "required_outputs_missing",
    "input_hash_changed",
    "as_of_not_covered",
    "explicit_user_force_refresh",
    "deep_force_refresh",
    "previous_run_failed",
})

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

ALLOWED_STANDARD_SHADOW_FLOW_REFRESH_REASONS: frozenset[str] = frozenset({
    "no_previous_flow_cache",
    "flow_required_outputs_missing",
    "flow_hash_changed",
    "flow_as_of_not_covered",
    "explicit_user_force_refresh",
    "deep_force_refresh",
    "alpha_v2_full_refresh",
})

FLOW_UI_POLICY_LINES: list[str] = [
    _DISABLED_NOTE,
    "수급 신호는 매수 허가가 아닙니다.",
    "Actual Buy Allowed=0이면 모든 Buy Watch는 관찰 신호입니다.",
    "NO_TRADE 상태에서는 모든 수급 신호가 review-only입니다.",
]

STALE_STALENESS_DAYS_THRESHOLD = 3
_STALE_SOURCES = frozenset({"template", "missing"})
_STALE_FLOW_SIGNAL = "STALE"


def alpha_v2_enabled() -> bool:
    env = str(os.environ.get("ENABLE_ALPHA_V2", "")).strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    if env in {"0", "false", "no", "off"}:
        return False
    return bool(ENABLE_ALPHA_V2)


def _try_import(package: str, mod: str):
    if not alpha_v2_enabled():
        return None
    try:
        import importlib

        return importlib.import_module(f"src.{package}.{mod}")
    except ImportError:
        return None


# --- flow classifier helpers (needed by src/alpha even when packages archived) ---

def _truthy(val: Any) -> bool:
    return str(val).lower() in {"true", "1", "yes"}


def is_flow_record_stale(rec: dict[str, Any] | None) -> bool:
    real = _try_import("alpha_flow", "flow_classifier")
    if real is not None:
        return bool(real.is_flow_record_stale(rec))
    if not rec:
        return True
    if _truthy(rec.get("stale_flag")) or _truthy(rec.get("flow_data_stale")):
        return True
    if str(rec.get("flow_signal_state") or "").lower() == "stale":
        return True
    if str(rec.get("flow_signal") or "") == _STALE_FLOW_SIGNAL:
        return True
    try:
        if int(rec.get("staleness_days") or 0) >= STALE_STALENESS_DAYS_THRESHOLD:
            return True
    except (TypeError, ValueError):
        return True
    if "source" in rec and str(rec.get("source") or "").strip().lower() in _STALE_SOURCES:
        return True
    return False


def classify_stale_reason(
    rec: dict[str, Any] | None,
    *,
    ticker: str = "",
    pykrx_failed: bool = False,
    parse_error: bool = False,
) -> str:
    real = _try_import("alpha_flow", "flow_classifier")
    if real is not None:
        return str(
            real.classify_stale_reason(
                rec, ticker=ticker, pykrx_failed=pykrx_failed, parse_error=parse_error,
            )
        )
    if parse_error:
        return "parse_error"
    if pykrx_failed:
        return "pykrx_fetch_failed"
    if not rec:
        return "source_missing"
    src = str(rec.get("source") or "").strip().lower()
    if src in {"missing", "template", ""}:
        return "source_missing"
    if not str(rec.get("date") or "").strip():
        return "date_missing"
    if str(rec.get("flow_signal") or "") == _STALE_FLOW_SIGNAL:
        return "cache_too_old" if src == "cache_stale" else "flow_signal_stale"
    try:
        if int(rec.get("staleness_days") or 0) >= STALE_STALENESS_DAYS_THRESHOLD:
            return "cache_too_old"
    except (TypeError, ValueError):
        return "parse_error"
    if is_flow_record_stale(rec):
        return "flow_signal_stale"
    return "fresh"


def summarize_stale_reasons(reasons: list[str]) -> dict[str, int]:
    real = _try_import("alpha_flow", "flow_classifier")
    if real is not None:
        return dict(real.summarize_stale_reasons(reasons))
    summary: dict[str, int] = {}
    for r in reasons:
        summary[r] = summary.get(r, 0) + 1
    return summary


def get_flow_for_ticker_unified(data_dir: Path, ticker: str) -> dict[str, Any]:
    real = _try_import("alpha_flow", "flow_service")
    if real is not None:
        return real.get_flow_for_ticker_unified(data_dir, ticker)
    from src.alpha.investor_flows import get_flow_for_ticker as legacy_get_flow

    return legacy_get_flow(data_dir, ticker)


def resolve_watched_universe_tickers(
    data_dir: Path,
    output_dir: Path,
    *,
    max_tickers: int = 80,
    scored_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    real = _try_import("alpha_flow", "watched_universe")
    if real is not None:
        return real.resolve_watched_universe_tickers(
            data_dir, output_dir, max_tickers=max_tickers, scored_rows=scored_rows,
        )
    merged: dict[str, dict[str, str]] = {}

    def _merge(tk: str, name: str = "") -> None:
        t = str(tk).strip()
        t = t.zfill(6) if t.isdigit() else t
        if not t or t.upper() == "CASH":
            return
        merged.setdefault(t, {"ticker": t, "name": name or t})
        if name:
            merged[t]["name"] = name

    try:
        from src.data_loader import load_positions, load_target_portfolio

        for row in load_positions(data_dir / "positions.csv"):
            if float(row.quantity or 0) > 0 and row.asset_group == "kr_alpha":
                _merge(row.ticker, row.name or "")
        for row in load_target_portfolio(data_dir / "target_portfolio.csv"):
            if row.asset_group == "kr_alpha":
                _merge(row.ticker, row.name or "")
    except Exception:
        pass

    for fname in ("alpha_signal_board.csv", "alpha_candidates.csv", "alpha_top10_scored.csv"):
        path = output_dir / fname
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                _merge(row.get("ticker", ""), str(row.get("name") or ""))
                if len(merged) >= max_tickers:
                    break
        if len(merged) >= max_tickers:
            break

    return list(merged.values())[:max_tickers]


# --- price / snapshot (pipeline) ---

def evaluate_standard_price_fetch(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_mode: Any,
    force_refresh: bool = False,
) -> tuple[bool, str]:
    """Return (should_skip_fetch, reason). Disabled → never skip (kr_alpha still fetches)."""
    real = _try_import("alpha_v2", "price_fetch_policy")
    if real is not None:
        return real.evaluate_standard_price_fetch(
            data_dir, output_dir, as_of=as_of, run_mode=run_mode, force_refresh=force_refresh,
        )
    return False, "alpha_v2_disabled"


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
    real = _try_import("alpha_v2", "price_fetch_policy")
    if real is not None:
        return real.maybe_refresh_tier_prices_before_alpha(
            data_dir,
            output_dir,
            as_of=as_of,
            run_mode=run_mode,
            profiler=profiler,
            force_refresh=force_refresh,
            run_id=run_id,
            step_runner=step_runner,
        )
    return {"skipped": True, "reason": "alpha_v2_disabled", "price_fetch_executed": False}


def write_pipeline_input_snapshot(
    output_dir: Path,
    data_dir: Path,
    *,
    as_of: str,
    run_id: str = "",
) -> Path | None:
    real = _try_import("alpha_v2", "cache_decision")
    if real is not None:
        return real.write_pipeline_input_snapshot(
            output_dir, data_dir, as_of=as_of, run_id=run_id,
        )
    return None


def commit_pipeline_input_snapshot(
    output_dir: Path,
    data_dir: Path,
    *,
    as_of: str,
    run_id: str = "",
) -> Path | None:
    real = _try_import("alpha_v2", "cache_decision")
    if real is not None:
        return real.commit_pipeline_input_snapshot(
            output_dir, data_dir, as_of=as_of, run_id=run_id,
        )
    return None


def load_committed_pipeline_input_snapshot(output_dir: Path) -> dict[str, Any]:
    real = _try_import("alpha_v2", "cache_decision")
    if real is not None:
        return real.load_committed_pipeline_input_snapshot(output_dir)
    return {}


# --- shadow runners ---

def run_alpha_v2_shadow(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    real = _try_import("alpha_v2", "pipeline")
    if real is not None:
        return real.run_alpha_v2_shadow(*args, **kwargs)
    return None


def maybe_run_shadow_flow_dashboard(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    real = _try_import("alpha_flow", "shadow_flow_cache")
    if real is not None:
        return real.maybe_run_shadow_flow_dashboard(*args, **kwargs)
    return None


# --- report / export ---

def build_daily_report_alpha_v2_section(output_dir: Path) -> list[str]:
    real = _try_import("alpha_v2", "export_alpha_v2")
    if real is not None:
        return real.build_daily_report_alpha_v2_section(output_dir)
    return [
        "## Alpha v2 Shadow (review-only)",
        "",
        f"- {_DISABLED_NOTE}",
        "",
    ]


def build_daily_report_flow_section(output_dir: Path) -> list[str]:
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.build_daily_report_flow_section(output_dir)
    return [
        "## Alpha 수급 현황 (review-only)",
        "",
        f"- {_DISABLED_NOTE}",
        "",
    ]


def build_alpha_v2_export_sections(output_dir: Path) -> dict[str, Any]:
    real = _try_import("alpha_v2", "export_alpha_v2")
    if real is not None:
        return real.build_alpha_v2_export_sections(output_dir)
    return {
        "alpha_v2_coverage": {"enabled": False, "note": _DISABLED_NOTE},
        "alpha_v2_policy_notes": [_DISABLED_NOTE],
    }


# --- UI dashboard stubs ---

def _empty_df():
    import pandas as pd

    return pd.DataFrame()


def build_holdings_target_flow_table(data_dir: Path, output_dir: Path):
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.build_holdings_target_flow_table(data_dir, output_dir)
    return _empty_df()


def build_v2_candidate_flow_table(output_dir: Path):
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.build_v2_candidate_flow_table(output_dir)
    return _empty_df()


def compute_dashboard_cards(output_dir: Path) -> dict[str, Any]:
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.compute_dashboard_cards(output_dir)
    return {
        "fresh_flow_count": 0,
        "stale_flow_count": 0,
        "buy_watch_count": 0,
        "trim_watch_count": 0,
        "actual_buy_allowed": 0,
        "no_trade": True,
        "note": _DISABLED_NOTE,
    }


def load_freshness_summary(output_dir: Path) -> dict[str, Any]:
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.load_freshness_summary(output_dir)
    return {"actual_consecutive_days_available": False, "note": _DISABLED_NOTE}


def load_leaderboard_tables(output_dir: Path) -> dict[str, Any]:
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.load_leaderboard_tables(output_dir)
    return {}


def load_streaks_table(output_dir: Path):
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.load_streaks_table(output_dir)
    return _empty_df()


def load_trim_watch_tables(output_dir: Path) -> tuple[Any, Any]:
    real = _try_import("alpha_flow", "dashboard_data")
    if real is not None:
        return real.load_trim_watch_tables(output_dir)
    return _empty_df(), _empty_df()
