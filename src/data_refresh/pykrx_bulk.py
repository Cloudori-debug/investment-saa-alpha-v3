from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from src.config import load_yaml
from src.data_loader import load_positions, load_target_portfolio
from src.data_refresh.pykrx_client import (
    import_pykrx_stock,
    lookback_start,
    resolve_trading_date,
    to_compact_date,
)
from src.data_refresh.universe_sync import UNIVERSE_COLUMNS

Scope = Literal["all", "liquid", "holdings"]


@dataclass
class BulkCollectResult:
    as_of: str
    universe_count: int
    prices_count: int
    fundamentals_count: int
    scope: str
    warnings: list[str] = field(default_factory=list)
    paths: dict[str, str] = field(default_factory=dict)
    dart_enriched: int = 0


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _bool_str(val: bool) -> str:
    return "true" if val else "false"


def classify_security(name: str, ticker: str, etf_set: set[str], etn_set: set[str]) -> dict[str, Any]:
    name = name or ""
    is_etf = ticker in etf_set
    is_etn = ticker in etn_set
    is_preferred = name.endswith("우") or name.endswith("우B") or name.endswith("우(전환)")
    if not is_preferred and ticker.isdigit() and len(ticker) == 6:
        # KOSPI 우선주: 종종 맨 끝이 5/7/8/9 (휴리스틱)
        if ticker.endswith(("5", "7", "8", "9")) and "우" in name:
            is_preferred = True
    is_reit = "리츠" in name or name.upper().endswith("REIT")
    is_spac = "스팩" in name.upper() or "SPAC" in name.upper()
    if is_etf or is_etn:
        security_type = "etf_etn"
    elif is_preferred:
        security_type = "preferred_stock"
    elif is_reit:
        security_type = "reit"
    elif is_spac:
        security_type = "spac"
    else:
        security_type = "common_stock"
    return {
        "is_preferred": is_preferred,
        "is_etf_etn": is_etf or is_etn,
        "is_reit": is_reit,
        "is_spac": is_spac,
        "security_type": security_type,
    }


def merge_manual_universe_fields(existing: pd.DataFrame | None, new_df: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        return new_df
    manual_cols = [
        "is_trading_halt", "is_administrative_issue", "audit_opinion", "capital_impairment", "listed_date",
    ]
    keep = existing.copy()
    keep["ticker"] = keep["ticker"].map(_normalize_ticker)
    new_df = new_df.copy()
    new_df["ticker"] = new_df["ticker"].map(_normalize_ticker)
    merged = new_df.merge(keep[["ticker"] + [c for c in manual_cols if c in keep.columns]], on="ticker", how="left", suffixes=("", "_old"))
    for col in manual_cols:
        old_col = f"{col}_old"
        if old_col in merged.columns:
            old_vals = merged[old_col].astype(str).str.strip()
            has_old = old_vals.ne("") & ~old_vals.str.lower().isin({"nan", "none"})
            merged[col] = merged[old_col].where(has_old, merged[col])
            merged.drop(columns=[old_col], inplace=True)
    return merged


def normalize_universe_defaults(df: pd.DataFrame) -> pd.DataFrame:
    """PyKRX bulk 후 빈 governance 필드를 기본값으로 채움."""
    out = df.copy()
    defaults = {
        "is_trading_halt": "false",
        "is_administrative_issue": "false",
        "audit_opinion": "clean",
        "capital_impairment": "false",
        "listed_date": "2010-01-01",
    }
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
        else:
            empty = out[col].astype(str).str.strip().isin({"", "nan", "none"})
            out.loc[empty, col] = default
    return out


def fetch_kospi_universe(stock: Any, as_of: str) -> pd.DataFrame:
    return _fetch_market_universe(stock, as_of, "KOSPI")


def fetch_kosdaq_universe(stock: Any, as_of: str) -> pd.DataFrame:
    return _fetch_market_universe(stock, as_of, "KOSDAQ")


def _fetch_market_universe(stock: Any, as_of: str, market: str) -> pd.DataFrame:
    compact = to_compact_date(as_of)
    tickers = [_normalize_ticker(t) for t in stock.get_market_ticker_list(compact, market=market)]
    if not tickers:
        raise RuntimeError(f"{market} ticker 목록 없음 (as_of={as_of}). KRX_ID/KRX_PW 확인.")

    etf_set: set[str] = set()
    etn_set: set[str] = set()
    try:
        etf_set = {_normalize_ticker(t) for t in stock.get_etf_ticker_list(compact)}
    except Exception:
        pass
    try:
        etn_set = {_normalize_ticker(t) for t in stock.get_etn_ticker_list(compact)}
    except Exception:
        pass

    rows: list[dict[str, str]] = []
    for ticker in tickers:
        try:
            name = stock.get_market_ticker_name(ticker)
        except Exception:
            name = ticker
        meta = classify_security(str(name), ticker, etf_set, etn_set)
        rows.append(
            {
                "ticker": ticker,
                "name": str(name),
                "market": market,
                "security_type": meta["security_type"],
                "sector": "",
                "industry": "",
                "listed_date": "2010-01-01",
                "is_preferred": _bool_str(meta["is_preferred"]),
                "is_etf_etn": _bool_str(meta["is_etf_etn"]),
                "is_reit": _bool_str(meta["is_reit"]),
                "is_spac": _bool_str(meta["is_spac"]),
                "is_trading_halt": "false",
                "is_administrative_issue": "false",
                "audit_opinion": "clean",
                "capital_impairment": "false",
            }
        )
    return pd.DataFrame(rows)


def _merge_universe_frames(
    existing: pd.DataFrame | None,
    kospi_df: pd.DataFrame,
    kosdaq_df: pd.DataFrame,
) -> pd.DataFrame:
    """Keep non-KOSDAQ rows from existing, replace KOSPI/KOSDAQ from fresh fetch."""
    parts = [kospi_df, kosdaq_df]
    if existing is not None and not existing.empty:
        ex = existing.copy()
        ex["ticker"] = ex["ticker"].map(_normalize_ticker)
        ex["market"] = ex.get("market", "KOSPI").astype(str).str.upper()
        other = ex[~ex["market"].isin({"KOSPI", "KOSDAQ"})]
        if not other.empty:
            parts.append(other)
    combined = pd.concat(parts, ignore_index=True)
    combined["ticker"] = combined["ticker"].map(_normalize_ticker)
    combined = combined.drop_duplicates(subset=["ticker"], keep="last")
    return merge_manual_universe_fields(existing, combined)


def quick_prices_from_cap_snapshot(
    cap_snapshot: pd.DataFrame,
    as_of: str,
    *,
    min_market_cap: float = 100_000_000_000,
    min_trading_value: float = 1_000_000_000,
) -> pd.DataFrame:
    """Bootstrap price rows from a single-day cap snapshot (tv20 proxy = day turnover)."""
    rows: list[dict[str, Any]] = []
    for ticker, row in cap_snapshot.iterrows():
        t = _normalize_ticker(str(ticker))
        mcap = float(row.get("시가총액", 0) or 0)
        tv = float(row.get("거래대금", 0) or 0)
        if mcap < min_market_cap or tv < min_trading_value:
            continue
        close = float(row.get("종가", 0) or 0)
        rows.append(
            {
                "date": as_of,
                "ticker": t,
                "close": int(close),
                "market_cap": int(mcap),
                "trading_value_20d": int(tv),
                "trading_value_60d": int(tv),
                "return_1m": 0.0,
                "return_3m": 0.0,
                "return_6m": 0.0,
                "return_12m": 0.0,
                "return_12m_ex_1m": 0.0,
                "high_52w": int(close),
                "distance_from_52w_high": 1.0 if close else 0.0,
                "volatility_60d": 0.0,
            }
        )
    return pd.DataFrame(rows)


@dataclass
class KosdaqSyncResult:
    as_of: str
    kosdaq_universe_count: int
    kosdaq_prices_count: int
    total_universe_count: int
    warnings: list[str] = field(default_factory=list)


def run_kosdaq_universe_sync(
    data_dir: Path,
    *,
    as_of: str | None = None,
    merge_existing: bool = True,
    bootstrap_prices: bool = True,
) -> KosdaqSyncResult:
    """Sync KOSDAQ common stocks into universe.csv and bootstrap liquid KOSDAQ prices."""
    stock = import_pykrx_stock(data_dir)
    as_of_date = resolve_trading_date(stock, as_of)
    warnings: list[str] = []

    kosdaq_df = fetch_kosdaq_universe(stock, as_of_date)
    universe_path = data_dir / "universe.csv"
    existing = (
        pd.read_csv(universe_path, dtype=str, keep_default_na=False)
        if merge_existing and universe_path.exists()
        else None
    )
    if existing is not None and not existing.empty:
        kospi_existing = existing[existing.get("market", "KOSPI").astype(str).str.upper() == "KOSPI"]
    else:
        kospi_existing = pd.DataFrame(columns=UNIVERSE_COLUMNS)

    universe_df = _merge_universe_frames(existing, kospi_existing, kosdaq_df)
    universe_df = normalize_universe_defaults(universe_df)
    universe_df = universe_df[UNIVERSE_COLUMNS]
    universe_path.parent.mkdir(parents=True, exist_ok=True)
    universe_df.to_csv(universe_path, index=False, encoding="utf-8-sig")

    kosdaq_prices_count = 0
    if bootstrap_prices:
        compact = to_compact_date(as_of_date)
        cap_kosdaq = stock.get_market_cap(compact, market="KOSDAQ")
        prices_df = quick_prices_from_cap_snapshot(cap_kosdaq, as_of_date)
        kosdaq_prices_count = len(prices_df)
        prices_path = data_dir / "prices.csv"
        if not prices_df.empty:
            if prices_path.exists():
                from src.data_refresh.price_store import merge_prices_dataframes

                old = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
                kosdaq_tickers = set(prices_df["ticker"].astype(str))
                old = old[~old["ticker"].astype(str).isin(kosdaq_tickers)]
                merged = merge_prices_dataframes(old, prices_df.astype(str))
                merged.to_csv(prices_path, index=False, encoding="utf-8-sig")
            else:
                prices_df.to_csv(prices_path, index=False, encoding="utf-8-sig")

        fund_path = data_dir / "fundamentals.csv"
        fund_kosdaq = fetch_fundamentals_bulk(stock, as_of_date, market="KOSDAQ")
        if not fund_kosdaq.empty:
            if fund_path.exists() and merge_existing:
                old_f = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
                old_f["ticker"] = old_f["ticker"].map(_normalize_ticker)
                fund_kosdaq["ticker"] = fund_kosdaq["ticker"].map(_normalize_ticker)
                merged_f = pd.concat(
                    [old_f[~old_f["ticker"].isin(fund_kosdaq["ticker"])], fund_kosdaq],
                    ignore_index=True,
                )
                merged_f = normalize_fundamentals_pit(merged_f)
                merged_f.to_csv(fund_path, index=False, encoding="utf-8-sig")
            else:
                fund_kosdaq = normalize_fundamentals_pit(fund_kosdaq)
                fund_kosdaq.to_csv(fund_path, index=False, encoding="utf-8-sig")
        else:
            warnings.append("KOSDAQ fundamentals bulk fetch 빈 결과")

    kosdaq_n = int((universe_df["market"].astype(str).str.upper() == "KOSDAQ").sum())
    return KosdaqSyncResult(
        as_of=as_of_date,
        kosdaq_universe_count=kosdaq_n,
        kosdaq_prices_count=kosdaq_prices_count,
        total_universe_count=len(universe_df),
        warnings=warnings,
    )


def _load_liquidity_config(data_dir: Path) -> dict[str, float]:
    from src.alpha.loaders import load_universe_filter_config

    cfg = load_universe_filter_config(data_dir / "universe_filter.yaml").get("liquidity", {})
    return {
        "min_market_cap": float(cfg.get("min_market_cap_krw", 0)),
        "min_tv20": float(cfg.get("min_20d_avg_trading_value_krw", 0)),
        "min_tv60": float(cfg.get("min_60d_avg_trading_value_krw", 0)),
    }


def select_tickers_for_prices(
    universe_df: pd.DataFrame,
    cap_snapshot: pd.DataFrame,
    *,
    scope: Scope,
    data_dir: Path,
    max_tickers: int | None,
) -> list[str]:
    liq = _load_liquidity_config(data_dir)
    common = universe_df[
        (universe_df["security_type"] == "common_stock")
        & (universe_df["is_preferred"] == "false")
        & (universe_df["is_etf_etn"] == "false")
    ].copy()
    tickers = common["ticker"].tolist()

    if scope == "holdings":
        wanted: set[str] = set()
        for row in load_positions(data_dir / "positions.csv"):
            if row.asset_group == "kr_alpha":
                wanted.add(_normalize_ticker(row.ticker))
        for row in load_target_portfolio(data_dir / "target_portfolio.csv"):
            if row.asset_group == "kr_alpha":
                wanted.add(_normalize_ticker(row.ticker))
        tickers = [t for t in tickers if t in wanted] or sorted(wanted)

    if scope in {"all", "liquid"} and not cap_snapshot.empty:
        cap = cap_snapshot.copy()
        cap.index = cap.index.map(_normalize_ticker)
        filtered = []
        for t in tickers:
            if t not in cap.index:
                continue
            row = cap.loc[t]
            mcap = float(row.get("시가총액", 0))
            tv = float(row.get("거래대금", 0))
            if scope == "liquid":
                if liq["min_market_cap"] and mcap < liq["min_market_cap"]:
                    continue
                if liq["min_tv20"] and tv < liq["min_tv20"]:
                    continue
            filtered.append(t)
        if filtered:
            tickers = filtered

    if max_tickers and len(tickers) > max_tickers:
        tickers = tickers[:max_tickers]
    return tickers


def _compute_returns(closes: pd.Series) -> dict[str, float]:
    if closes.empty:
        return {}
    closes = closes.sort_index()
    last = float(closes.iloc[-1])
    out: dict[str, float] = {}
    for label, days in (("return_1m", 21), ("return_3m", 63), ("return_6m", 126), ("return_12m", 252)):
        if len(closes) > days:
            base = float(closes.iloc[-days - 1])
            out[label] = round((last / base) - 1.0, 4) if base else 0.0
    if "return_12m" in out and "return_1m" in out:
        out["return_12m_ex_1m"] = round(out["return_12m"] - out["return_1m"], 4)
    if len(closes) >= 60:
        rets = closes.pct_change().dropna().tail(60)
        out["volatility_60d"] = round(float(rets.std()), 4) if len(rets) else 0.0
    high_52w = float(closes.tail(252).max()) if len(closes) else last
    out["high_52w"] = high_52w
    out["distance_from_52w_high"] = round(last / high_52w, 4) if high_52w else 0.0
    return out


def build_price_row(
    ticker: str,
    as_of: str,
    ohlcv: pd.DataFrame,
    cap_hist: pd.DataFrame | None,
    cap_today: pd.Series | None,
) -> dict[str, Any]:
    close = float(ohlcv.iloc[-1]["종가"]) if not ohlcv.empty else 0.0
    rets = _compute_returns(ohlcv["종가"]) if not ohlcv.empty else {}

    mcap = float(cap_today["시가총액"]) if cap_today is not None else 0.0
    tv20 = tv60 = 0.0
    if cap_hist is not None and not cap_hist.empty and "거래대금" in cap_hist.columns:
        tv = cap_hist["거래대금"].astype(float)
        tv20 = float(tv.tail(20).mean()) if len(tv) else 0.0
        tv60 = float(tv.tail(60).mean()) if len(tv) else 0.0

    return {
        "date": as_of,
        "ticker": ticker,
        "close": int(close),
        "market_cap": int(mcap),
        "trading_value_20d": int(tv20),
        "trading_value_60d": int(tv60),
        "return_1m": rets.get("return_1m", 0.0),
        "return_3m": rets.get("return_3m", 0.0),
        "return_6m": rets.get("return_6m", 0.0),
        "return_12m": rets.get("return_12m", 0.0),
        "return_12m_ex_1m": rets.get("return_12m_ex_1m", 0.0),
        "high_52w": int(rets.get("high_52w", close)),
        "distance_from_52w_high": rets.get("distance_from_52w_high", 0.0),
        "volatility_60d": rets.get("volatility_60d", 0.0),
    }


def fetch_prices_for_tickers(
    stock: Any,
    tickers: list[str],
    as_of: str,
    *,
    ticker_markets: dict[str, str] | None = None,
    sleep_sec: float = 0.15,
) -> pd.DataFrame:
    compact_end = to_compact_date(as_of)
    compact_start = to_compact_date(lookback_start(as_of, 400))
    cap_by_market: dict[str, pd.DataFrame] = {}
    for market in {"KOSPI", "KOSDAQ"}:
        try:
            cap_df = stock.get_market_cap(compact_end, market=market)
            cap_df.index = cap_df.index.map(_normalize_ticker)
            cap_by_market[market] = cap_df
        except Exception:
            cap_by_market[market] = pd.DataFrame()

    rows: list[dict] = []
    for i, ticker in enumerate(tickers):
        market = (ticker_markets or {}).get(ticker, "KOSPI").upper()
        cap_today_df = cap_by_market.get(market, pd.DataFrame())
        try:
            ohlcv = stock.get_market_ohlcv(compact_start, compact_end, ticker)
            cap_hist = stock.get_market_cap(compact_start, compact_end, ticker)
            cap_today = cap_today_df.loc[ticker] if ticker in cap_today_df.index else None
            rows.append(build_price_row(ticker, as_of, ohlcv, cap_hist, cap_today))
        except Exception:
            continue
        if sleep_sec and i < len(tickers) - 1:
            time.sleep(sleep_sec)
    return pd.DataFrame(rows)


def normalize_fundamentals_pit(df: pd.DataFrame) -> pd.DataFrame:
    """usable_from_date <= report_date (PIT 게이트 통과)."""
    out = df.copy()
    for idx, row in out.iterrows():
        report = str(row.get("report_date", "")).strip()
        usable = str(row.get("usable_from_date", "")).strip()
        if report and (not usable or usable > report):
            out.at[idx, "usable_from_date"] = report
    return out


def fetch_fundamentals_bulk(stock: Any, as_of: str, market: str = "KOSPI") -> pd.DataFrame:
    compact = to_compact_date(as_of)
    df = stock.get_market_fundamental(compact, market=market)
    if df.empty:
        return pd.DataFrame()

    usable = as_of
    rows: list[dict] = []
    for ticker, row in df.iterrows():
        ticker = _normalize_ticker(str(ticker))
        per = float(row.get("PER", 0) or 0)
        pbr = float(row.get("PBR", 0) or 0)
        div = float(row.get("DIV", 0) or 0)
        eps = float(row.get("EPS", 0) or 0)
        bps = float(row.get("BPS", 0) or 0)
        rows.append(
            {
                "ticker": ticker,
                "period_end": as_of[:4] + "-12-31",
                "report_date": as_of,
                "usable_from_date": usable,
                "roe": round((eps / bps) * 100, 2) if bps else None,
                "roa": None,
                "operating_margin": None,
                "gross_profitability": None,
                "debt_ratio": None,
                "interest_coverage": None,
                "per": per if per > 0 else None,
                "pbr": pbr if pbr > 0 else None,
                "pcr": None,
                "psr": None,
                "ev_ebitda": None,
                "dividend_yield": div if div > 0 else None,
                "fcf": None,
                "operating_cash_flow": None,
                "net_income": eps if eps != 0 else None,
                "earnings_yoy": None,
            }
        )
    return pd.DataFrame(rows)


def run_pykrx_bulk_collect(
    data_dir: Path,
    *,
    as_of: str | None = None,
    scope: Scope = "liquid",
    max_tickers: int | None = None,
    sleep_sec: float = 0.15,
    merge_existing_universe: bool = True,
    write_history: bool = True,
    enrich_dart: bool = True,
) -> BulkCollectResult:
    stock = import_pykrx_stock(data_dir)
    as_of_date = resolve_trading_date(stock, as_of)
    warnings: list[str] = []

    universe_new_kospi = fetch_kospi_universe(stock, as_of_date)
    universe_new_kosdaq = fetch_kosdaq_universe(stock, as_of_date)
    universe_path = data_dir / "universe.csv"
    existing = pd.read_csv(universe_path, dtype=str, keep_default_na=False) if merge_existing_universe and universe_path.exists() else None
    universe_df = _merge_universe_frames(existing, universe_new_kospi, universe_new_kosdaq)
    universe_df = normalize_universe_defaults(universe_df)
    universe_df = universe_df[UNIVERSE_COLUMNS]
    universe_path.parent.mkdir(parents=True, exist_ok=True)
    universe_df.to_csv(universe_path, index=False, encoding="utf-8-sig")

    compact = to_compact_date(as_of_date)
    cap_kospi = stock.get_market_cap(compact, market="KOSPI")
    cap_kosdaq = stock.get_market_cap(compact, market="KOSDAQ")
    cap_snapshot = pd.concat([cap_kospi, cap_kosdaq])
    ticker_markets = {
        _normalize_ticker(str(r["ticker"])): str(r.get("market", "KOSPI")).upper()
        for _, r in universe_df.iterrows()
    }
    tickers = select_tickers_for_prices(
        universe_df, cap_snapshot, scope=scope, data_dir=data_dir, max_tickers=max_tickers
    )
    if not tickers:
        warnings.append("prices 대상 ticker 없음")
        prices_df = pd.DataFrame()
    else:
        prices_df = fetch_prices_for_tickers(
            stock, tickers, as_of_date, ticker_markets=ticker_markets, sleep_sec=sleep_sec
        )

    prices_path = data_dir / "prices.csv"
    if not prices_df.empty:
        if prices_path.exists():
            from src.data_refresh.price_store import merge_prices_dataframes

            old = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
            prices_df = merge_prices_dataframes(old, prices_df.astype(str))
        prices_df.to_csv(prices_path, index=False, encoding="utf-8-sig")
        if write_history:
            from src.data_refresh.prices_refresh import append_prices_history

            append_prices_history(data_dir)

    fund_path = data_dir / "fundamentals.csv"
    fund_kospi = fetch_fundamentals_bulk(stock, as_of_date, market="KOSPI")
    fund_kosdaq = fetch_fundamentals_bulk(stock, as_of_date, market="KOSDAQ")
    fund_df = pd.concat([fund_kospi, fund_kosdaq], ignore_index=True) if not fund_kosdaq.empty else fund_kospi
    if not fund_df.empty:
        if fund_path.exists() and merge_existing_universe:
            old = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
            old["ticker"] = old["ticker"].map(_normalize_ticker)
            fund_df["ticker"] = fund_df["ticker"].map(_normalize_ticker)
            merged = pd.concat([old[~old["ticker"].isin(fund_df["ticker"])], fund_df], ignore_index=True)
            merged = normalize_fundamentals_pit(merged)
            merged.to_csv(fund_path, index=False, encoding="utf-8-sig")
            fund_df = merged
        else:
            fund_df = normalize_fundamentals_pit(fund_df)
            fund_df.to_csv(fund_path, index=False, encoding="utf-8-sig")
    else:
        warnings.append("fundamentals bulk fetch 실패 또는 빈 결과")

    dart_enriched = 0
    if enrich_dart and tickers:
        try:
            from src.data_refresh.dart_enrich import enrich_fundamentals_from_dart

            dart = enrich_fundamentals_from_dart(
                data_dir,
                as_of=as_of_date,
                tickers=tickers,
                scope="prices",
                sleep_sec=sleep_sec,
            )
            dart_enriched = dart.enriched
            if dart.errors:
                warnings.append(f"DART 보강: {dart.enriched}/{dart.requested} 성공, {dart.skipped} 스킵")
            fund_path = data_dir / "fundamentals.csv"
            if fund_path.exists():
                fund_df = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
        except Exception as exc:
            warnings.append(f"DART 보강 스킵: {exc}")

    return BulkCollectResult(
        as_of=as_of_date,
        universe_count=len(universe_df),
        prices_count=len(prices_df),
        fundamentals_count=len(fund_df) if not fund_df.empty else 0,
        scope=scope,
        warnings=warnings,
        dart_enriched=dart_enriched,
        paths={
            "universe": str(universe_path),
            "prices": str(prices_path) if not prices_df.empty else "",
            "fundamentals": str(fund_path) if not fund_df.empty else "",
        },
    )
