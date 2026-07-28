from __future__ import annotations

from datetime import datetime
from typing import Any

from src.alpha.schemas import UniverseRecord, make_excluded


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _days_listed(listed_date: str, as_of: str) -> int:
    start = _parse_date(listed_date)
    end = _parse_date(as_of)
    if not start or not end:
        return 9999
    return (end - start).days


def filter_universe(
    universe: list[UniverseRecord],
    prices_by_ticker: dict[str, Any],
    config: dict[str, Any],
    as_of: str,
):
    rules = config.get("universe", {})
    include = rules.get("include", {})
    exclude = rules.get("exclude", {})
    liq = config.get("liquidity", {})

    min_mcap = float(liq.get("min_market_cap_krw", 0))
    min_tv20 = float(liq.get("min_20d_avg_trading_value_krw", 0))
    min_tv60 = float(liq.get("min_60d_avg_trading_value_krw", 0))
    min_days = int(liq.get("min_listed_days", 252))

    allowed_markets = {m.upper() for m in include.get("market", ["KOSPI"])}
    allowed_types = {t.lower() for t in include.get("security_type", ["common_stock"])}

    passed: list[UniverseRecord] = []
    excluded = []

    for rec in universe:
        if rec.market.upper() not in allowed_markets:
            excluded.append(make_excluded(rec.ticker, rec.name, "시장 제외", "market"))
            continue
        if exclude.get("preferred_stock") and rec.is_preferred:
            excluded.append(make_excluded(rec.ticker, rec.name, "우선주 제외", "preferred_stock"))
            continue
        if exclude.get("etf_etn") and rec.is_etf_etn:
            excluded.append(make_excluded(rec.ticker, rec.name, "ETF/ETN 제외", "etf_etn"))
            continue
        if exclude.get("reit") and rec.is_reit:
            excluded.append(make_excluded(rec.ticker, rec.name, "리츠 제외", "reit"))
            continue
        if exclude.get("spac") and rec.is_spac:
            excluded.append(make_excluded(rec.ticker, rec.name, "SPAC 제외", "spac"))
            continue
        if exclude.get("trading_halt") and rec.is_trading_halt:
            excluded.append(make_excluded(rec.ticker, rec.name, "거래정지", "trading_halt"))
            continue
        if exclude.get("administrative_issue") and rec.is_administrative_issue:
            excluded.append(make_excluded(rec.ticker, rec.name, "관리종목", "administrative_issue"))
            continue
        if exclude.get("capital_impairment") and rec.capital_impairment:
            excluded.append(make_excluded(rec.ticker, rec.name, "자본잠식", "capital_impairment"))
            continue
        if exclude.get("audit_opinion_not_clean") and rec.audit_opinion not in {"clean", "unqualified", "qualified"}:
            excluded.append(make_excluded(rec.ticker, rec.name, f"감사의견 {rec.audit_opinion}", "audit_opinion"))
            continue
        if rec.security_type.lower() not in allowed_types:
            excluded.append(make_excluded(rec.ticker, rec.name, "증권유형 제외", "security_type"))
            continue
        if _days_listed(rec.listed_date, as_of) < min_days:
            excluded.append(make_excluded(rec.ticker, rec.name, f"상장 {min_days}일 미만", "min_listed_days"))
            continue

        px = prices_by_ticker.get(rec.ticker)
        if not px:
            excluded.append(make_excluded(rec.ticker, rec.name, "시세 미확보", "missing_price"))
            continue
        if min_mcap and px.market_cap < min_mcap:
            excluded.append(make_excluded(rec.ticker, rec.name, "시가총액 하한 미달", "min_market_cap"))
            continue
        if min_tv20 and px.trading_value_20d < min_tv20:
            excluded.append(make_excluded(rec.ticker, rec.name, "20일 거래대금 부족", "min_20d_trading_value"))
            continue
        if min_tv60 and px.trading_value_60d < min_tv60:
            excluded.append(make_excluded(rec.ticker, rec.name, "60일 거래대금 부족", "min_60d_trading_value"))
            continue

        passed.append(rec)

    return passed, excluded
