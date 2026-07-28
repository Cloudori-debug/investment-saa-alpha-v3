"""Fetch & assemble Method B input panel (isolated under outputs/backtest/)."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_refresh.market_indicators_refresh import _compute_kospi_metrics
from src.data_refresh.pykrx_client import import_pykrx_stock, to_compact_date

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
# OECD Korea 10Y government bond yield (monthly) — confirmed via FRED search 2026-07-16
KOREA_10Y_FRED_ID = "IRLTLT01KRM156N"

YAHOO_UA = "investment-saa-alpha-method-b/1.0"


def _yahoo_daily(symbol: str, *, range_str: str = "max") -> pd.Series:
    encoded = urllib.request.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        f"?interval=1d&range={range_str}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": YAHOO_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError(f"Yahoo empty chart: {symbol}")
    block = result[0]
    timestamps = block.get("timestamp") or []
    closes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    idx: list[pd.Timestamp] = []
    vals: list[float] = []
    for ts, c in zip(timestamps, closes):
        if c is None:
            continue
        idx.append(pd.Timestamp(datetime.fromtimestamp(int(ts), tz=timezone.utc).date()))
        vals.append(float(c))
    if not vals:
        raise ValueError(f"Yahoo no closes: {symbol}")
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name=symbol)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _fred_series(series_id: str, api_key: str, *, start: str = "2010-01-01") -> pd.Series:
    params = urllib.parse.urlencode(
        {
            "series_id": series_id,
            "api_key": api_key.strip(),
            "file_type": "json",
            "observation_start": start,
            "sort_order": "asc",
        }
    )
    url = f"{FRED_OBS_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": YAHOO_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    obs = payload.get("observations") or []
    idx: list[pd.Timestamp] = []
    vals: list[float] = []
    for row in obs:
        raw = str(row.get("value", "")).strip()
        if raw in {"", "."}:
            continue
        try:
            vals.append(float(raw))
            idx.append(pd.Timestamp(str(row["date"])[:10]))
        except (TypeError, ValueError, KeyError):
            continue
    if not vals:
        raise ValueError(f"FRED empty: {series_id}")
    return pd.Series(vals, index=pd.DatetimeIndex(idx), name=series_id).sort_index()


def fetch_kospi_closes(data_dir: Path, *, start: str = "2015-01-02", end: str | None = None) -> pd.Series:
    stock = import_pykrx_stock(data_dir)
    end = end or datetime.now().strftime("%Y-%m-%d")
    df = stock.get_index_ohlcv_by_date(to_compact_date(start), to_compact_date(end), "1001")
    if df is None or df.empty:
        raise ValueError("KOSPI OHLCV empty")
    closes = df["종가"].astype(float)
    closes.index = pd.to_datetime(closes.index).normalize()
    closes = closes[~closes.index.duplicated(keep="last")].sort_index()
    closes.name = "kospi"
    return closes


def _metrics_at(
    closes: pd.Series,
    as_of: pd.Timestamp,
    *,
    lookback_calendar_days: int = 400,
) -> dict[str, float]:
    """Point-in-time metrics via live `_compute_kospi_metrics` (종가 column)."""
    end = as_of.normalize()
    start = end - pd.Timedelta(days=lookback_calendar_days)
    window = closes.loc[(closes.index >= start) & (closes.index <= end)]
    if window.empty:
        raise ValueError(f"no closes for metrics at {end.date()}")
    fake = pd.DataFrame({"종가": window.astype(float).values}, index=window.index)
    metrics, _ = _compute_kospi_metrics(fake, existing=None)
    return metrics


def build_method_b_input(
    data_dir: Path,
    *,
    kospi_start: str = "2015-01-02",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return daily panel + provenance notes. Does not write under data/."""
    notes: dict[str, Any] = {
        "kospi_source": "pykrx get_index_ohlcv_by_date 1001",
        "yahoo_symbols": ["^GSPC", "^VIX", "KRW=X", "BZ=F", "GC=F"],
        "korea_10y_fred_id": KOREA_10Y_FRED_ID,
        "korea_10y_frequency": "monthly_ffill",
        "foreign_flow_3d": "neutral_fixed",
        "tier2": "excluded",
    }

    kospi = fetch_kospi_closes(data_dir, start=kospi_start)
    # Prefer long range strings that data-check confirmed
    try:
        sp500 = _yahoo_daily("^GSPC", range_str="3650d")
    except Exception:
        sp500 = _yahoo_daily("^GSPC", range_str="max")
    vix = _yahoo_daily("^VIX", range_str="3650d")
    usdkrw = _yahoo_daily("KRW=X", range_str="3650d")
    oil = _yahoo_daily("BZ=F", range_str="3650d")
    gold = _yahoo_daily("GC=F", range_str="3650d")

    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(data_dir)
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    korea_10y_daily: pd.Series | None = None
    if api_key:
        try:
            k10 = _fred_series(KOREA_10Y_FRED_ID, api_key, start="2014-01-01")
            # forward-fill monthly onto KOSPI calendar later
            korea_10y_daily = k10
            notes["korea_10y_status"] = "ok"
            notes["korea_10y_obs"] = int(len(k10))
        except Exception as exc:  # noqa: BLE001
            notes["korea_10y_status"] = f"failed: {exc}"
    else:
        notes["korea_10y_status"] = "FRED_API_KEY missing"

    # Master calendar = KOSPI trading days
    cal = kospi.index.sort_values()
    rows: list[dict[str, Any]] = []
    for dt in cal:
        try:
            k_m = _metrics_at(kospi, dt)
            s_win = sp500.loc[sp500.index <= dt]
            if s_win.empty:
                continue
            s_m = _metrics_at(s_win, dt)
        except Exception:
            continue

        def _last(series: pd.Series, default: float = 0.0) -> float:
            sub = series.loc[series.index <= dt]
            if sub.empty:
                return default
            return float(sub.iloc[-1])

        k10y = 0.0
        if korea_10y_daily is not None:
            sub = korea_10y_daily.loc[korea_10y_daily.index <= dt]
            if not sub.empty:
                k10y = float(sub.iloc[-1])

        v = _last(vix)
        u = _last(usdkrw)
        o = _last(oil)
        g = _last(gold)
        # Require core fields present (non-zero heuristic for yahoo)
        if v <= 0 or u <= 0 or s_m["kospi"] <= 0:
            continue

        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "kospi": k_m["kospi"],
                "kospi_recent_high": k_m["kospi_recent_high"],
                "kospi_200ma": k_m["kospi_200ma"],
                "sp500": s_m["kospi"],
                "sp500_recent_high": s_m["kospi_recent_high"],
                "vix": round(v, 4),
                "usdkrw": round(u, 4),
                "korea_10y": round(k10y, 4),
                "oil_brent": round(o, 4),
                "gold": round(g, 4),
                "foreign_flow_3d": "neutral",
                "regime": "NEUTRAL",
            }
        )

    panel = pd.DataFrame(rows)
    if panel.empty:
        raise RuntimeError("Method B panel empty after joins")

    notes["panel_rows"] = int(len(panel))
    notes["panel_start"] = str(panel["date"].iloc[0])
    notes["panel_end"] = str(panel["date"].iloc[-1])
    # Warmup: first date with enough prior KOSPI history (~200 trading days)
    notes["warmup_trading_days"] = 200
    if len(panel) > 200:
        notes["judgment_start"] = str(panel["date"].iloc[200])
    else:
        notes["judgment_start"] = str(panel["date"].iloc[0])
    return panel, notes
