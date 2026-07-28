from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from src.data_refresh.dart_client import DartApiError, DartCredentialsError, RateLimiter
from src.data_refresh.dart_corp_codes import build_ticker_corp_map
from src.data_refresh.dart_financials import (
    build_fundamental_record,
    compute_metrics,
    fetch_financial_accounts,
    find_latest_report,
)
from src.data_refresh.fundamentals_validate import FUNDAMENTAL_COLUMNS
from src.data_refresh.pykrx_bulk import Scope, _normalize_ticker, select_tickers_for_prices

ScopeLike = Literal["all", "liquid", "holdings", "prices"]


@dataclass
class DartEnrichResult:
    as_of: str
    requested: int
    enriched: int
    skipped: int
    errors: list[str] = field(default_factory=list)
    path: str = ""


def _load_valuation_overlay(data_dir: Path) -> dict[str, dict[str, float | None]]:
    path = data_dir / "fundamentals.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    overlay: dict[str, dict[str, float | None]] = {}
    val_cols = ("per", "pbr", "pcr", "psr", "ev_ebitda", "dividend_yield")
    for _, row in df.iterrows():
        ticker = _normalize_ticker(str(row["ticker"]))
        vals: dict[str, float | None] = {}
        for col in val_cols:
            raw = str(row.get(col, "")).strip()
            if raw:
                try:
                    vals[col] = float(raw)
                except ValueError:
                    vals[col] = None
        if vals:
            overlay[ticker] = vals
    return overlay


def resolve_tickers_for_dart(data_dir: Path, scope: ScopeLike, explicit: list[str] | None) -> list[str]:
    if explicit:
        return [_normalize_ticker(t) for t in explicit if str(t).strip()]
    if scope == "prices":
        path = data_dir / "prices.csv"
        if path.exists():
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            return [_normalize_ticker(t) for t in df["ticker"].tolist()]
    universe_path = data_dir / "universe.csv"
    if not universe_path.exists():
        return []
    universe = pd.read_csv(universe_path, dtype=str, keep_default_na=False)
    cap = pd.DataFrame()
    cap_path = data_dir / "prices.csv"
    if cap_path.exists() and scope in {"all", "liquid", "holdings"}:
        px = pd.read_csv(cap_path, dtype=str, keep_default_na=False)
        cap_rows = []
        for _, row in px.iterrows():
            t = _normalize_ticker(str(row["ticker"]))
            cap_rows.append(
                {
                    "ticker": t,
                    "시가총액": float(row.get("market_cap", 0) or 0),
                    "거래대금": float(row.get("trading_value_20d", 0) or 0),
                }
            )
        if cap_rows:
            cap = pd.DataFrame(cap_rows).set_index("ticker")
    scope_arg: Scope = "liquid" if scope == "prices" else scope  # type: ignore[assignment]
    if scope in {"all", "liquid", "holdings"}:
        return select_tickers_for_prices(universe, cap, scope=scope_arg, data_dir=data_dir, max_tickers=None)
    return universe[universe["security_type"] == "common_stock"]["ticker"].map(_normalize_ticker).tolist()


def enrich_fundamentals_from_dart(
    data_dir: Path,
    *,
    as_of: str,
    tickers: list[str] | None = None,
    scope: ScopeLike = "prices",
    sleep_sec: float = 0.12,
    merge_valuation: bool = True,
) -> DartEnrichResult:
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(data_dir)
    target_tickers = resolve_tickers_for_dart(data_dir, scope, tickers)
    corp_map = build_ticker_corp_map(data_dir, target_tickers)
    valuation = _load_valuation_overlay(data_dir) if merge_valuation else {}
    limiter = RateLimiter(min_interval_sec=sleep_sec)

    rows: list[dict] = []
    errors: list[str] = []
    skipped = 0

    for ticker in target_tickers:
        corp_code = corp_map.get(ticker)
        if not corp_code:
            skipped += 1
            errors.append(f"{ticker}: corp_code 없음")
            continue
        try:
            meta = find_latest_report(corp_code, as_of, limiter=limiter)
            if not meta:
                skipped += 1
                errors.append(f"{ticker}: 공시 없음 (as_of={as_of})")
                continue
            accounts = fetch_financial_accounts(meta, limiter=limiter)
            if not accounts:
                skipped += 1
                errors.append(f"{ticker}: 재무 계정 없음")
                continue
            metrics = compute_metrics(accounts, meta)
            record = build_fundamental_record(ticker, meta, metrics, valuation.get(ticker))
            rows.append(record)
        except DartApiError as exc:
            skipped += 1
            errors.append(f"{ticker}: {exc}")
        except Exception as exc:
            skipped += 1
            errors.append(f"{ticker}: {exc}")

    fund_path = data_dir / "fundamentals.csv"
    if rows:
        new_df = pd.DataFrame(rows)
        for col in FUNDAMENTAL_COLUMNS:
            if col not in new_df.columns:
                new_df[col] = None
        new_df = new_df[FUNDAMENTAL_COLUMNS]
        if fund_path.exists():
            old = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
            old["ticker"] = old["ticker"].map(_normalize_ticker)
            old = old[~old["ticker"].isin(new_df["ticker"].astype(str).map(_normalize_ticker))]
            merged = pd.concat([old, new_df.astype(object)], ignore_index=True)
        else:
            merged = new_df
        merged.to_csv(fund_path, index=False, encoding="utf-8-sig")

    return DartEnrichResult(
        as_of=as_of,
        requested=len(target_tickers),
        enriched=len(rows),
        skipped=skipped,
        errors=errors[:100],
        path=str(fund_path) if rows else "",
    )


def run_dart_enrich_or_raise(data_dir: Path, **kwargs) -> DartEnrichResult:
    try:
        return enrich_fundamentals_from_dart(data_dir, **kwargs)
    except DartCredentialsError:
        raise
