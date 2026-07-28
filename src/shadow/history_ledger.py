"""Shadow history ledger — Alpha v2 / Flow Dashboard review-only accumulation."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.benchmark_data import load_combined_prices
from src.alpha_v2_gate import classify_stale_reason, is_flow_record_stale
from src.decision.shadow_performance import _pct_change, _row_on_or_before, add_business_days

HISTORY_SUBDIR = "history"

ALPHA_V2_SHADOW_FIELDS = [
    "run_id", "run_date", "ticker", "name", "market", "tier", "grade",
    "total_score", "q_score", "v_score", "m_score", "flow_score",
    "pension_flow_score", "foreign_flow_score", "flow_signal_state",
    "buy_watch", "trim_watch", "buy_permission", "review_only",
    "is_kosdaq", "is_final_candidate", "is_top30",
    "actual_buy_allowed", "execution_scope",
]

FLOW_DASHBOARD_FIELDS = [
    "run_id", "run_date", "ticker", "name", "market",
    "pension_net_buy_1d", "pension_net_buy_5d", "pension_net_buy_20d",
    "foreign_net_buy_1d", "foreign_net_buy_5d", "foreign_net_buy_20d",
    "pension_streak_direction", "pension_streak_days",
    "foreign_streak_direction", "foreign_streak_days",
    "co_buy_signal", "co_sell_signal", "flow_signal_state",
    "fresh_or_stale", "stale_reason", "cache_hit",
    "buy_permission", "review_only",
]

OUTCOME_FIELDS = [
    "run_id", "run_date", "ticker", "name", "signal_source",
    "buy_watch", "trim_watch", "flow_signal_state", "fresh_or_stale", "is_kosdaq",
    "5d_return", "20d_return", "60d_return",
    "max_favorable_excursion", "max_adverse_excursion",
    "outcome_label", "false_positive_flag", "false_negative_flag",
    "evaluation_status", "evaluated_at",
]

DAILY_SUMMARY_FIELDS = [
    "run_id", "run_date",
    "alpha_v2_shadow_history_updated", "flow_dashboard_history_updated",
    "buy_watch_count", "trim_watch_count",
    "trim_watch_held_count", "trim_watch_informational_count",
    "new_kosdaq_candidates_count", "fresh_flow_ratio",
    "watched_ticker_count", "target_write_occurred",
]


def _history_dir(output_dir: Path) -> Path:
    return output_dir / HISTORY_SUBDIR


def _truthy(val: Any) -> bool:
    return str(val).lower() in {"true", "1", "yes"}


def _bool_str(val: Any) -> str:
    return "true" if _truthy(val) else "false"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_csv_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return []
    if df.empty:
        return []
    return [dict(r) for r in df.to_dict(orient="records")]


def _existing_run_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    try:
        df = pd.read_csv(path, usecols=["run_id"], dtype=str)
        return set(df["run_id"].dropna().unique())
    except (ValueError, pd.errors.EmptyDataError):
        return set()


def _append_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _load_trigger_flags(output_dir: Path) -> dict[str, dict[str, str]]:
    flags: dict[str, dict[str, str]] = {}
    for row in _read_csv_records(output_dir / "alpha_v2_flow_triggers.csv"):
        tk = str(row.get("ticker", "")).zfill(6)
        if not tk:
            continue
        flags[tk] = {
            "buy_watch": _bool_str(row.get("buy_watch")),
            "trim_watch": _bool_str(row.get("trim_watch")),
            "buy_permission": _bool_str(row.get("buy_permission")),
            "review_only": _bool_str(row.get("review_only")),
            "flow_signal_state": str(row.get("flow_signal_state") or ""),
        }
    return flags


def _load_set_from_csv(path: Path, col: str = "ticker") -> set[str]:
    return {
        str(r.get(col, "")).zfill(6)
        for r in _read_csv_records(path)
        if r.get(col)
    }


def build_alpha_v2_shadow_rows(
    output_dir: Path,
    *,
    run_id: str,
    run_date: str,
) -> list[dict[str, Any]]:
    scored = _read_csv_records(output_dir / "alpha_v2_scored.csv")
    if not scored:
        return []

    summary = _read_json(output_dir / "alpha_v2_summary.json")
    exec_ctx = summary.get("execution_context") or {}
    actual_buy_allowed = int(exec_ctx.get("actual_buy_allowed") or 0)
    execution_scope = str(exec_ctx.get("execution_scope") or "")
    review_only = _bool_str(
        exec_ctx.get("no_trade") or execution_scope == "NO_TRADE"
    )

    top30 = _load_set_from_csv(output_dir / "alpha_v2_top30.csv")
    final = _load_set_from_csv(output_dir / "alpha_v2_final_candidates.csv")
    triggers = _load_trigger_flags(output_dir)

    rows: list[dict[str, Any]] = []
    for raw in scored:
        tk = str(raw.get("ticker", "")).zfill(6)
        if not tk:
            continue
        market = str(raw.get("market") or "KOSPI")
        trig = triggers.get(tk, {})
        buy_watch = trig.get("buy_watch") or _bool_str(raw.get("buy_watch"))
        trim_watch = trig.get("trim_watch") or _bool_str(raw.get("trim_watch"))
        buy_perm = trig.get("buy_permission") or _bool_str(
            actual_buy_allowed > 0 and not _truthy(review_only)
        )
        rows.append({
            "run_id": run_id,
            "run_date": run_date[:10],
            "ticker": tk,
            "name": raw.get("name", tk),
            "market": market,
            "tier": raw.get("tier", ""),
            "grade": raw.get("grade", ""),
            "total_score": raw.get("total_score_v2_shadow") or raw.get("total_score", ""),
            "q_score": raw.get("quality_score", ""),
            "v_score": raw.get("valuation_score", ""),
            "m_score": raw.get("momentum_score", ""),
            "flow_score": raw.get("flow_score", ""),
            "pension_flow_score": raw.get("pension_rank_20d", ""),
            "foreign_flow_score": raw.get("foreign_rank_20d", ""),
            "flow_signal_state": trig.get("flow_signal_state") or raw.get("flow_signal_state", ""),
            "buy_watch": buy_watch,
            "trim_watch": trim_watch,
            "buy_permission": buy_perm,
            "review_only": trig.get("review_only") or review_only,
            "is_kosdaq": _bool_str(market.upper() == "KOSDAQ"),
            "is_final_candidate": _bool_str(tk in final),
            "is_top30": _bool_str(tk in top30),
            "actual_buy_allowed": actual_buy_allowed,
            "execution_scope": execution_scope,
        })
    return rows


def _sum_window(df: pd.DataFrame, col: str, days: int) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    series = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return float(series.tail(days).sum())


def build_flow_dashboard_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    run_date: str,
) -> list[dict[str, Any]]:
    ts_path = output_dir / "flow_daily_timeseries.csv"
    streak_path = output_dir / "flow_streaks.csv"
    if not ts_path.exists() or not streak_path.exists():
        return []

    ts_df = pd.read_csv(ts_path, dtype=str, keep_default_na=False)
    streak_df = pd.read_csv(streak_path, dtype=str, keep_default_na=False)
    if ts_df.empty or streak_df.empty:
        return []

    summary = _read_json(output_dir / "alpha_v2_summary.json")
    exec_ctx = summary.get("execution_context") or {}
    actual_buy_allowed = int(exec_ctx.get("actual_buy_allowed") or 0)
    execution_scope = str(exec_ctx.get("execution_scope") or "")
    review_only = _bool_str(
        exec_ctx.get("no_trade") or execution_scope == "NO_TRADE"
    )
    triggers = _load_trigger_flags(output_dir)

    from src.alpha.investor_flows import load_investor_flows

    flows = load_investor_flows(data_dir)
    cache_dir = data_dir / "cache" / "flow_refresh"

    rows: list[dict[str, Any]] = []
    for _, srow in streak_df.iterrows():
        tk = str(srow.get("ticker", "")).zfill(6)
        if not tk:
            continue
        grp = ts_df[ts_df["ticker"].astype(str).str.zfill(6) == tk].sort_values("date")
        flow_rec = flows.get(tk)
        stale = is_flow_record_stale(flow_rec) if flow_rec else True
        stale_reason = classify_stale_reason(flow_rec) if flow_rec else "source_missing"
        if _truthy(srow.get("stale_flag")):
            stale = True
            stale_reason = stale_reason if stale_reason != "fresh" else "flow_signal_stale"

        cache_hit = cache_dir.joinpath(f"{tk}.json").exists()
        trig = triggers.get(tk, {})
        co_buy = False
        co_sell = False
        if not grp.empty:
            p20 = _sum_window(grp, "pension_net_buy_amount", 20)
            f20 = _sum_window(grp, "foreign_net_buy_amount", 20)
            co_buy = p20 > 0 and f20 > 0
            co_sell = p20 < 0 and f20 < 0

        rows.append({
            "run_id": run_id,
            "run_date": run_date[:10],
            "ticker": tk,
            "name": srow.get("name", tk),
            "market": srow.get("market", "KOSPI"),
            "pension_net_buy_1d": _sum_window(grp, "pension_net_buy_amount", 1) if not grp.empty else "",
            "pension_net_buy_5d": _sum_window(grp, "pension_net_buy_amount", 5) if not grp.empty else "",
            "pension_net_buy_20d": _sum_window(grp, "pension_net_buy_amount", 20) if not grp.empty else "",
            "foreign_net_buy_1d": _sum_window(grp, "foreign_net_buy_amount", 1) if not grp.empty else "",
            "foreign_net_buy_5d": _sum_window(grp, "foreign_net_buy_amount", 5) if not grp.empty else "",
            "foreign_net_buy_20d": _sum_window(grp, "foreign_net_buy_amount", 20) if not grp.empty else "",
            "pension_streak_direction": srow.get("pension_streak_direction", ""),
            "pension_streak_days": srow.get("pension_consecutive_days", ""),
            "foreign_streak_direction": srow.get("foreign_streak_direction", ""),
            "foreign_streak_days": srow.get("foreign_consecutive_days", ""),
            "co_buy_signal": _bool_str(co_buy),
            "co_sell_signal": _bool_str(co_sell),
            "flow_signal_state": trig.get("flow_signal_state") or (
                "stale" if stale else str((flow_rec or {}).get("flow_signal_state") or "neutral")
            ),
            "fresh_or_stale": "stale" if stale else "fresh",
            "stale_reason": stale_reason if stale else "fresh",
            "cache_hit": _bool_str(cache_hit),
            "buy_permission": trig.get("buy_permission") or _bool_str(actual_buy_allowed > 0),
            "review_only": trig.get("review_only") or review_only,
        })
    return rows


def _forward_return_pct(
    prices: pd.DataFrame,
    ticker: str,
    from_date: str,
    business_days: int,
) -> float | None:
    sub = prices[prices["ticker"] == ticker].sort_values("date")
    if sub.empty:
        return None
    start = _row_on_or_before(sub, from_date)  # type: ignore[arg-type]
    if start is None:
        return None
    target = add_business_days(from_date, business_days)
    if not target:
        return None
    end = _row_on_or_before(sub, target)
    if end is None or end["date"] <= start["date"]:
        return None
    return round(_pct_change(float(end["close"]), float(start["close"])), 4)


def _mfe_mae_pct(
    prices: pd.DataFrame,
    ticker: str,
    from_date: str,
    business_days: int,
) -> tuple[float | None, float | None]:
    sub = prices[prices["ticker"] == ticker].sort_values("date")
    if sub.empty:
        return None, None
    start = _row_on_or_before(sub, from_date)  # type: ignore[arg-type]
    if start is None:
        return None, None
    target = add_business_days(from_date, business_days)
    if not target:
        return None, None
    end_bound = _row_on_or_before(sub, target)
    if end_bound is None:
        return None, None
    window = sub[(sub["date"] > start["date"]) & (sub["date"] <= end_bound["date"])]
    if window.empty:
        return None, None
    start_price = float(start["close"])
    closes = pd.to_numeric(window["close"], errors="coerce").dropna()
    if closes.empty or start_price <= 0:
        return None, None
    mfe = round((float(closes.max()) / start_price - 1) * 100, 4)
    mae = round((float(closes.min()) / start_price - 1) * 100, 4)
    return mfe, mae


def _outcome_label(
    *,
    buy_watch: bool,
    trim_watch: bool,
    return_20d: float | None,
) -> str:
    if return_20d is None:
        return "pending"
    if buy_watch:
        return "hit" if return_20d > 0 else "miss"
    if trim_watch:
        return "hit" if return_20d < 0 else "miss"
    return "neutral"


def _count_new_kosdaq_candidates(output_dir: Path, run_date: str) -> int:
    hist_path = _history_dir(output_dir) / "alpha_v2_shadow_history.csv"
    current_final = {
        str(r.get("ticker", "")).zfill(6)
        for r in _read_csv_records(output_dir / "alpha_v2_final_candidates.csv")
        if str(r.get("market", "")).upper() == "KOSDAQ"
    }
    if not current_final:
        return 0
    if not hist_path.exists():
        return len(current_final)
    prior: set[str] = set()
    for row in _read_csv_records(hist_path):
        if str(row.get("run_date", ""))[:10] >= run_date[:10]:
            continue
        if _truthy(row.get("is_final_candidate")) and _truthy(row.get("is_kosdaq")):
            prior.add(str(row.get("ticker", "")).zfill(6))
    return len(current_final - prior)


def evaluate_candidate_outcomes(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_id_filter: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate pending outcomes for history rows with sufficient price data."""
    hist_dir = _history_dir(output_dir)
    v2_hist_path = hist_dir / "alpha_v2_shadow_history.csv"
    flow_hist_path = hist_dir / "flow_dashboard_history.csv"
    v2_out_path = hist_dir / "alpha_v2_candidate_outcomes.csv"
    flow_out_path = hist_dir / "flow_signal_outcomes.csv"

    existing_v2 = {
        (r.get("run_id"), str(r.get("ticker", "")).zfill(6))
        for r in _read_csv_records(v2_out_path)
        if r.get("evaluation_status") == "evaluated"
    }
    existing_flow = {
        (r.get("run_id"), str(r.get("ticker", "")).zfill(6))
        for r in _read_csv_records(flow_out_path)
        if r.get("evaluation_status") == "evaluated"
    }

    prices = load_combined_prices(data_dir)
    if prices.empty:
        return [], []

    evaluated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    v2_outcomes: list[dict[str, Any]] = []
    flow_outcomes: list[dict[str, Any]] = []

    def _eval_row(
        row: dict[str, Any],
        *,
        signal_source: str,
        existing: set[tuple[str, str]],
    ) -> dict[str, Any] | None:
        run_id = str(row.get("run_id") or "")
        tk = str(row.get("ticker", "")).zfill(6)
        run_date = str(row.get("run_date", ""))[:10]
        key = (run_id, tk)
        if key in existing:
            return None

        buy_watch = _truthy(row.get("buy_watch"))
        trim_watch = _truthy(row.get("trim_watch"))
        fresh_or_stale = str(row.get("fresh_or_stale") or "")
        stale = fresh_or_stale == "stale" or _truthy(row.get("flow_data_stale"))

        if stale and signal_source == "flow_dashboard":
            return {
                "run_id": run_id,
                "run_date": run_date,
                "ticker": tk,
                "name": row.get("name", tk),
                "signal_source": signal_source,
                "buy_watch": _bool_str(buy_watch),
                "trim_watch": _bool_str(trim_watch),
                "flow_signal_state": row.get("flow_signal_state", ""),
                "fresh_or_stale": "stale",
                "is_kosdaq": row.get("is_kosdaq", ""),
                "5d_return": "",
                "20d_return": "",
                "60d_return": "",
                "max_favorable_excursion": "",
                "max_adverse_excursion": "",
                "outcome_label": "stale_excluded",
                "false_positive_flag": "",
                "false_negative_flag": "",
                "evaluation_status": "stale_excluded",
                "evaluated_at": evaluated_at,
            }

        if not buy_watch and not trim_watch and signal_source == "alpha_v2":
            return None

        r5 = _forward_return_pct(prices, tk, run_date, 5)
        r20 = _forward_return_pct(prices, tk, run_date, 20)
        r60 = _forward_return_pct(prices, tk, run_date, 60)
        if r20 is None and r5 is None:
            return None

        mfe, mae = _mfe_mae_pct(prices, tk, run_date, 60)
        label = _outcome_label(buy_watch=buy_watch, trim_watch=trim_watch, return_20d=r20)
        fp = ""
        if buy_watch and r20 is not None:
            fp = _bool_str(r20 < 0)
        fn = ""
        if trim_watch and r20 is not None:
            fn = _bool_str(r20 > 0)

        return {
            "run_id": run_id,
            "run_date": run_date,
            "ticker": tk,
            "name": row.get("name", tk),
            "signal_source": signal_source,
            "buy_watch": _bool_str(buy_watch),
            "trim_watch": _bool_str(trim_watch),
            "flow_signal_state": row.get("flow_signal_state", ""),
            "fresh_or_stale": fresh_or_stale or ("stale" if _truthy(row.get("flow_data_stale")) else "fresh"),
            "is_kosdaq": row.get("is_kosdaq", ""),
            "5d_return": r5 if r5 is not None else "",
            "20d_return": r20 if r20 is not None else "",
            "60d_return": r60 if r60 is not None else "",
            "max_favorable_excursion": mfe if mfe is not None else "",
            "max_adverse_excursion": mae if mae is not None else "",
            "outcome_label": label,
            "false_positive_flag": fp,
            "false_negative_flag": fn,
            "evaluation_status": "evaluated" if r20 is not None else "pending",
            "evaluated_at": evaluated_at,
        }

    for row in _read_csv_records(v2_hist_path):
        if run_id_filter and str(row.get("run_id") or "") != run_id_filter:
            continue
        out = _eval_row(row, signal_source="alpha_v2", existing=existing_v2)
        if out:
            v2_outcomes.append(out)

    for row in _read_csv_records(flow_hist_path):
        if run_id_filter and str(row.get("run_id") or "") != run_id_filter:
            continue
        if str(row.get("fresh_or_stale")) != "fresh":
            out = _eval_row(row, signal_source="flow_dashboard", existing=existing_flow)
            if out:
                flow_outcomes.append(out)
            continue
        buy_sig = _truthy(row.get("co_buy_signal"))
        trim_sig = _truthy(row.get("co_sell_signal"))
        enriched = dict(row)
        enriched["buy_watch"] = _bool_str(buy_sig)
        enriched["trim_watch"] = _bool_str(trim_sig)
        out = _eval_row(enriched, signal_source="flow_dashboard", existing=existing_flow)
        if out and (buy_sig or trim_sig or out.get("evaluation_status") == "evaluated"):
            flow_outcomes.append(out)

    if v2_outcomes:
        _append_csv_rows(v2_out_path, v2_outcomes, OUTCOME_FIELDS)
    if flow_outcomes:
        _append_csv_rows(flow_out_path, flow_outcomes, OUTCOME_FIELDS)

    return v2_outcomes, flow_outcomes


def append_shadow_history_ledger(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    run_date: str,
    evaluate_outcomes: bool = True,
    run_id_filter: str | None = None,
) -> dict[str, Any]:
    """Append shadow history for this run_id (skip duplicate). Review-only — no target write."""
    hist_dir = _history_dir(output_dir)
    v2_path = hist_dir / "alpha_v2_shadow_history.csv"
    flow_path = hist_dir / "flow_dashboard_history.csv"
    summary_path = hist_dir / "shadow_daily_summary.csv"

    if run_id in _existing_run_ids(v2_path) or run_id in _existing_run_ids(flow_path):
        return {
            "skipped_duplicate_run_id": run_id,
            "alpha_v2_shadow_history_updated": False,
            "flow_dashboard_history_updated": False,
            "target_write_occurred": False,
        }

    v2_rows = build_alpha_v2_shadow_rows(output_dir, run_id=run_id, run_date=run_date)
    flow_rows = build_flow_dashboard_rows(
        data_dir, output_dir, run_id=run_id, run_date=run_date,
    )

    v2_updated = False
    flow_updated = False
    if v2_rows:
        _append_csv_rows(v2_path, v2_rows, ALPHA_V2_SHADOW_FIELDS)
        v2_updated = True
    if flow_rows:
        _append_csv_rows(flow_path, flow_rows, FLOW_DASHBOARD_FIELDS)
        flow_updated = True

    v2_summary = _read_json(output_dir / "alpha_v2_summary.json")
    coverage = v2_summary.get("coverage") or {}
    trim_val = v2_summary.get("trim_watch_validation") or {}
    dash = _read_json(output_dir / "flow_dashboard_summary.json")

    buy_watch_count = int(coverage.get("buy_watch_count") or 0)
    trim_watch_count = int(coverage.get("trim_watch_count") or 0)
    trim_held = int(trim_val.get("trim_watch_held_or_target") or coverage.get("trim_watch_held_count") or 0)
    trim_info = int(trim_val.get("trim_watch_informational") or coverage.get("trim_watch_informational_count") or 0)
    fresh_ratio = dash.get("fresh_ratio") or coverage.get("fresh_flow_ratio") or ""

    summary_row = {
        "run_id": run_id,
        "run_date": run_date[:10],
        "alpha_v2_shadow_history_updated": _bool_str(v2_updated),
        "flow_dashboard_history_updated": _bool_str(flow_updated),
        "buy_watch_count": buy_watch_count,
        "trim_watch_count": trim_watch_count,
        "trim_watch_held_count": trim_held,
        "trim_watch_informational_count": trim_info,
        "new_kosdaq_candidates_count": _count_new_kosdaq_candidates(output_dir, run_date),
        "fresh_flow_ratio": fresh_ratio,
        "watched_ticker_count": dash.get("ticker_count") or len(flow_rows),
        "target_write_occurred": "false",
    }
    _append_csv_rows(summary_path, [summary_row], DAILY_SUMMARY_FIELDS)

    if evaluate_outcomes:
        evaluate_candidate_outcomes(
            data_dir, output_dir, as_of=run_date, run_id_filter=run_id_filter or run_id,
        )

    result = {
        "alpha_v2_shadow_history_updated": v2_updated,
        "flow_dashboard_history_updated": flow_updated,
        "alpha_v2_rows_appended": len(v2_rows),
        "flow_rows_appended": len(flow_rows),
        "buy_watch_count": buy_watch_count,
        "trim_watch_count": trim_watch_count,
        "trim_watch_held_count": trim_held,
        "trim_watch_informational_count": trim_info,
        "new_kosdaq_candidates_count": summary_row["new_kosdaq_candidates_count"],
        "fresh_flow_ratio": fresh_ratio,
        "target_write_occurred": False,
        "paths": {
            "alpha_v2_shadow_history": str(v2_path),
            "flow_dashboard_history": str(flow_path),
            "shadow_daily_summary": str(summary_path),
            "alpha_v2_candidate_outcomes": str(hist_dir / "alpha_v2_candidate_outcomes.csv"),
            "flow_signal_outcomes": str(hist_dir / "flow_signal_outcomes.csv"),
        },
    }

    hist_dir.mkdir(parents=True, exist_ok=True)
    (hist_dir / "shadow_history_last.json").write_text(
        json.dumps({"run_id": run_id, "run_date": run_date[:10], "last_summary": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def build_daily_report_shadow_history_lines(summary: dict[str, Any] | None) -> list[str]:
    if not summary:
        return []
    if summary.get("skipped_duplicate_run_id"):
        return [
            "",
            "## Shadow history ledger",
            "",
            f"- **Skipped duplicate run_id**: `{summary['skipped_duplicate_run_id']}`",
            "",
        ]
    fresh_pct = summary.get("fresh_flow_ratio")
    fresh_line = f"{float(fresh_pct) * 100:.1f}%" if fresh_pct not in ("", None) else "—"
    return [
        "",
        "## Shadow history ledger",
        "",
        f"- **Alpha v2 shadow history updated**: {'yes' if summary.get('alpha_v2_shadow_history_updated') else 'no'}",
        f"- **Flow history updated**: {'yes' if summary.get('flow_dashboard_history_updated') else 'no'}",
        f"- **New KOSDAQ candidates count**: {summary.get('new_kosdaq_candidates_count', 0)}",
        f"- **Buy Watch count**: {summary.get('buy_watch_count', 0)}",
        f"- **Trim Watch held count**: {summary.get('trim_watch_held_count', 0)}",
        f"- **Trim Watch informational count**: {summary.get('trim_watch_informational_count', 0)}",
        f"- **Fresh flow ratio**: {fresh_line}",
        "- **target write**: false (shadow ledger — review-only)",
        "",
    ]


__all__ = [
    "append_shadow_history_ledger",
    "build_alpha_v2_shadow_rows",
    "build_flow_dashboard_rows",
    "build_daily_report_shadow_history_lines",
    "evaluate_candidate_outcomes",
]
