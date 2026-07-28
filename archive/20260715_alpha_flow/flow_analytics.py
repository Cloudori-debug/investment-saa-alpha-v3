from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.flow_refresh import _extract_investor_nets, _find_flow_columns, _load_mcap_by_ticker
from src.alpha.investor_flows import load_investor_flows


TIMESERIES_COLUMNS = [
    "date", "ticker", "name", "market",
    "pension_net_buy_amount", "pension_net_buy_volume",
    "foreign_net_buy_amount", "foreign_net_buy_volume",
    "institution_net_buy_amount", "individual_net_buy_amount",
    "close", "market_cap", "trading_value",
    "data_source", "data_as_of", "stale_flag",
]

STREAK_COLUMNS = [
    "ticker", "name", "market",
    "pension_streak_direction", "pension_consecutive_days", "pension_streak_amount",
    "foreign_streak_direction", "foreign_consecutive_days", "foreign_streak_amount",
    "cobuy_consecutive_days", "cosell_consecutive_days",
    "latest_date", "stale_flag", "actual_consecutive_days",
]

LEADERBOARD_COLUMNS = [
    "rank", "ticker", "name", "market", "sector",
    "net_buy_amount", "net_buy_to_market_cap", "net_buy_to_turnover",
    "consecutive_days", "co_buy_flag", "co_sell_flag",
    "grade", "alpha_v2_score", "holding_flag", "target_flag",
    "buy_watch", "trim_watch", "buy_permission", "review_only",
    "period", "leaderboard_type", "actual_consecutive_days",
]


@dataclass
class FlowDashboardResult:
    as_of: str
    ticker_count: int
    timeseries_rows: int
    streak_rows: int
    warnings: list[str] = field(default_factory=list)
    paths: dict[str, str] = field(default_factory=dict)


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _format_index_date(idx: Any) -> str:
    text = str(idx)
    c = text.replace("-", "")[:8]
    if len(c) == 8 and c.isdigit():
        return f"{c[:4]}-{c[4:6]}-{c[6:8]}"
    return text[:10]


def parse_daily_timeseries_from_df(
    df: Any,
    *,
    ticker: str,
    name: str,
    market: str,
    as_of: str,
    mcap: float,
    data_source: str = "auto_pykrx",
) -> list[dict[str, Any]]:
    """Parse net-purchases-by-ticker layout (date index, investor columns)."""
    if df is None or getattr(df, "empty", True):
        return []
    foreign_col, institution_col, retail_col, _program_col = _find_flow_columns(df)
    if foreign_col is None and institution_col is None:
        return []

    rows: list[dict[str, Any]] = []
    for idx in df.index:
        try:
            f_val = float(df.loc[idx, foreign_col]) if foreign_col is not None else 0.0
        except (TypeError, ValueError, KeyError):
            f_val = 0.0
        try:
            i_val = float(df.loc[idx, institution_col]) if institution_col is not None else 0.0
        except (TypeError, ValueError, KeyError):
            i_val = 0.0
        try:
            r_val = float(df.loc[idx, retail_col]) if retail_col is not None else 0.0
        except (TypeError, ValueError, KeyError):
            r_val = 0.0
        dt = _format_index_date(idx)
        rows.append({
            "date": dt,
            "ticker": _normalize_ticker(ticker),
            "name": name,
            "market": market,
            "pension_net_buy_amount": i_val,
            "pension_net_buy_volume": "",
            "foreign_net_buy_amount": f_val,
            "foreign_net_buy_volume": "",
            "institution_net_buy_amount": i_val,
            "individual_net_buy_amount": r_val,
            "close": "",
            "market_cap": int(mcap) if mcap else "",
            "trading_value": "",
            "data_source": data_source,
            "data_as_of": as_of[:10],
            "stale_flag": "false",
        })
    return rows


def fetch_daily_series_pykrx(
    stock: Any,
    ticker: str,
    *,
    name: str,
    market: str,
    as_of: str,
    mcap: float,
    lookback_days: int = 25,
    sleep_sec: float = 0.05,
) -> list[dict[str, Any]]:
    """Fetch per-trading-day investor nets via single-day PyKRX calls."""
    from datetime import datetime, timedelta

    from src.data_refresh.pykrx_client import to_compact_date

    end = datetime.strptime(as_of[:10], "%Y-%m-%d")
    cur = end
    daily_rows: list[dict[str, Any]] = []
    scanned = 0
    while len(daily_rows) < lookback_days and scanned < lookback_days * 3:
        if cur.weekday() < 5:
            day = cur.strftime("%Y-%m-%d")
            try:
                df = stock.get_market_trading_value_by_investor(
                    to_compact_date(day), to_compact_date(day), ticker,
                )
                f_val, i_val, r_val, _ = _extract_investor_nets(df)
                daily_rows.append({
                    "date": day,
                    "ticker": _normalize_ticker(ticker),
                    "name": name,
                    "market": market,
                    "pension_net_buy_amount": i_val,
                    "pension_net_buy_volume": "",
                    "foreign_net_buy_amount": f_val,
                    "foreign_net_buy_volume": "",
                    "institution_net_buy_amount": i_val,
                    "individual_net_buy_amount": r_val,
                    "close": "",
                    "market_cap": int(mcap) if mcap else "",
                    "trading_value": "",
                    "data_source": "auto_pykrx_daily",
                    "data_as_of": as_of[:10],
                    "stale_flag": "false",
                })
            except Exception:
                pass
            if sleep_sec:
                time.sleep(sleep_sec)
        cur -= timedelta(days=1)
        scanned += 1
    daily_rows.sort(key=lambda r: r["date"])
    return daily_rows


def consecutive_days(amounts: list[float], direction: str) -> int:
    """Trading-day series oldest→newest; count consecutive days from latest."""
    if not amounts:
        return 0
    streak = 0
    total = 0.0
    for amt in reversed(amounts):
        if direction == "buy":
            if amt > 0:
                streak += 1
                total += amt
            else:
                break
        elif direction == "sell":
            if amt < 0:
                streak += 1
                total += amt
            else:
                break
    return streak if streak else 0


def consecutive_cobuy(pension: list[float], foreign: list[float]) -> int:
    if len(pension) != len(foreign) or not pension:
        return 0
    streak = 0
    for p, f in zip(reversed(pension), reversed(foreign)):
        if p > 0 and f > 0:
            streak += 1
        else:
            break
    return streak


def consecutive_cosell(pension: list[float], foreign: list[float]) -> int:
    if len(pension) != len(foreign) or not pension:
        return 0
    streak = 0
    for p, f in zip(reversed(pension), reversed(foreign)):
        if p < 0 and f < 0:
            streak += 1
        else:
            break
    return streak


def compute_streak_row(
    ticker: str,
    name: str,
    market: str,
    daily: pd.DataFrame,
) -> dict[str, Any]:
    daily = daily.sort_values("date")
    p_amts = pd.to_numeric(daily["pension_net_buy_amount"], errors="coerce").fillna(0).tolist()
    f_amts = pd.to_numeric(daily["foreign_net_buy_amount"], errors="coerce").fillna(0).tolist()
    p_buy = consecutive_days(p_amts, "buy")
    p_sell = consecutive_days(p_amts, "sell")
    f_buy = consecutive_days(f_amts, "buy")
    f_sell = consecutive_days(f_amts, "sell")
    p_dir = "buy" if p_buy >= p_sell and p_buy > 0 else ("sell" if p_sell > 0 else "neutral")
    f_dir = "buy" if f_buy >= f_sell and f_buy > 0 else ("sell" if f_sell > 0 else "neutral")
    p_days = p_buy if p_dir == "buy" else p_sell
    f_days = f_buy if f_dir == "buy" else f_sell
    p_streak_amt = sum(p_amts[-p_days:]) if p_days else 0.0
    f_streak_amt = sum(f_amts[-f_days:]) if f_days else 0.0
    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "pension_streak_direction": p_dir,
        "pension_consecutive_days": p_days,
        "pension_streak_amount": round(p_streak_amt, 0),
        "foreign_streak_direction": f_dir,
        "foreign_consecutive_days": f_days,
        "foreign_streak_amount": round(f_streak_amt, 0),
        "cobuy_consecutive_days": consecutive_cobuy(p_amts, f_amts),
        "cosell_consecutive_days": consecutive_cosell(p_amts, f_amts),
        "latest_date": str(daily["date"].iloc[-1]) if not daily.empty else "",
        "stale_flag": "false",
        "actual_consecutive_days": "true",
    }


def _sum_window(daily: pd.DataFrame, col: str, days: int) -> float:
    s = pd.to_numeric(daily[col], errors="coerce").fillna(0)
    if s.empty:
        return 0.0
    return float(s.tail(days).sum())


def _build_leaderboard_rows(
    streaks_df: pd.DataFrame,
    meta: dict[str, dict[str, Any]],
    *,
    leaderboard_type: str,
    period: str,
    sort_col: str,
    ascending: bool,
    top_n: int = 20,
) -> list[dict[str, Any]]:
    if streaks_df.empty:
        return []
    work = streaks_df.copy()
    if sort_col in work.columns:
        work["_sort"] = pd.to_numeric(work[sort_col], errors="coerce").fillna(0)
    else:
        work["_sort"] = work.apply(
            lambda r: meta.get(str(r["ticker"]).zfill(6), {}).get(sort_col, 0),
            axis=1,
        )
    work = work.sort_values("_sort", ascending=ascending).head(top_n)
    rows: list[dict[str, Any]] = []
    for i, (_, r) in enumerate(work.iterrows(), start=1):
        tk = str(r["ticker"]).zfill(6)
        m = meta.get(tk, {})
        is_foreign = "foreign" in leaderboard_type
        amount_key = f"foreign_net_{period}" if is_foreign else f"net_{period}"
        cd_key = "foreign_consecutive_days" if is_foreign else "pension_consecutive_days"
        if "cobuy" in leaderboard_type:
            cd_key = "cobuy_consecutive_days"
        rows.append({
            "rank": i,
            "ticker": tk,
            "name": r.get("name", m.get("name", "")),
            "market": r.get("market", m.get("market", "KOSPI")),
            "sector": m.get("sector", ""),
            "net_buy_amount": m.get(amount_key, 0),
            "net_buy_to_market_cap": m.get(f"net_{period}_mcap", ""),
            "net_buy_to_turnover": m.get(f"net_{period}_turnover", ""),
            "consecutive_days": r.get(cd_key, 0),
            "co_buy_flag": str(int(r.get("cobuy_consecutive_days") or 0) >= 1),
            "co_sell_flag": str(int(r.get("cosell_consecutive_days") or 0) >= 1),
            "grade": m.get("grade", ""),
            "alpha_v2_score": m.get("alpha_v2_score", ""),
            "holding_flag": m.get("holding_flag", "False"),
            "target_flag": m.get("target_flag", "False"),
            "buy_watch": m.get("buy_watch", "False"),
            "trim_watch": m.get("trim_watch", "False"),
            "buy_permission": "False",
            "review_only": "True",
            "period": period,
            "leaderboard_type": leaderboard_type,
            "actual_consecutive_days": "true",
        })
    return rows


def resolve_flow_target_tickers(data_dir: Path, output_dir: Path, *, max_tickers: int = 80) -> list[dict[str, str]]:
    from src.alpha_flow.watched_universe import resolve_watched_universe_tickers

    return resolve_watched_universe_tickers(data_dir, output_dir, max_tickers=max_tickers)


def _load_universe_market(data_dir: Path) -> dict[str, str]:
    universe_market: dict[str, str] = {}
    uni_path = data_dir / "universe.csv"
    if uni_path.exists():
        try:
            udf = pd.read_csv(uni_path, dtype=str, keep_default_na=False)
            for _, r in udf.iterrows():
                universe_market[_normalize_ticker(r["ticker"])] = str(r.get("market", "KOSPI"))
        except Exception:
            pass
    return universe_market


def _load_scored_meta(output_dir: Path) -> dict[str, dict[str, Any]]:
    scored_meta: dict[str, dict[str, Any]] = {}
    scored_path = output_dir / "alpha_v2_scored.csv"
    if scored_path.exists():
        sdf = pd.read_csv(scored_path, dtype=str, keep_default_na=False)
        for _, r in sdf.iterrows():
            tk = _normalize_ticker(r["ticker"])
            scored_meta[tk] = dict(r)
    return scored_meta


def _finalize_flow_dashboard(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    targets: list[dict[str, str]],
    mcap_map: dict[str, float],
    ts_df: pd.DataFrame,
    warnings: list[str],
    scored_meta: dict[str, dict[str, Any]],
) -> FlowDashboardResult:
    ts_path = output_dir / "flow_daily_timeseries.csv"
    if not ts_path.exists() and not ts_df.empty:
        if set(TIMESERIES_COLUMNS).issubset(ts_df.columns):
            ts_df = ts_df[TIMESERIES_COLUMNS]
        ts_df.to_csv(ts_path, index=False, encoding="utf-8-sig")

    streak_rows: list[dict[str, Any]] = []
    period_meta: dict[str, dict[str, Any]] = {}
    if not ts_df.empty:
        for tk, grp in ts_df.groupby("ticker"):
            tk = _normalize_ticker(str(tk))
            g = grp.sort_values("date")
            name = str(g["name"].iloc[0])
            market = str(g["market"].iloc[0])
            streak_row = compute_streak_row(tk, name, market, g)
            streak_rows.append(streak_row)
            mcap = float(mcap_map.get(tk) or 0)
            tv = pd.to_numeric(g.get("trading_value", 0), errors="coerce").fillna(0)
            turnover = float(tv.tail(20).sum()) if len(tv) else 0.0
            sm = scored_meta.get(tk, {})
            for period, days in (("1d", 1), ("5d", 5), ("20d", 20), ("60d", 60)):
                p_sum = _sum_window(g, "pension_net_buy_amount", days)
                f_sum = _sum_window(g, "foreign_net_buy_amount", days)
                base = period_meta.setdefault(tk, {
                    "name": name,
                    "market": market,
                    "sector": sm.get("sector", ""),
                    "grade": sm.get("grade", ""),
                    "alpha_v2_score": sm.get("total_score_v2_shadow", ""),
                    "buy_watch": sm.get("buy_watch", "False"),
                    "trim_watch": sm.get("trim_watch", "False"),
                    "holding_flag": "False",
                    "target_flag": "False",
                })
                base[f"net_{period}"] = p_sum
                base[f"foreign_net_{period}"] = f_sum
                base[f"net_{period}_mcap"] = round(p_sum / mcap, 6) if mcap else ""
                base[f"net_{period}_turnover"] = round(p_sum / turnover, 6) if turnover else ""
            base["pension_consecutive_days"] = streak_row["pension_consecutive_days"]
            base["foreign_consecutive_days"] = streak_row["foreign_consecutive_days"]
            base["cobuy_consecutive_days"] = streak_row["cobuy_consecutive_days"]
            base["cosell_consecutive_days"] = streak_row["cosell_consecutive_days"]

    streak_df = pd.DataFrame(streak_rows)
    streak_path = output_dir / "flow_streaks.csv"
    if not streak_df.empty:
        streak_df = streak_df[STREAK_COLUMNS]
    streak_df.to_csv(streak_path, index=False, encoding="utf-8-sig")

    boards: dict[str, list[dict[str, Any]]] = {}
    if not streak_df.empty:
        boards["pension_buy"] = _build_leaderboard_rows(
            streak_df, period_meta, leaderboard_type="pension_buy", period="20d",
            sort_col="net_20d", ascending=False,
        )
        boards["foreign_buy"] = _build_leaderboard_rows(
            streak_df, period_meta, leaderboard_type="foreign_buy", period="20d",
            sort_col="foreign_net_20d", ascending=False,
        )
        boards["cobuy"] = sorted(
            _build_leaderboard_rows(
                streak_df[pd.to_numeric(streak_df["cobuy_consecutive_days"], errors="coerce").fillna(0) >= 1],
                period_meta,
                leaderboard_type="cobuy",
                period="20d",
                sort_col="cobuy_consecutive_days",
                ascending=False,
            ),
            key=lambda x: int(str(x.get("consecutive_days") or 0)),
            reverse=True,
        )[:20]
        sell_streaks = streak_df.copy()
        sell_streaks["_ps"] = pd.to_numeric(sell_streaks["pension_consecutive_days"], errors="coerce").fillna(0)
        sell_streaks = sell_streaks[sell_streaks["pension_streak_direction"] == "sell"]
        buy_streaks = streak_df.copy()
        buy_streaks = buy_streaks[buy_streaks["pension_streak_direction"] == "buy"]
        boards["streak_buy"] = _build_leaderboard_rows(
            buy_streaks, period_meta, leaderboard_type="streak_buy", period="20d",
            sort_col="pension_consecutive_days", ascending=False,
        )
        boards["streak_sell"] = _build_leaderboard_rows(
            sell_streaks, period_meta, leaderboard_type="streak_sell", period="20d",
            sort_col="pension_consecutive_days", ascending=False,
        )
        boards["pension_sell"] = _build_leaderboard_rows(
            streak_df, period_meta, leaderboard_type="pension_sell", period="20d",
            sort_col="net_20d", ascending=True,
        )
        boards["foreign_sell"] = _build_leaderboard_rows(
            streak_df, period_meta, leaderboard_type="foreign_sell", period="20d",
            sort_col="foreign_net_20d", ascending=True,
        )

    path_map = {
        "pension_buy": "flow_leaderboard_pension.csv",
        "foreign_buy": "flow_leaderboard_foreign.csv",
        "cobuy": "flow_leaderboard_cobuy.csv",
        "pension_sell": "flow_leaderboard_pension_sell.csv",
        "foreign_sell": "flow_leaderboard_foreign_sell.csv",
        "streak_buy": "flow_leaderboard_streak_buy.csv",
        "streak_sell": "flow_leaderboard_streak_sell.csv",
    }
    paths: dict[str, str] = {"timeseries": str(ts_path), "streaks": str(streak_path)}
    for key, fname in path_map.items():
        rows = boards.get(key, [])
        p = output_dir / fname
        if rows:
            pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
        else:
            pd.DataFrame(columns=LEADERBOARD_COLUMNS).to_csv(p, index=False, encoding="utf-8-sig")
        paths[key] = str(p)

    scored_path = output_dir / "alpha_v2_scored.csv"
    coverage_records: list[dict[str, Any]] = []
    watch_set = { _normalize_ticker(t["ticker"]) for t in targets }
    if scored_path.exists():
        sdf = pd.read_csv(scored_path, dtype=str, keep_default_na=False)
        coverage_records = [
            dict(r) for _, r in sdf.iterrows()
            if _normalize_ticker(r["ticker"]) in watch_set
        ]
    elif not ts_df.empty:
        coverage_records = [{"stale_flag": r.get("stale_flag", "false")} for r in streak_rows]

    refresh_meta: dict[str, Any] = {}
    gpt_path = output_dir / "gpt_context.json"
    if gpt_path.exists():
        try:
            gpt = json.loads(gpt_path.read_text(encoding="utf-8"))
            refresh_meta = (gpt.get("kr_alpha_meta") or {}).get("flow_refresh") or {}
        except (json.JSONDecodeError, OSError):
            pass

    from src.alpha_flow.flow_service import build_flow_coverage_meta

    cache_meta = build_flow_coverage_meta(
        coverage_records,
        as_of=as_of,
        data_dir=data_dir,
        source="flow_dashboard",
        cache_hit_count=int(refresh_meta.get("cache_hit_count") or 0),
        cache_miss_count=int(refresh_meta.get("cache_miss_count") or 0),
        pykrx_call_count=int(refresh_meta.get("pykrx_call_count") or 0),
        pykrx_failed_tickers=list(refresh_meta.get("failed_tickers") or []),
        stale_reason_summary=dict(refresh_meta.get("stale_reason_summary") or {}),
        last_successful_flow_refresh=str(refresh_meta.get("last_successful_flow_refresh") or as_of),
        coverage_scope="watched_universe",
        warnings=warnings,
    )

    summary = {
        "as_of": as_of,
        "ticker_count": len(targets),
        "timeseries_rows": len(ts_df),
        "streak_rows": len(streak_df),
        "actual_consecutive_days": len(streak_df) > 0,
        "fresh_flow_count": cache_meta["fresh_flow_count"],
        "stale_flow_count": cache_meta["stale_flow_count"],
        "fresh_count": cache_meta["fresh_count"],
        "stale_count": cache_meta["stale_count"],
        "fresh_ratio": cache_meta["fresh_ratio"],
        "stale_ratio": cache_meta["stale_ratio"],
        "stale_reason_summary": cache_meta["stale_reason_summary"],
        "cache_hit_count": cache_meta["cache_hit_count"],
        "cache_miss_count": cache_meta["cache_miss_count"],
        "pykrx_call_count": cache_meta["pykrx_call_count"],
        "pykrx_failed_tickers": cache_meta["pykrx_failed_tickers"],
        "last_successful_flow_refresh": cache_meta["last_successful_flow_refresh"],
        "coverage_scope": "watched_universe",
        "cache_meta": cache_meta,
        "warnings": warnings[:20],
        "paths": paths,
    }
    (output_dir / "flow_dashboard_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return FlowDashboardResult(
        as_of=as_of,
        ticker_count=len(targets),
        timeseries_rows=len(ts_df),
        streak_rows=len(streak_df),
        warnings=warnings,
        paths=paths,
    )


def reuse_flow_dashboard_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    max_tickers: int = 80,
    profiler: object | None = None,
    stale_flow_warning: bool = False,
) -> FlowDashboardResult:
    """Reuse existing flow dashboard artifacts without PyKRX refresh."""
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of = as_of[:10]
    warnings: list[str] = ["shadow flow: reused from cache"]
    if stale_flow_warning:
        warnings.append("shadow flow stale — review-only; buy permission unchanged")
    targets = resolve_flow_target_tickers(data_dir, output_dir, max_tickers=max_tickers)
    mcap_map = _load_mcap_by_ticker(data_dir)
    scored_meta = _load_scored_meta(output_dir)
    ts_path = output_dir / "flow_daily_timeseries.csv"
    if not ts_path.exists():
        raise FileNotFoundError("flow_daily_timeseries.csv missing for reuse")
    ts_df = pd.read_csv(ts_path, dtype=str, keep_default_na=False)
    if set(TIMESERIES_COLUMNS).issubset(ts_df.columns):
        ts_df = ts_df[TIMESERIES_COLUMNS]
    if profiler is not None and hasattr(profiler, "record_cache_hit"):
        profiler.record_cache_hit()
    if profiler is not None and hasattr(profiler, "add_note"):
        profiler.add_note("Shadow flow dashboard: reused existing outputs")
    return _finalize_flow_dashboard(
        data_dir,
        output_dir,
        as_of=as_of,
        targets=targets,
        mcap_map=mcap_map,
        ts_df=ts_df,
        warnings=warnings,
        scored_meta=scored_meta,
    )


def run_flow_dashboard_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    max_tickers: int = 80,
    sleep_sec: float = 0.12,
    refresh_mode: str = "cache_first",
    profiler: object | None = None,
) -> FlowDashboardResult:
    """Build daily timeseries, streaks, leaderboards — shadow analytics only."""
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of = as_of[:10]
    warnings: list[str] = []
    targets = resolve_flow_target_tickers(data_dir, output_dir, max_tickers=max_tickers)
    mcap_map = _load_mcap_by_ticker(data_dir)
    scored_meta = _load_scored_meta(output_dir)
    universe_market = _load_universe_market(data_dir)

    ts_path = output_dir / "flow_daily_timeseries.csv"
    if refresh_mode == "cache_first" and ts_path.exists():
        try:
            cached_ts = pd.read_csv(ts_path, dtype=str, keep_default_na=False)
            if not cached_ts.empty and "date" in cached_ts.columns:
                max_date = str(cached_ts["date"].max())[:10]
                if max_date >= as_of:
                    warnings.append("flow dashboard: reused cached daily timeseries")
                    if profiler is not None and hasattr(profiler, "record_cache_hit"):
                        profiler.record_cache_hit()
                    if profiler is not None and hasattr(profiler, "add_note"):
                        profiler.add_note("Flow dashboard: cache-first reuse of flow_daily_timeseries.csv")
                    if profiler is not None:
                        from src.runtime.run_mode_contract import _record_flow_skip

                        _record_flow_skip(profiler, "flow_timeseries_unchanged")
                    ts_df = cached_ts
                    if set(TIMESERIES_COLUMNS).issubset(ts_df.columns):
                        ts_df = ts_df[TIMESERIES_COLUMNS]
                    return _finalize_flow_dashboard(
                        data_dir,
                        output_dir,
                        as_of=as_of,
                        targets=targets,
                        mcap_map=mcap_map,
                        ts_df=ts_df,
                        warnings=warnings,
                        scored_meta=scored_meta,
                    )
        except Exception as exc:
            warnings.append(f"flow cache read failed: {exc}")

    if profiler is not None and hasattr(profiler, "record_cache_miss"):
        profiler.record_cache_miss()
    if profiler is not None:
        from src.runtime.run_mode_contract import _record_flow_run

        _record_flow_run(
            profiler,
            executed=True,
            reason="new_trading_day" if refresh_mode == "cache_first" else "full_refresh",
            full_refresh=refresh_mode == "full",
        )

    all_daily: list[dict[str, Any]] = []
    stock = None
    try:
        from src.data_refresh.pykrx_client import import_pykrx_stock

        stock = import_pykrx_stock(data_dir)
    except Exception as exc:
        warnings.append(f"PyKRX unavailable: {exc}")

    for i, item in enumerate(targets):
        tk = _normalize_ticker(item["ticker"])
        name = str(item.get("name") or tk)
        market = universe_market.get(tk, "KOSPI")
        mcap = mcap_map.get(tk, 0.0)
        daily_rows: list[dict[str, Any]] = []
        if stock is not None:
            if profiler is not None and hasattr(profiler, "record_pykrx_call"):
                profiler.record_pykrx_call()
            daily_rows = fetch_daily_series_pykrx(
                stock, tk, name=name, market=market, as_of=as_of, mcap=mcap,
                lookback_days=25, sleep_sec=sleep_sec,
            )
        if not daily_rows:
            warnings.append(f"no daily series: {tk}")
            if profiler is not None and hasattr(profiler, "record_pykrx_failure"):
                profiler.record_pykrx_failure(tk)
        all_daily.extend(daily_rows)
        if sleep_sec and stock is not None and i < len(targets) - 1:
            time.sleep(sleep_sec * 0.5)

    ts_df = pd.DataFrame(all_daily)
    if not ts_df.empty:
        ts_df = ts_df[TIMESERIES_COLUMNS]
    return _finalize_flow_dashboard(
        data_dir,
        output_dir,
        as_of=as_of,
        targets=targets,
        mcap_map=mcap_map,
        ts_df=ts_df,
        warnings=warnings,
        scored_meta=scored_meta,
    )
