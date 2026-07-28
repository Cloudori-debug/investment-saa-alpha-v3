from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.schemas import FundamentalRecord, PriceRecord, UniverseRecord
from src.config import load_yaml
from src.field_normalize import normalize_sector


def _bool_val(val: str) -> bool:
    return str(val).strip().lower() in {"true", "1", "yes", "y"}


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def load_universe(path: Path) -> list[UniverseRecord]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows: list[UniverseRecord] = []
    for r in df.to_dict(orient="records"):
        rows.append(
            UniverseRecord(
                ticker=_normalize_ticker(r["ticker"]),
                name=str(r["name"]).strip(),
                market=str(r.get("market", "KOSPI")).strip(),
                security_type=str(r.get("security_type", "common_stock")).strip(),
                sector=normalize_sector(r.get("sector", "")),
                industry=str(r.get("industry", "")).strip(),
                listed_date=str(r.get("listed_date", "")).strip(),
                is_preferred=_bool_val(r.get("is_preferred", "false")),
                is_etf_etn=_bool_val(r.get("is_etf_etn", "false")),
                is_reit=_bool_val(r.get("is_reit", "false")),
                is_spac=_bool_val(r.get("is_spac", "false")),
                is_trading_halt=_bool_val(r.get("is_trading_halt", "false")),
                is_administrative_issue=_bool_val(r.get("is_administrative_issue", "false")),
                audit_opinion=str(r.get("audit_opinion", "clean")).strip().lower(),
                capital_impairment=_bool_val(r.get("capital_impairment", "false")),
            )
        )
    return rows


def load_fundamentals(path: Path) -> list[FundamentalRecord]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    float_cols = (
        "roe", "roa", "operating_margin", "gross_profitability", "debt_ratio",
        "interest_coverage", "per", "pbr", "pcr", "psr", "ev_ebitda", "dividend_yield",
        "fcf", "operating_cash_flow", "net_income", "earnings_yoy",
    )
    rows: list[FundamentalRecord] = []
    for r in df.to_dict(orient="records"):
        for col in float_cols:
            if col in r and str(r[col]).strip():
                r[col] = float(r[col])
            else:
                r[col] = None
        rows.append(FundamentalRecord.model_validate({**r, "ticker": _normalize_ticker(r["ticker"])}))
    return rows


def load_prices(path: Path, as_of: str | None = None) -> list[PriceRecord]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    if as_of:
        df = df[df["date"] <= as_of[:10]]
    if df.empty:
        return []
    df = df.sort_values(["ticker", "date"], na_position="last")
    df = df.drop_duplicates(subset=["ticker"], keep="last")
    float_cols = (
        "close", "market_cap", "trading_value_20d", "trading_value_60d",
        "return_1m", "return_3m", "return_6m", "return_12m", "return_12m_ex_1m",
        "high_52w", "distance_from_52w_high", "volatility_60d",
    )
    rows: list[PriceRecord] = []
    for r in df.to_dict(orient="records"):
        for col in float_cols:
            if col in r and str(r[col]).strip():
                r[col] = float(r[col])
            else:
                r[col] = 0.0 if col != "distance_from_52w_high" else 0.0
        rows.append(PriceRecord.model_validate({**r, "ticker": _normalize_ticker(r["ticker"])}))
    return rows


def load_universe_filter_config(path: Path) -> dict:
    from src.alpha.universe_presets import resolve_universe_filter_config

    return resolve_universe_filter_config(load_yaml(path))


def load_alpha_scoring_config(path: Path) -> dict:
    return load_yaml(path)
