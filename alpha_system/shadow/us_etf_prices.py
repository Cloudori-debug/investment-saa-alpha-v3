"""미국 상장 ETF/지수 일봉 · Yahoo chart (Review-only 검증용).

운영 PyKRX 경로와 분리 · Soft/target 불변.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import requests

CACHE_REL = Path("data") / "local" / "us_etf_prices.csv"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; alpha-screener-lab/1.0)"}
# 2000-01-01 ~ far future
_PERIOD1 = 946684800
_PERIOD2 = 1893456000


def cache_path(root: Path) -> Path:
    return Path(root) / CACHE_REL


def norm_us_ticker(raw: object) -> str:
    text = str(raw or "").strip().upper()
    if text.startswith("^"):
        return text
    return "".join(ch for ch in text if ch.isalnum())


def fetch_yahoo_adj_close(symbol: str) -> pd.Series:
    sym = norm_us_ticker(symbol)
    if not sym:
        return pd.Series(dtype=float)
    url = YAHOO_CHART.format(symbol=requests.utils.quote(sym))
    try:
        resp = requests.get(
            url,
            params={
                "period1": _PERIOD1,
                "period2": _PERIOD2,
                "interval": "1d",
                "events": "history",
            },
            headers=_UA,
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (OSError, ValueError, requests.RequestException):
        return pd.Series(dtype=float)
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return pd.Series(dtype=float)
    block = results[0]
    ts = block.get("timestamp") or []
    indicators = block.get("indicators") or {}
    adj = ((indicators.get("adjclose") or [{}])[0] or {}).get("adjclose")
    close = ((indicators.get("quote") or [{}])[0] or {}).get("close")
    vals = adj if adj is not None else close
    if not ts or vals is None:
        return pd.Series(dtype=float)
    rows: list[tuple[pd.Timestamp, float]] = []
    for t, v in zip(ts, vals):
        if v is None:
            continue
        try:
            rows.append(
                (
                    pd.Timestamp(datetime.fromtimestamp(int(t), tz=timezone.utc).date()),
                    float(v),
                )
            )
        except (TypeError, ValueError, OSError):
            continue
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({d: v for d, v in rows}).sort_index()
    return s[~s.index.duplicated(keep="last")].dropna()


def _read_cache(root: Path, tickers: Sequence[str]) -> pd.DataFrame:
    path = cache_path(root)
    if not path.is_file():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype=str)
    except (OSError, ValueError):
        return pd.DataFrame()
    if df.empty or "ticker" not in df.columns or "date" not in df.columns:
        return pd.DataFrame()
    need = {norm_us_ticker(t) for t in tickers}
    df["ticker"] = df["ticker"].map(norm_us_ticker)
    df = df[df["ticker"].isin(need)].copy()
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df.get("close"), errors="coerce")
    df = df.dropna(subset=["date", "close"])
    return (
        df.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
        .sort_index()
    )


def _write_cache(root: Path, panel: pd.DataFrame) -> None:
    if panel.empty:
        return
    path = cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    long = (
        panel.reset_index()
        .melt(id_vars=panel.index.name or "index", var_name="ticker", value_name="close")
        .rename(columns={panel.index.name or "index": "date"})
    )
    long = long.dropna(subset=["close"])
    long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
    long["ticker"] = long["ticker"].map(norm_us_ticker)
    # merge with existing other tickers
    if path.is_file():
        try:
            old = pd.read_csv(path, dtype=str)
            keep = old[~old["ticker"].map(norm_us_ticker).isin(set(long["ticker"]))]
            long = pd.concat([keep, long], ignore_index=True)
        except (OSError, ValueError, KeyError):
            pass
    try:
        long.to_csv(path, index=False, encoding="utf-8")
    except OSError:
        pass


def build_us_price_panel(
    root: Path,
    tickers: Iterable[str],
    *,
    ensure_fetch: bool = True,
    injected: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if injected is not None and not injected.empty:
        return injected.sort_index()
    tks = [norm_us_ticker(t) for t in tickers if norm_us_ticker(t)]
    tks = list(dict.fromkeys(tks))
    panel = _read_cache(root, tks)
    missing = [t for t in tks if t not in panel.columns or panel[t].dropna().empty]
    if ensure_fetch and missing:
        cols: dict[str, pd.Series] = {}
        for t in missing:
            s = fetch_yahoo_adj_close(t)
            if not s.empty:
                cols[t] = s
        if cols:
            fetched = pd.DataFrame(cols).sort_index()
            panel = fetched if panel.empty else panel.combine_first(fetched)
            _write_cache(root, panel[tks] if set(tks) <= set(panel.columns) else panel)
    cols_ok = [t for t in tks if t in panel.columns]
    if not cols_ok:
        return pd.DataFrame()
    return panel[cols_ok].sort_index().dropna(how="all")


__all__ = [
    "CACHE_REL",
    "build_us_price_panel",
    "cache_path",
    "fetch_yahoo_adj_close",
    "norm_us_ticker",
]
