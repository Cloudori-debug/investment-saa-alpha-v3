from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.benchmark_data import load_combined_prices
from src.alpha.gate_forward_enrich import FORWARD_HORIZONS
from src.decision.shadow_performance import _pct_change, _row_on_or_before, add_business_days
from src.value_list.rerating_screener import _load_qvm_maps

FORWARD_RETURN_DISCLAIMER = (
    "Shadow diagnostic only. Forward returns are not buy/sell recommendations. "
    "Do not use for execution until 90-120 days of data accumulate. "
    "Execution authority remains v1.0.2 trade_actions/allowed_actions only."
)

FORWARD_RETURN_QA_DISCLAIMER = (
    "Shadow diagnostic only. Signal dates are aligned to the last valid trading day before "
    "forward returns are measured on trading-day offsets (5/20/60/120). Not for execution."
)

BENCHMARK_KOSPI200 = "069500"
HORIZONS = FORWARD_HORIZONS

TRACKER_FIELDS = [
    "as_of", "ticker", "name", "source_list",
    "signal_calendar_date", "effective_signal_date", "signal_date_adjustment_reason",
    "hakedaka_score", "hakedaka_rank", "catalyst_confidence", "shareholder_return_yield",
    "price_at_signal", "benchmark_price_at_signal",
    "forward_target_date_5d", "forward_target_date_20d", "forward_target_date_60d", "forward_target_date_120d",
    "available_price_date_5d", "available_price_date_20d", "available_price_date_60d", "available_price_date_120d",
    "forward_return_5d", "forward_return_20d", "forward_return_60d", "forward_return_120d",
    "excess_vs_kospi200_5d", "excess_vs_kospi200_20d", "excess_vs_kospi200_60d", "excess_vs_kospi200_120d",
    "result_status", "shadow_only", "execution_authority",
]

WATCHLIST_PERF_FIELDS = [
    "as_of", "ticker", "name", "event_type", "confidence", "shareholder_return_yield",
    "hakedaka_score", "hakedaka_rank", "forward_return_5d", "forward_return_20d",
    "excess_vs_kospi200_20d", "result_status", "shadow_only", "execution_authority",
]

PHASE4I_GROUP_LABELS = {
    101: "phase4i_top15",
    102: "phase4i_catalyst_watchlist",
    103: "phase4i_high_confidence_catalyst",
    104: "phase4i_low_confidence_catalyst",
    105: "phase4i_qvm_overlap",
    106: "phase4i_qvm_non_overlap",
    107: "phase4i_verified_primary",
}


def _f(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _avg(vals: list[float | None]) -> float | None:
    clean = [v for v in vals if v is not None]
    return round(sum(clean) / len(clean), 4) if clean else None


def _price_on(prices: pd.DataFrame, ticker: str, as_of: str) -> float | None:
    norm = str(ticker).zfill(6)
    sub = prices[prices["ticker"] == norm].sort_values("date")
    if sub.empty:
        return None
    row = _row_on_or_before(sub, as_of)
    if row is None:
        return None
    return float(row["close"])


def _latest_price_date(prices: pd.DataFrame, ticker: str | None = None) -> str:
    if prices.empty:
        return date.today().isoformat()
    sub = prices
    if ticker:
        sub = prices[prices["ticker"] == str(ticker).zfill(6)]
    if sub.empty:
        return date.today().isoformat()
    return pd.to_datetime(sub["date"].max()).strftime("%Y-%m-%d")


def _parse_date_str(d: str) -> pd.Timestamp | None:
    ts = pd.to_datetime(str(d)[:10], errors="coerce")
    return ts if pd.notna(ts) else None


def resolve_effective_signal_date(
    prices: pd.DataFrame,
    calendar_date: str,
    *,
    benchmark_ticker: str = BENCHMARK_KOSPI200,
) -> tuple[str | None, str, str]:
    """Align signal calendar date to last valid benchmark trading day on/before calendar date."""
    last_price_date = _latest_price_date(prices, benchmark_ticker)
    norm = str(benchmark_ticker).zfill(6)
    bench = prices[prices["ticker"] == norm].sort_values("date")
    if bench.empty:
        return None, "missing_price", last_price_date

    row = _row_on_or_before(bench, calendar_date)
    if row is None:
        return None, "missing_price", last_price_date

    effective = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
    cal = calendar_date[:10]
    if effective == cal:
        return effective, "none", last_price_date

    reasons: list[str] = []
    cal_ts = _parse_date_str(cal)
    if cal_ts is not None and cal_ts.weekday() >= 5:
        reasons.append("non_trading_day")
    if cal > last_price_date:
        reasons.append("price_lag")
    if not reasons:
        reasons.append("non_trading_day")

    if "non_trading_day" in reasons and "price_lag" in reasons:
        return effective, "non_trading_day_or_price_lag", last_price_date
    return effective, reasons[0], last_price_date


def _ticker_sub(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    norm = str(ticker).zfill(6)
    return prices[prices["ticker"] == norm].sort_values("date").reset_index(drop=True)


def _forward_target_trading_date(sub: pd.DataFrame, effective_date: str, n: int) -> str | None:
    """Nth trading session on/after effective_date (n=0 -> effective_date itself)."""
    if sub.empty or n < 0:
        return None
    start_row = _row_on_or_before(sub, effective_date)
    if start_row is None:
        return None
    start_date = pd.Timestamp(start_row["date"])
    future = sub[sub["date"] >= start_date]["date"].tolist()
    if len(future) > n:
        return pd.Timestamp(future[n]).strftime("%Y-%m-%d")
    return add_business_days(effective_date, n)


def _forward_return_trading_days(
    prices: pd.DataFrame,
    ticker: str,
    effective_date: str,
    n: int,
    last_data_date: str,
) -> tuple[float | None, str | None, str | None]:
    """Return (forward_return_pct, forward_target_date, available_price_date)."""
    sub = _ticker_sub(prices, ticker)
    target_date = _forward_target_trading_date(sub, effective_date, n)
    if not target_date:
        return None, None, None
    if target_date > last_data_date:
        return None, target_date, None

    start_row = _row_on_or_before(sub, effective_date)
    end_row = _row_on_or_before(sub, target_date)
    if start_row is None or end_row is None:
        return None, target_date, None
    if pd.Timestamp(end_row["date"]) <= pd.Timestamp(start_row["date"]):
        return None, target_date, None

    ret = _pct_change(float(end_row["close"]), float(start_row["close"]))
    avail = pd.Timestamp(end_row["date"]).strftime("%Y-%m-%d")
    return ret, target_date, avail


def _resolve_result_status(
    *,
    signal_price: float | None,
    benchmark_price: float | None,
    any_available: bool,
    any_pending: bool,
    ticker_has_history: bool,
) -> str:
    if benchmark_price is None:
        return "benchmark_missing"
    if signal_price is None:
        return "signal_price_missing"
    if not ticker_has_history:
        return "insufficient_price"
    if any_available:
        return "available"
    if any_pending:
        return "pending"
    return "pending"


def _compute_forward_row(
    prices: pd.DataFrame,
    ticker: str,
    effective_signal_date: str,
    last_data_date: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    any_available = False
    any_pending = False
    sub = _ticker_sub(prices, ticker)
    bench_sub = _ticker_sub(prices, BENCHMARK_KOSPI200)
    ticker_has_history = not sub.empty

    for h in HORIZONS:
        col = f"forward_return_{h}d"
        exc_col = f"excess_vs_kospi200_{h}d"
        target_col = f"forward_target_date_{h}d"
        avail_col = f"available_price_date_{h}d"

        target = _forward_target_trading_date(bench_sub, effective_signal_date, h)
        out[target_col] = target

        ret, _, avail = _forward_return_trading_days(
            prices, ticker, effective_signal_date, h, last_data_date,
        )
        bench_ret, _, _ = _forward_return_trading_days(
            prices, BENCHMARK_KOSPI200, effective_signal_date, h, last_data_date,
        )

        out[avail_col] = avail
        out[col] = ret
        out[exc_col] = round(ret - bench_ret, 4) if ret is not None and bench_ret is not None else None

        if ret is not None:
            any_available = True
        elif target and target > last_data_date:
            any_pending = True
        elif target:
            any_pending = True

    out["result_status"] = _resolve_result_status(
        signal_price=_price_on(prices, ticker, effective_signal_date),
        benchmark_price=_price_on(prices, BENCHMARK_KOSPI200, effective_signal_date),
        any_available=any_available,
        any_pending=any_pending,
        ticker_has_history=ticker_has_history,
    )
    return out


def _load_score_meta(output_dir: Path) -> tuple[dict[str, float], dict[str, int], dict[str, str]]:
    scores: dict[str, float] = {}
    ranks: dict[str, int] = {}
    names: dict[str, str] = {}
    path = output_dir / "hakedaka_catalyst_scores.csv"
    if not path.exists():
        return scores, ranks, names
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    score_col = "hakedaka_total_score" if "hakedaka_total_score" in df.columns else "total_score"
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
    df = df.sort_values(score_col, ascending=False).reset_index(drop=True)
    for i, row in df.iterrows():
        t = str(row["ticker"]).zfill(6)
        scores[t] = float(row[score_col])
        ranks[t] = int(i) + 1
        names[t] = str(row.get("name", t))
    return scores, ranks, names


def _best_catalyst_confidence(output_dir: Path, ticker: str) -> str:
    path = output_dir / "hakedaka_catalyst_evidence.json"
    if not path.exists():
        return ""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        best = "low"
        rank = {"high": 3, "medium": 2, "needs_review": 1, "low": 0}
        for row in doc.get("rows") or []:
            if str(row.get("ticker", "")).zfill(6) != ticker.zfill(6):
                continue
            c = str(row.get("extraction_confidence", "low"))
            if rank.get(c, 0) > rank.get(best, 0):
                best = c
        return best
    except (json.JSONDecodeError, OSError):
        return ""


def _shareholder_yield(output_dir: Path, ticker: str) -> float | None:
    path = output_dir / "hakedaka_shareholder_return.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    row = df[df["ticker"].astype(str).str.zfill(6) == ticker.zfill(6)]
    if row.empty:
        return None
    return _f(row.iloc[0].get("shareholder_return_yield"))


def collect_tracking_universe(
    output_dir: Path,
    *,
    top_n: int = 15,
) -> dict[str, dict[str, Any]]:
    """Map ticker -> metadata including source_list tags."""
    scores, ranks, names = _load_score_meta(output_dir)
    qvm_map, shortlist = _load_qvm_maps(output_dir)
    universe: dict[str, dict[str, Any]] = {}

    def _add(ticker: str, source: str, **extra: Any) -> None:
        t = str(ticker).zfill(6)
        if t not in universe:
            universe[t] = {
                "ticker": t,
                "name": names.get(t, extra.get("name", t)),
                "sources": set(),
                "hakedaka_score": scores.get(t),
                "hakedaka_rank": ranks.get(t),
            }
        universe[t]["sources"].add(source)
        for k, v in extra.items():
            if v not in (None, "") and k != "name":
                universe[t][k] = v
        if extra.get("name"):
            universe[t]["name"] = extra["name"]

    top_path = output_dir / "hakedaka_top_candidate_verification.csv"
    if top_path.exists():
        df = pd.read_csv(top_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            _add(row["ticker"], "top15", name=row.get("name"))
    else:
        sorted_tickers = sorted(scores.keys(), key=lambda t: scores.get(t, 0), reverse=True)
        for t in sorted_tickers[:top_n]:
            _add(t, "top15")

    wl_path = output_dir / "hakedaka_catalyst_watchlist.csv"
    if wl_path.exists():
        df = pd.read_csv(wl_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            _add(
                row["ticker"], "catalyst_watchlist",
                name=row.get("name"),
                catalyst_confidence=row.get("confidence"),
            )

    pri_path = output_dir / "hakedaka_primary_hunt_list.csv"
    if pri_path.exists():
        df = pd.read_csv(pri_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            _add(row["ticker"], "verified_primary", name=row.get("name"))

    for t, info in qvm_map.items():
        status = "qvm_overlap" if (t in shortlist or info.get("in_shortlist")) else "qvm_non_overlap"
        if info.get("qvm_rank") or t in shortlist:
            _add(t, status)

    cat_path = output_dir / "hakedaka_catalyst_evidence.json"
    if cat_path.exists():
        try:
            doc = json.loads(cat_path.read_text(encoding="utf-8"))
            for row in doc.get("rows") or []:
                conf = str(row.get("extraction_confidence", "low"))
                tag = "high_confidence_catalyst" if conf == "high" else (
                    "low_confidence_catalyst" if conf in ("low", "needs_review") else ""
                )
                if tag:
                    _add(row["ticker"], tag, catalyst_confidence=conf, name=row.get("name"))
        except (json.JSONDecodeError, OSError):
            pass

    return universe


def build_forward_return_tracker_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    top_n: int = 15,
) -> list[dict[str, Any]]:
    prices = load_combined_prices(data_dir)
    if prices.empty:
        from src.decision.shadow_performance import _load_price_history
        prices = _load_price_history(data_dir)
    last_data = _latest_price_date(prices, BENCHMARK_KOSPI200)
    effective_date, adjustment_reason, _ = resolve_effective_signal_date(prices, as_of)
    bench_px = _price_on(prices, BENCHMARK_KOSPI200, effective_date) if effective_date else None

    universe = collect_tracking_universe(output_dir, top_n=top_n)
    rows: list[dict[str, Any]] = []

    for t, meta in sorted(universe.items()):
        eff = effective_date or as_of
        fwd = _compute_forward_row(prices, t, eff, last_data)
        conf = meta.get("catalyst_confidence") or _best_catalyst_confidence(output_dir, t)
        shr = _shareholder_yield(output_dir, t)
        rows.append({
            "as_of": as_of,
            "ticker": t,
            "name": meta.get("name", t),
            "source_list": ";".join(sorted(meta.get("sources") or [])),
            "signal_calendar_date": as_of,
            "effective_signal_date": eff,
            "signal_date_adjustment_reason": adjustment_reason if effective_date else "missing_price",
            "hakedaka_score": meta.get("hakedaka_score"),
            "hakedaka_rank": meta.get("hakedaka_rank"),
            "catalyst_confidence": conf,
            "shareholder_return_yield": shr,
            "price_at_signal": _price_on(prices, t, eff),
            "benchmark_price_at_signal": bench_px,
            **fwd,
            "shadow_only": True,
            "execution_authority": "none",
        })
    return rows


def build_watchlist_performance_rows(
    tracker_rows: list[dict[str, Any]],
    output_dir: Path,
    *,
    as_of: str,
) -> list[dict[str, Any]]:
    wl_path = output_dir / "hakedaka_catalyst_watchlist.csv"
    if not wl_path.exists():
        return []
    wl = pd.read_csv(wl_path, dtype=str, keep_default_na=False)
    by_ticker = {str(r["ticker"]).zfill(6): r for r in tracker_rows}
    rows: list[dict[str, Any]] = []
    for _, row in wl.iterrows():
        t = str(row["ticker"]).zfill(6)
        tr = by_ticker.get(t, {})
        rows.append({
            "as_of": as_of,
            "ticker": t,
            "name": row.get("name", t),
            "event_type": row.get("event_type", ""),
            "confidence": row.get("confidence", ""),
            "shareholder_return_yield": row.get("shareholder_return_yield") or tr.get("shareholder_return_yield"),
            "hakedaka_score": row.get("hakedaka_score") or tr.get("hakedaka_score"),
            "hakedaka_rank": row.get("hakedaka_rank") or tr.get("hakedaka_rank"),
            "forward_return_5d": tr.get("forward_return_5d"),
            "forward_return_20d": tr.get("forward_return_20d"),
            "excess_vs_kospi200_20d": tr.get("excess_vs_kospi200_20d"),
            "result_status": tr.get("result_status", "pending"),
            "shadow_only": True,
            "execution_authority": "none",
        })
    return rows


def _aggregate_by_source(rows: list[dict[str, Any]], source_key: str) -> dict[str, Any]:
    matched = [r for r in rows if source_key in str(r.get("source_list", "")).split(";")]
    return {
        "count": len(matched),
        "avg_forward_5d": _avg([_f(r.get("forward_return_5d")) for r in matched]),
        "avg_forward_20d": _avg([_f(r.get("forward_return_20d")) for r in matched]),
        "avg_forward_60d": _avg([_f(r.get("forward_return_60d")) for r in matched]),
        "avg_forward_120d": _avg([_f(r.get("forward_return_120d")) for r in matched]),
        "avg_excess_kospi_20d": _avg([_f(r.get("excess_vs_kospi200_20d")) for r in matched]),
        "pending": sum(1 for r in matched if r.get("result_status") == "pending"),
        "available": sum(1 for r in matched if r.get("result_status") == "available"),
    }



def _quintile_spread(rows: list[dict[str, Any]]) -> float | None:
    scored = [(r, _f(r.get("hakedaka_score")) or 0) for r in rows if r.get("hakedaka_score") not in (None, "")]
    if len(scored) < 5:
        return None
    scored.sort(key=lambda x: x[1], reverse=True)
    n = max(1, len(scored) // 5)
    top = _avg([_f(r.get("forward_return_20d")) for r, _ in scored[:n]])
    bottom = _avg([_f(r.get("forward_return_20d")) for r, _ in scored[-n:]])
    if top is None or bottom is None:
        return None
    return round(top - bottom, 4)


def append_phase4i_group_forward_rows(
    output_dir: Path,
    aggregates: dict[str, dict[str, Any]],
    *,
    as_of: str,
) -> None:
    path = output_dir / "hakedaka_group_forward_return.csv"
    fieldnames = [
        "date", "run_id", "group_id", "group_label", "candidate_count",
        "avg_forward_5d", "avg_forward_20d", "avg_forward_60d", "avg_forward_120d",
        "avg_excess_vs_kospi_20d", "top_quintile_avg_20d", "bottom_quintile_avg_20d",
        "overlap_avg_20d", "hakedaka_only_avg_20d",
    ]
    write_header = not path.exists()
    gid_map = {
        "top15": 101,
        "catalyst_watchlist": 102,
        "high_confidence_catalyst": 103,
        "low_confidence_catalyst": 104,
        "qvm_overlap": 105,
        "qvm_non_overlap": 106,
        "verified_primary": 107,
    }
    out_rows: list[dict[str, Any]] = []
    for key, agg in aggregates.items():
        if key.startswith("_") or not agg.get("count"):
            continue
        gid = gid_map.get(key, 199)
        out_rows.append({
            "date": as_of,
            "run_id": "phase4i",
            "group_id": gid,
            "group_label": PHASE4I_GROUP_LABELS.get(gid, key),
            "candidate_count": agg.get("count", 0),
            "avg_forward_5d": agg.get("avg_forward_5d"),
            "avg_forward_20d": agg.get("avg_forward_20d"),
            "avg_forward_60d": agg.get("avg_forward_60d"),
            "avg_forward_120d": agg.get("avg_forward_120d"),
            "avg_excess_vs_kospi_20d": agg.get("avg_excess_kospi_20d"),
            "top_quintile_avg_20d": "",
            "bottom_quintile_avg_20d": "",
            "overlap_avg_20d": aggregates.get("qvm_overlap", {}).get("avg_forward_20d", ""),
            "hakedaka_only_avg_20d": aggregates.get("qvm_non_overlap", {}).get("avg_forward_20d", ""),
        })
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(out_rows)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_hakedaka_forward_return_tracking(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    top_n: int = 15,
) -> dict[str, Any]:
    """Phase 4i — Forward Return & Catalyst Watchlist Tracking (shadow only)."""
    as_of_date = as_of or date.today().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    tracker_rows = build_forward_return_tracker_rows(
        data_dir, output_dir, as_of=as_of_date, top_n=top_n,
    )
    write_csv(output_dir / "hakedaka_forward_return_tracker.csv", TRACKER_FIELDS, tracker_rows)

    wl_perf = build_watchlist_performance_rows(tracker_rows, output_dir, as_of=as_of_date)
    write_csv(output_dir / "hakedaka_catalyst_watchlist_performance.csv", WATCHLIST_PERF_FIELDS, wl_perf)

    prices = load_combined_prices(data_dir)
    effective_date, adjustment_reason, last_price_date = resolve_effective_signal_date(
        prices, as_of_date,
    )
    aggregates = {
        "top15": _aggregate_by_source(tracker_rows, "top15"),
        "catalyst_watchlist": _aggregate_by_source(tracker_rows, "catalyst_watchlist"),
        "verified_primary": _aggregate_by_source(tracker_rows, "verified_primary"),
        "qvm_overlap": _aggregate_by_source(tracker_rows, "qvm_overlap"),
        "qvm_non_overlap": _aggregate_by_source(tracker_rows, "qvm_non_overlap"),
        "high_confidence_catalyst": _aggregate_by_source(tracker_rows, "high_confidence_catalyst"),
        "low_confidence_catalyst": _aggregate_by_source(tracker_rows, "low_confidence_catalyst"),
        "_quintile_spread_20d": {"value": _quintile_spread(tracker_rows)},
        "_kospi200_bench": {
            "avg_forward_20d": _forward_return_trading_days(
                prices, BENCHMARK_KOSPI200, effective_date or as_of_date, 20, last_price_date,
            )[0] if effective_date and not prices.empty else None,
        },
    }
    append_phase4i_group_forward_rows(output_dir, aggregates, as_of=as_of_date)

    pending = sum(1 for r in tracker_rows if r.get("result_status") == "pending")
    available = sum(1 for r in tracker_rows if r.get("result_status") == "available")
    insufficient = sum(1 for r in tracker_rows if r.get("result_status") == "insufficient_price")
    signal_missing = sum(1 for r in tracker_rows if r.get("result_status") == "signal_price_missing")
    bench_missing = sum(1 for r in tracker_rows if r.get("result_status") == "benchmark_missing")
    price_at_signal_filled = sum(1 for r in tracker_rows if r.get("price_at_signal") not in (None, ""))

    doc = {
        "as_of": as_of_date,
        "mode": "shadow_forward_return_tracking",
        "disclaimer": FORWARD_RETURN_DISCLAIMER,
        "signal_calendar_date": as_of_date,
        "effective_signal_date": effective_date,
        "signal_date_adjustment_reason": adjustment_reason,
        "last_price_date": last_price_date,
        "tracker_count": len(tracker_rows),
        "watchlist_performance_count": len(wl_perf),
        "status_counts": {
            "pending": pending,
            "available": available,
            "insufficient_price": insufficient,
            "signal_price_missing": signal_missing,
            "benchmark_missing": bench_missing,
        },
        "aggregates": aggregates,
        "rows": tracker_rows,
    }
    (output_dir / "hakedaka_forward_return_tracker.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    report = {
        "as_of": as_of_date,
        "mode": "shadow_only",
        "phase": "4i",
        "disclaimer": FORWARD_RETURN_DISCLAIMER,
        "summary": {
            "tracker_count": len(tracker_rows),
            "pending_count": pending,
            "available_count": available,
            "insufficient_price_count": insufficient,
            "watchlist_count": len(wl_perf),
            "top15_avg_forward_5d": aggregates["top15"].get("avg_forward_5d"),
            "top15_avg_forward_20d": aggregates["top15"].get("avg_forward_20d"),
            "watchlist_avg_forward_20d": aggregates["catalyst_watchlist"].get("avg_forward_20d"),
            "high_confidence_avg_forward_20d": aggregates["high_confidence_catalyst"].get("avg_forward_20d"),
            "qvm_overlap_avg_forward_20d": aggregates["qvm_overlap"].get("avg_forward_20d"),
            "qvm_non_overlap_avg_forward_20d": aggregates["qvm_non_overlap"].get("avg_forward_20d"),
            "quintile_spread_20d": aggregates["_quintile_spread_20d"].get("value"),
        },
    }
    (output_dir / "hakedaka_phase4i_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    qa_report = {
        "as_of": as_of_date,
        "mode": "shadow_only",
        "phase": "4i-1",
        "disclaimer": FORWARD_RETURN_QA_DISCLAIMER,
        "summary": {
            "signal_calendar_date": as_of_date,
            "effective_signal_date": effective_date,
            "last_price_date": last_price_date,
            "signal_date_adjustment_reason": adjustment_reason,
            "tracker_count": len(tracker_rows),
            "price_at_signal_filled_count": price_at_signal_filled,
            "pending_count": pending,
            "available_count": available,
            "signal_price_missing_count": signal_missing,
            "benchmark_missing_count": bench_missing,
            "insufficient_price_count": insufficient,
            "alignment_pass": (
                effective_date is not None
                and price_at_signal_filled == len(tracker_rows) - signal_missing - bench_missing
            ),
        },
    }
    (output_dir / "hakedaka_phase4i1_report.json").write_text(
        json.dumps(qa_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report


def build_daily_report_forward_return_qa_section(output_dir: Path | None) -> list[str]:
    if not output_dir:
        return []
    path = output_dir / "hakedaka_phase4i1_report.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    summ = doc.get("summary") or {}
    lines = [
        "## Hakedaka Forward Return QA (shadow only)",
        f"> {FORWARD_RETURN_QA_DISCLAIMER}",
        f"- **signal_calendar_date**: {summ.get('signal_calendar_date', '—')} → "
        f"**effective_signal_date**: {summ.get('effective_signal_date', '—')} "
        f"({summ.get('signal_date_adjustment_reason', '—')})",
        f"- **last_price_date**: {summ.get('last_price_date', '—')} · "
        f"price_at_signal filled {summ.get('price_at_signal_filled_count', 0)}/{summ.get('tracker_count', 0)}",
        f"- **status**: pending {summ.get('pending_count', 0)} · available {summ.get('available_count', 0)} · "
        f"signal_price_missing {summ.get('signal_price_missing_count', 0)}",
        "- horizon은 **거래일 기준** (5/20/60/120 trading sessions) — shadow diagnostic only",
        "- 90~120일 데이터가 쌓이기 전까지 실행 판단에 사용하지 않음",
        "",
    ]
    return lines


def build_daily_report_forward_return_section(output_dir: Path | None) -> list[str]:
    if not output_dir:
        return []
    path = output_dir / "hakedaka_phase4i_report.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    summ = doc.get("summary") or {}
    lines = [
        "## Hakedaka Forward Return Tracking (shadow only)",
        f"> {FORWARD_RETURN_DISCLAIMER}",
        f"- **추적 종목**: {summ.get('tracker_count', 0)} · pending {summ.get('pending_count', 0)} · "
        f"available {summ.get('available_count', 0)} · insufficient_price {summ.get('insufficient_price_count', 0)}",
        f"- **5D/20D available (top15 avg)**: 5D — · 20D {summ.get('top15_avg_forward_20d', '—')}%",
        f"- **catalyst watchlist avg 20D**: {summ.get('watchlist_avg_forward_20d', '—')}% "
        f"({summ.get('watchlist_count', 0)}종)",
        f"- **top15 vs watchlist (20D excess vs KOSPI)**: top15 {summ.get('top15_avg_forward_20d', '—')}% · "
        f"watchlist {summ.get('watchlist_avg_forward_20d', '—')}%",
        "- 이 섹션은 **shadow diagnostic only** — forward return은 매수/매도 권고가 아님",
        "- 90~120일 데이터가 쌓이기 전까지 실행 판단에 사용하지 않음",
        "",
    ]
    return lines
