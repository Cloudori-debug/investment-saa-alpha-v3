from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_refresh.external_market import business_days_between
from src.data_refresh.pykrx_bulk import _normalize_ticker

TIER_H_FUND_STATE = "tier_h_fundamentals_refresh.json"
DEFAULT_INTERVAL_BUSINESS_DAYS = 5

HAKEDAKA_FUND_COLUMNS = [
    "ticker",
    "as_of",
    "report_date",
    "usable_from_date",
    "period_end",
    "latest_quarter_year",
    "latest_quarter_reprt_code",
    "annual_year",
    "annual_reprt_code",
    "operating_cash_flow",
    "free_cash_flow",
    "ocf_latest_quarter",
    "ocf_annual",
    "fcf_latest_quarter",
    "fcf_annual",
    "debt_ratio",
    "debt_latest_quarter",
    "debt_annual",
    "interest_coverage",
    "cash_and_equivalents",
    "cash_latest_quarter",
    "cash_annual",
    "short_term_financial_assets",
    "total_debt",
    "net_cash",
    "current_assets",
    "total_liabilities",
    "ncav",
    "fcf_confidence",
    "treasury_shares_value_or_ratio",
    "dividend_per_share",
    "payout_ratio",
    "capital_expenditure",
    "net_cash_to_market_cap",
    "ncav_to_market_cap",
    "treasury_share_ratio",
    "buyback_cancellation_progress",
    "dividend_policy_change_flag",
    "shareholder_return_yield",
    "holding_company_discount_proxy",
    "nav_discount_proxy_pct",
    "asset_value_discount_proxy",
    "related_party_risk_flag",
    "governance_event_flag",
    "missing_reason",
    "enriched_at",
]

QUARTER_REPRT_CODES = ("11013", "11014", "11012")
ANNUAL_REPRT_CODES = ("11011",)


@dataclass
class HakedakaFundRefreshResult:
    as_of: str
    ran: bool
    reason: str
    enriched: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _state_path(data_dir: Path) -> Path:
    return data_dir / TIER_H_FUND_STATE


def load_tier_h_fund_state(data_dir: Path) -> dict[str, Any]:
    path = _state_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def tier_h_fundamentals_is_due(data_dir: Path, as_of: str, *, interval: int = DEFAULT_INTERVAL_BUSINESS_DAYS) -> bool:
    state = load_tier_h_fund_state(data_dir)
    last = str(state.get("last_run_date", "")).strip()
    if not last:
        return True
    return business_days_between(last, as_of[:10]) >= interval



def _extended_metrics(rows: list[dict[str, Any]], meta: Any, valuation: dict[str, float | None] | None) -> dict[str, Any]:
    from src.data_refresh.dart_account_aliases import compute_hakedaka_metrics
    from src.data_refresh.dart_financials import compute_metrics

    base = compute_metrics(rows, meta)
    alias = compute_hakedaka_metrics(rows, meta)
    merged = {**base, **alias}
    if alias.get("operating_cash_flow") is not None:
        merged["operating_cash_flow"] = alias["operating_cash_flow"]
    if alias.get("fcf") is not None:
        merged["fcf"] = alias["fcf"]
    if alias.get("debt_ratio") is not None:
        merged["debt_ratio"] = alias["debt_ratio"]

    val = valuation or {}
    div_yield = val.get("dividend_yield")
    ncav = merged.get("ncav")
    treasury_ratio = merged.get("treasury_share_ratio")

    return {
        **merged,
        "treasury_shares_value_or_ratio": (
            treasury_ratio if treasury_ratio is not None else merged.get("treasury_shares_value_or_ratio")
        ),
        "ncav": ncav,
        "fcf_confidence": alias.get("fcf_confidence"),
        "short_term_financial_assets": alias.get("short_term_financial_assets"),
        "current_assets": alias.get("current_assets"),
        "total_liabilities": alias.get("total_liabilities"),
        "dividend_per_share": None,
        "payout_ratio": None,
        "shareholder_return_yield": div_yield,
        "missing_reason": alias.get("missing_reason") or "",
    }


def _period_metrics(
    corp: str,
    as_of: str,
    reprt_codes: tuple[str, ...],
    *,
    limiter: Any,
    valuation: dict[str, float | None] | None,
) -> dict[str, Any]:
    from src.data_refresh.dart_accounts_fetch import fetch_financial_accounts_with_fallback

    result = fetch_financial_accounts_with_fallback(
        corp, as_of, limiter=limiter, reprt_codes=reprt_codes,
    )
    if not result.success or not result.meta:
        return {}
    ext = _extended_metrics(result.accounts, result.meta, valuation)
    return {
        "year": result.meta.bsns_year,
        "reprt_code": result.meta.reprt_code,
        "ocf": ext.get("operating_cash_flow"),
        "fcf": ext.get("fcf"),
        "debt": ext.get("debt_ratio"),
        "cash": ext.get("cash_and_equivalents"),
    }


def _market_cap(data_dir: Path, ticker: str) -> float | None:
    path = data_dir / "prices.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    row = df[df["ticker"].astype(str).str.zfill(6) == ticker.zfill(6)]
    if row.empty:
        return None
    try:
        return float(row.iloc[0].get("market_cap", 0) or 0)
    except (TypeError, ValueError):
        return None


def enrich_hakedaka_fundamentals(
    data_dir: Path,
    tickers: list[str],
    *,
    as_of: str,
    force: bool = False,
) -> HakedakaFundRefreshResult:
    from src.data_refresh.dart_client import RateLimiter
    from src.data_refresh.dart_corp_codes import build_ticker_corp_map
    from src.data_refresh.dart_accounts_fetch import (
        check_accounts_alias_coverage,
        fetch_financial_accounts_with_fallback,
        validate_corp_code,
    )
    from src.data_refresh.dart_enrich import _load_valuation_overlay
    from src.data_refresh.dart_financials import build_fundamental_record
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(data_dir)
    if not force and not tier_h_fundamentals_is_due(data_dir, as_of):
        return HakedakaFundRefreshResult(as_of=as_of, ran=False, reason="not_due")

    norm = [_normalize_ticker(t) for t in tickers if str(t).strip()]
    corp_map = build_ticker_corp_map(data_dir, norm)
    valuation = _load_valuation_overlay(data_dir)
    limiter = RateLimiter(min_interval_sec=0.12)
    enriched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    errors_by_ticker: dict[str, str] = {}
    skipped = 0

    errors_detail: dict[str, dict[str, Any]] = {}

    for ticker in norm:
        corp = corp_map.get(ticker)
        valid, corp_err = validate_corp_code(corp)
        if not valid:
            skipped += 1
            msg = corp_err
            errors.append(f"{ticker}:{msg}")
            errors_by_ticker[ticker] = msg
            errors_detail[ticker] = {"category": msg, "detail": "invalid or missing corp_code"}
            continue
        try:
            fetch_result = fetch_financial_accounts_with_fallback(corp, as_of, limiter=limiter)
            if not fetch_result.success:
                skipped += 1
                msg = fetch_result.failure_category or "accounts_api_empty_list"
                errors.append(f"{ticker}:{msg}")
                errors_by_ticker[ticker] = msg
                errors_detail[ticker] = {
                    "category": msg,
                    "detail": fetch_result.failure_detail,
                    "tried": fetch_result.tried_combinations_count,
                }
                continue
            accounts = fetch_result.accounts
            meta = fetch_result.meta
            if not accounts or not meta:
                skipped += 1
                msg = "accounts_api_empty_list"
                errors.append(f"{ticker}:{msg}")
                errors_by_ticker[ticker] = msg
                continue
            alias_ok, alias_missing = check_accounts_alias_coverage(accounts)
            if not alias_ok:
                errors_detail[ticker] = {
                    "category": "accounts_present_alias_missing",
                    "detail": ";".join(alias_missing),
                    "warning_only": True,
                }
            ext = _extended_metrics(accounts, meta, valuation.get(ticker))
            record = build_fundamental_record(ticker, meta, ext, valuation.get(ticker))
            quarter = _period_metrics(
                corp, as_of, QUARTER_REPRT_CODES, limiter=limiter, valuation=valuation.get(ticker),
            )
            annual = _period_metrics(
                corp, as_of, ANNUAL_REPRT_CODES, limiter=limiter, valuation=valuation.get(ticker),
            )
            mcap = _market_cap(data_dir, ticker)
            net_cash = ext.get("net_cash")
            ncav = ext.get("ncav")
            pbr = record.get("pbr")
            nav_pct = None
            meta_row = None
            try:
                from src.value_list.ticker_registry import hakedaka_meta_by_ticker
                meta_row = hakedaka_meta_by_ticker(data_dir).get(ticker, {})
            except Exception:
                meta_row = {}
            if int(meta_row.get("group_id", 0) or 0) == 1 and pbr and float(pbr) < 1:
                nav_pct = round((1 - float(pbr)) * 100, 2)
            row = {
                "ticker": ticker,
                "as_of": as_of,
                "report_date": record.get("report_date"),
                "usable_from_date": record.get("usable_from_date"),
                "period_end": record.get("period_end"),
                "latest_quarter_year": quarter.get("year"),
                "latest_quarter_reprt_code": quarter.get("reprt_code"),
                "annual_year": annual.get("year"),
                "annual_reprt_code": annual.get("reprt_code"),
                "operating_cash_flow": record.get("operating_cash_flow"),
                "free_cash_flow": record.get("fcf"),
                "ocf_latest_quarter": quarter.get("ocf"),
                "ocf_annual": annual.get("ocf"),
                "fcf_latest_quarter": quarter.get("fcf"),
                "fcf_annual": annual.get("fcf"),
                "debt_ratio": record.get("debt_ratio"),
                "debt_latest_quarter": quarter.get("debt"),
                "debt_annual": annual.get("debt"),
                "interest_coverage": record.get("interest_coverage"),
                "cash_and_equivalents": ext.get("cash_and_equivalents"),
                "cash_latest_quarter": quarter.get("cash"),
                "cash_annual": annual.get("cash"),
                "short_term_financial_assets": ext.get("short_term_financial_assets"),
                "total_debt": ext.get("total_debt"),
                "net_cash": net_cash,
                "current_assets": ext.get("current_assets"),
                "total_liabilities": ext.get("total_liabilities"),
                "ncav": ncav,
                "fcf_confidence": ext.get("fcf_confidence"),
                "treasury_shares_value_or_ratio": ext.get("treasury_shares_value_or_ratio"),
                "dividend_per_share": ext.get("dividend_per_share"),
                "payout_ratio": ext.get("payout_ratio"),
                "capital_expenditure": ext.get("capital_expenditure"),
                "net_cash_to_market_cap": round(net_cash / mcap * 100, 4) if net_cash is not None and mcap else None,
                "ncav_to_market_cap": round(ncav / mcap * 100, 4) if ncav is not None and mcap else None,
                "treasury_share_ratio": ext.get("treasury_share_ratio"),
                "buyback_cancellation_progress": None,
                "dividend_policy_change_flag": bool(record.get("dividend_yield")),
                "shareholder_return_yield": ext.get("shareholder_return_yield"),
                "holding_company_discount_proxy": round(1 - float(pbr), 4) if pbr and float(pbr) < 1 else None,
                "nav_discount_proxy_pct": nav_pct,
                "asset_value_discount_proxy": record.get("pbr"),
                "related_party_risk_flag": False,
                "governance_event_flag": False,
                "missing_reason": ext.get("missing_reason", ""),
                "enriched_at": enriched_at,
            }
            rows.append(row)
        except Exception as exc:
            skipped += 1
            msg = str(exc)
            errors.append(f"{ticker}:{msg}")
            errors_by_ticker[ticker] = msg

    (data_dir / "hakedaka_enrich_last_errors.json").write_text(
        json.dumps({
            "as_of": as_of[:10],
            "by_ticker": errors_by_ticker,
            "details": errors_detail,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    out_path = data_dir / "hakedaka_fundamentals.csv"
    if rows:
        new_df = pd.DataFrame(rows)
        for col in HAKEDAKA_FUND_COLUMNS:
            if col not in new_df.columns:
                new_df[col] = None
        new_df = new_df[HAKEDAKA_FUND_COLUMNS]
        if out_path.exists():
            old = pd.read_csv(out_path, dtype=str, keep_default_na=False)
            old["ticker"] = old["ticker"].map(_normalize_ticker)
            for col in HAKEDAKA_FUND_COLUMNS:
                if col not in old.columns:
                    old[col] = ""
            old = old[~old["ticker"].isin(new_df["ticker"].astype(str).map(_normalize_ticker))]
            merged = pd.concat([old, new_df.astype(object)], ignore_index=True)
        else:
            merged = new_df
        merged.to_csv(out_path, index=False, encoding="utf-8-sig")

    _state_path(data_dir).write_text(
        json.dumps({"last_run_date": as_of[:10], "last_run_at": enriched_at, "enriched": len(rows)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return HakedakaFundRefreshResult(
        as_of=as_of,
        ran=True,
        reason="ok",
        enriched=len(rows),
        skipped=skipped,
        errors=errors[:50],
    )


def load_hakedaka_fundamentals(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / "hakedaka_fundamentals.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        if t:
            out[t] = dict(row)
    return out
