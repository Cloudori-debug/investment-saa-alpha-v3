from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.decision.shadow_performance import _pct_change, _row_on_or_before


def load_combined_prices(data_dir: Path) -> pd.DataFrame:
    """prices_history + prices.csv 병합 — Core benchmark·forward return용."""
    frames: list[pd.DataFrame] = []
    for name in ("prices_history.csv", "prices.csv"):
        path = data_dir / name
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype={"ticker": str}, keep_default_na=False)
        if df.empty or "date" not in df.columns or "close" not in df.columns:
            continue
        df = df[["date", "ticker", "close"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["ticker"] = df["ticker"].astype(str).str.strip().str.zfill(6)
        frames.append(df.dropna(subset=["date", "close"]))

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values(["ticker", "date"]).drop_duplicates(
        subset=["ticker", "date"], keep="last",
    )
    return merged.reset_index(drop=True)


def ticker_return_mtd_detail(prices: pd.DataFrame, ticker: str, as_of: str) -> dict:
    """월초(또는 월 첫 거래일 직전 종가) 대비 as_of MTD + 데이터 품질.

    Stale/single-point series must not masquerade as a true 0.0% return.
    """
    norm = ticker.zfill(6) if str(ticker).isdigit() else str(ticker)
    sub = prices[prices["ticker"] == norm].sort_values("date")
    if sub.empty:
        return {"return_mtd": None, "quality": "missing_ticker", "obs_count": 0}

    end = _row_on_or_before(sub, as_of)  # type: ignore[arg-type]
    if end is None:
        return {"return_mtd": None, "quality": "no_price_on_or_before_as_of", "obs_count": len(sub)}

    month_start = pd.Timestamp(as_of[:10]).replace(day=1)
    end_ts = pd.Timestamp(end["date"])
    days_stale = (pd.Timestamp(as_of[:10]) - end_ts).days
    if days_stale > 5:
        return {
            "return_mtd": None,
            "quality": "stale_price",
            "obs_count": int(len(sub)),
            "last_price_date": str(end_ts.date()),
            "days_stale": int(days_stale),
        }

    in_month = sub[sub["date"] >= month_start]
    if not in_month.empty:
        start = in_month.iloc[0]
        if start["date"] < end["date"]:
            return {
                "return_mtd": _pct_change(float(end["close"]), float(start["close"])),
                "quality": "ok",
                "obs_count": int(len(sub)),
                "start_date": str(pd.Timestamp(start["date"]).date()),
                "end_date": str(end_ts.date()),
            }
        # only one in-month print — need prior month close

    prior = sub[sub["date"] < month_start]
    if prior.empty:
        # Single observation / no prior month → cannot compute MTD (was wrongly 0.0)
        return {
            "return_mtd": None,
            "quality": "insufficient_history",
            "obs_count": int(len(sub)),
            "last_price_date": str(end_ts.date()),
        }
    start = prior.iloc[-1]
    if end["date"] <= start["date"]:
        return {
            "return_mtd": None,
            "quality": "insufficient_history",
            "obs_count": int(len(sub)),
            "last_price_date": str(end_ts.date()),
        }
    return {
        "return_mtd": _pct_change(float(end["close"]), float(start["close"])),
        "quality": "ok_from_prior_month_close",
        "obs_count": int(len(sub)),
        "start_date": str(pd.Timestamp(start["date"]).date()),
        "end_date": str(end_ts.date()),
    }


def ticker_return_mtd(prices: pd.DataFrame, ticker: str, as_of: str) -> float | None:
    """월초(또는 월 첫 거래일 직전 종가) 대비 as_of MTD. Stale → None (not 0.0)."""
    detail = ticker_return_mtd_detail(prices, ticker, as_of)
    ret = detail.get("return_mtd")
    return float(ret) if ret is not None else None


def ticker_cum_return_detail(
    prices: pd.DataFrame,
    ticker: str,
    start_date: str,
    end_date: str,
    *,
    max_stale_days: int = 5,
) -> dict:
    """Cumulative return from start_date → end_date. Never fabricates 0.0 on missing/stale."""
    norm = ticker.zfill(6) if str(ticker).isdigit() else str(ticker)
    if str(ticker).strip().upper() == "CASH":
        return {
            "return_pct": 0.0,
            "quality": "cash_fixed_zero",
            "obs_count": 0,
        }
    sub = prices[prices["ticker"] == norm].sort_values("date")
    if sub.empty:
        return {"return_pct": None, "quality": "missing_ticker", "obs_count": 0}

    end = _row_on_or_before(sub, end_date)  # type: ignore[arg-type]
    if end is None:
        return {
            "return_pct": None,
            "quality": "no_price_on_or_before_as_of",
            "obs_count": int(len(sub)),
        }
    end_ts = pd.Timestamp(end["date"])
    days_stale = (pd.Timestamp(end_date[:10]) - end_ts).days
    if days_stale > max_stale_days:
        return {
            "return_pct": None,
            "quality": "stale_price",
            "obs_count": int(len(sub)),
            "last_price_date": str(end_ts.date()),
            "days_stale": int(days_stale),
        }

    # Prefer first print on/after inception; else last print on/before inception
    start_ts = pd.Timestamp(start_date[:10])
    on_or_after = sub[sub["date"] >= start_ts]
    if not on_or_after.empty:
        start = on_or_after.iloc[0]
        start_quality = "ok_from_first_on_or_after_inception"
    else:
        prior = sub[sub["date"] <= start_ts]
        if prior.empty:
            return {
                "return_pct": None,
                "quality": "missing_inception_price",
                "obs_count": int(len(sub)),
                "last_price_date": str(end_ts.date()),
            }
        start = prior.iloc[-1]
        start_quality = "ok_from_prior_close"

    if end["date"] <= start["date"]:
        return {
            "return_pct": None,
            "quality": "insufficient_history",
            "obs_count": int(len(sub)),
            "start_date": str(pd.Timestamp(start["date"]).date()),
            "end_date": str(end_ts.date()),
        }
    return {
        "return_pct": _pct_change(float(end["close"]), float(start["close"])),
        "quality": start_quality,
        "obs_count": int(len(sub)),
        "start_date": str(pd.Timestamp(start["date"]).date()),
        "end_date": str(end_ts.date()),
    }


def ticker_cum_return(
    prices: pd.DataFrame,
    ticker: str,
    start_date: str,
    end_date: str,
    *,
    max_stale_days: int = 5,
) -> float | None:
    """Cumulative % return start→end. Missing/stale → None (not 0.0). CASH → 0.0."""
    detail = ticker_cum_return_detail(
        prices, ticker, start_date, end_date, max_stale_days=max_stale_days,
    )
    ret = detail.get("return_pct")
    return float(ret) if ret is not None else None


def core_tickers_from_reference(data_dir: Path) -> set[str]:
    from src.exposure.core_saa_reference import load_core_saa_reference

    ref = load_core_saa_reference(data_dir)
    if not ref:
        return set()
    out: set[str] = set()
    for asset in ref.get("assets") or []:
        t = asset.get("ticker")
        if t:
            out.add(str(t).strip().zfill(6))
    return out
