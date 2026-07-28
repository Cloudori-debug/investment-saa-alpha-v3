from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_refresh.dart_accounts_fetch import (
    FAILURE_ACTIONS,
    PHASE4E_FAILURE_CATEGORIES,
    AccountsFetchResult,
    check_accounts_alias_coverage,
    extract_account_names,
    fetch_accounts_raw,
    fetch_financial_accounts_with_fallback,
    validate_corp_code,
)
from src.data_refresh.dart_client import RateLimiter
from src.data_refresh.dart_corp_codes import build_ticker_corp_map
from src.value_list.ticker_registry import resolve_hakedaka_registry

ACCOUNTS_DEBUG_DISCLAIMER = (
    "Shadow diagnostic only. Financial accounts coverage WARN is not a buy/sell recommendation. "
    "Until coverage improves, hakedaka candidates remain preliminary research only."
)


@dataclass
class TickerAccountsDebugRow:
    ticker: str
    name: str
    corp_code: str
    corp_code_valid: bool
    accounts_fetch_success: bool
    failure_category: str
    failure_detail: str
    tried_combinations_count: int
    winning_bsns_year: str
    winning_reprt_code: str
    winning_fs_div: str
    winning_list_length: int
    alias_ok: bool
    alias_missing: str
    raw_response_path: str


def _load_prior_coverage(output_dir: Path) -> dict[str, float]:
    path = output_dir / "hakedaka_coverage_audit.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc.get("coverage") or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw_sample(
    debug_dir: Path,
    *,
    ticker: str,
    name: str,
    corp_code: str,
    attempt: Any,
    raw_data: dict[str, Any] | None = None,
) -> str:
    raw_dir = debug_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{ticker}_{corp_code}_{attempt.bsns_year}_{attempt.reprt_code}_{attempt.fs_div}.json"
    path = raw_dir / fname
    doc = {
        "ticker": ticker,
        "name": name,
        "corp_code": corp_code,
        "bsns_year": attempt.bsns_year,
        "reprt_code": attempt.reprt_code,
        "fs_div": attempt.fs_div,
        "status": attempt.status,
        "message": attempt.message,
        "list_length": attempt.list_length,
    }
    if raw_data:
        doc["raw_response"] = raw_data
    elif attempt.rows:
        doc["raw_response"] = {"status": attempt.status, "message": attempt.message, "list": attempt.rows[:50]}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path.relative_to(debug_dir.parent))


def debug_ticker_accounts(
    ticker: str,
    name: str,
    corp_code: str,
    as_of: str,
    *,
    limiter: RateLimiter,
    years: list[str] | None = None,
    save_raw: bool = False,
    debug_dir: Path | None = None,
) -> TickerAccountsDebugRow:
    valid, corp_err = validate_corp_code(corp_code)
    raw_path = ""
    if not valid:
        return TickerAccountsDebugRow(
            ticker=ticker, name=name, corp_code=str(corp_code or ""),
            corp_code_valid=False, accounts_fetch_success=False,
            failure_category=corp_err, failure_detail="invalid corp_code format",
            tried_combinations_count=0, winning_bsns_year="", winning_reprt_code="",
            winning_fs_div="", winning_list_length=0, alias_ok=False, alias_missing="",
            raw_response_path="",
        )

    result = fetch_financial_accounts_with_fallback(
        corp_code, as_of, limiter=limiter, years=years,
    )
    alias_ok, alias_missing = True, []
    failure_cat = result.failure_category
    failure_detail = result.failure_detail

    if result.success and result.accounts:
        alias_ok, alias_missing = check_accounts_alias_coverage(result.accounts)
        if not alias_ok:
            failure_cat = "accounts_present_alias_missing"
            failure_detail = ";".join(alias_missing)
            if debug_dir:
                names_dir = debug_dir / "account_names"
                names_dir.mkdir(parents=True, exist_ok=True)
                names = extract_account_names(result.accounts)
                pd.DataFrame(names).to_csv(
                    names_dir / f"{ticker}.csv", index=False, encoding="utf-8-sig",
                )
    elif save_raw and debug_dir and result.attempts:
        last = result.attempts[-1]
        raw_path = _save_raw_sample(debug_dir, ticker=ticker, name=name, corp_code=corp_code, attempt=last)

    win = result.winning_attempt
    return TickerAccountsDebugRow(
        ticker=ticker,
        name=name,
        corp_code=corp_code,
        corp_code_valid=True,
        accounts_fetch_success=result.success,
        failure_category=failure_cat if not result.success else (failure_cat if not alias_ok else ""),
        failure_detail=failure_detail,
        tried_combinations_count=result.tried_combinations_count,
        winning_bsns_year=win.bsns_year if win else "",
        winning_reprt_code=win.reprt_code if win else "",
        winning_fs_div=win.fs_div if win else "",
        winning_list_length=win.list_length if win else 0,
        alias_ok=alias_ok,
        alias_missing=";".join(alias_missing),
        raw_response_path=raw_path,
    )


def save_raw_samples_for_failures(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    sample_size: int = 5,
    years: list[str] | None = None,
) -> list[str]:
    """no_accounts/failed 종목 상위 N개 raw JSON 저장."""
    debug_dir = output_dir / "dart_accounts_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    errors_path = data_dir / "hakedaka_enrich_last_errors.json"
    failed: list[str] = []
    if errors_path.exists():
        try:
            doc = json.loads(errors_path.read_text(encoding="utf-8"))
            failed = [
                t for t, e in (doc.get("by_ticker") or {}).items()
                if "no_accounts" in str(e) or "accounts_api" in str(e) or "empty" in str(e)
            ]
        except (json.JSONDecodeError, OSError):
            pass

    registry = {
        str(r["ticker"]).zfill(6): str(r.get("name", ""))
        for r in resolve_hakedaka_registry(data_dir) if r.get("ticker")
    }
    corp_map = build_ticker_corp_map(data_dir, list(registry.keys()))
    if not failed:
        failed = [t for t in registry if t not in corp_map][:sample_size]
    else:
        failed = failed[:sample_size]

    limiter = RateLimiter(min_interval_sec=0.12)
    saved: list[str] = []
    for ticker in failed:
        corp = corp_map.get(ticker)
        if not corp:
            continue
        meta = find_first_failed_attempt_params(corp, as_of, years=years, limiter=limiter)
        if meta:
            path = _save_raw_sample(debug_dir, ticker=ticker, name=registry.get(ticker, ticker),
                                    corp_code=corp, attempt=meta)
            saved.append(path)
    return saved


def find_first_failed_attempt_params(
    corp_code: str,
    as_of: str,
    *,
    years: list[str] | None,
    limiter: RateLimiter,
) -> Any | None:
    from src.data_refresh.dart_accounts_fetch import REPRT_CODE_PRIORITY, FS_DIV_PRIORITY, _years_for_as_of

    year_list = years or _years_for_as_of(as_of)
    for bsns_year in year_list:
        for reprt_code in REPRT_CODE_PRIORITY:
            for fs_div in FS_DIV_PRIORITY:
                att = fetch_accounts_raw(corp_code, bsns_year, reprt_code, fs_div, limiter=limiter)
                if att.status == "013" or att.list_length == 0:
                    return att
    return None


def run_dart_accounts_debug(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    sample_size: int = 5,
    force: bool = False,
    years: list[str] | None = None,
    save_raw: bool = True,
    write_summary: bool = True,
) -> dict[str, Any]:
    """Phase 4e — DART accounts fetch debug (shadow only)."""
    from src.settings.user_secrets import apply_secrets_to_env, credential_status

    as_of_date = as_of or date.today().isoformat()
    apply_secrets_to_env(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = output_dir / "dart_accounts_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    coverage_before = _load_prior_coverage(output_dir)
    report: dict[str, Any] = {
        "as_of": as_of_date,
        "mode": "shadow_only",
        "phase": "4e",
        "disclaimer": ACCOUNTS_DEBUG_DISCLAIMER,
        "dart_credentials": bool(credential_status(data_dir).get("dart")),
    }

    if not report["dart_credentials"]:
        report["error"] = "request_limit_or_api_error"
        report["message"] = "no DART credentials"
        _write_empty_outputs(output_dir, report)
        return report

    registry = [
        {"ticker": str(r["ticker"]).zfill(6), "name": str(r.get("name", ""))}
        for r in resolve_hakedaka_registry(data_dir) if r.get("ticker")
    ]
    corp_map = build_ticker_corp_map(data_dir, [r["ticker"] for r in registry])
    limiter = RateLimiter(min_interval_sec=0.12)
    rows: list[TickerAccountsDebugRow] = []

    for item in registry:
        ticker = item["ticker"]
        try:
            row = debug_ticker_accounts(
                ticker, item["name"], corp_map.get(ticker, ""),
                as_of_date, limiter=limiter, years=years,
                save_raw=save_raw, debug_dir=debug_dir,
            )
            rows.append(row)
        except Exception as exc:
            rows.append(TickerAccountsDebugRow(
                ticker=ticker, name=item["name"], corp_code=corp_map.get(ticker, ""),
                corp_code_valid=bool(corp_map.get(ticker)), accounts_fetch_success=False,
                failure_category="request_limit_or_api_error", failure_detail=str(exc),
                tried_combinations_count=0, winning_bsns_year="", winning_reprt_code="",
                winning_fs_div="", winning_list_length=0, alias_ok=False, alias_missing="",
                raw_response_path="",
            ))

    success_count = sum(1 for r in rows if r.accounts_fetch_success)
    total = len(rows) or 1
    fail_counter: Counter[str] = Counter(
        r.failure_category for r in rows if not r.accounts_fetch_success and r.failure_category
    )
    for r in rows:
        if r.accounts_fetch_success and not r.alias_ok:
            fail_counter["accounts_present_alias_missing"] += 1

    success_by_fs: Counter[str] = Counter(r.winning_fs_div for r in rows if r.accounts_fetch_success)
    success_by_reprt: Counter[str] = Counter(r.winning_reprt_code for r in rows if r.accounts_fetch_success)
    success_by_year: Counter[str] = Counter(r.winning_bsns_year for r in rows if r.accounts_fetch_success)

    dominant = fail_counter.most_common(1)[0][0] if fail_counter else ""
    summary = {
        "tried_combinations_count": sum(r.tried_combinations_count for r in rows),
        "success_count": success_count,
        "success_rate_pct": round(success_count / total * 100, 1),
        "success_by_fs_div": dict(success_by_fs),
        "success_by_reprt_code": dict(success_by_reprt),
        "success_by_bsns_year": dict(success_by_year),
        "dominant_failure_category": dominant,
        "recommended_next_action": FAILURE_ACTIONS.get(dominant, "investigate"),
        "failure_counts": dict(fail_counter),
        "raw_samples_saved": [],
    }

    if save_raw:
        try:
            summary["raw_samples_saved"] = save_raw_samples_for_failures(
                data_dir, output_dir, as_of=as_of_date, sample_size=sample_size, years=years,
            )
        except Exception as exc:
            summary["raw_samples_error"] = str(exc)

    if force:
        try:
            from src.value_list.hakedaka_fundamentals import enrich_hakedaka_fundamentals

            tickers = [r["ticker"] for r in registry]
            enrich_hakedaka_fundamentals(data_dir, tickers, as_of=as_of_date, force=True)
            from src.value_list.hakedaka_coverage_audit import write_hakedaka_coverage_audit

            audit = write_hakedaka_coverage_audit(data_dir, output_dir, as_of=as_of_date)
            report["coverage_after"] = audit.get("coverage")
        except Exception as exc:
            report["enrich_error"] = str(exc)

    coverage_after = report.get("coverage_after") or _load_prior_coverage(output_dir)
    summary["coverage_before"] = {
        "ocf_coverage": coverage_before.get("ocf_coverage"),
        "debt_coverage": coverage_before.get("debt_coverage"),
    }
    summary["coverage_after"] = {
        "ocf_coverage": coverage_after.get("ocf_coverage"),
        "debt_coverage": coverage_after.get("debt_coverage"),
    }

    report["summary"] = summary
    report["tickers"] = [asdict(r) for r in rows]

    csv_path = output_dir / "dart_accounts_fetch_debug.csv"
    json_path = output_dir / "dart_accounts_fetch_debug.json"
    summary_path = output_dir / "dart_accounts_debug_summary.json"

    pd.DataFrame([asdict(r) for r in rows]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return report


def _write_empty_outputs(output_dir: Path, report: dict[str, Any]) -> None:
    summary_path = output_dir / "dart_accounts_debug_summary.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
