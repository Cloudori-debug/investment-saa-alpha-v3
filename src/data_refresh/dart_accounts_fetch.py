from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.data_refresh.dart_client import DartApiError, RateLimiter, dart_get
from src.data_refresh.dart_financials import REPORT_CODES, ReportMeta

REPRT_CODE_PRIORITY = ("11011", "11014", "11012", "11013")
FS_DIV_PRIORITY = ("CFS", "OFS")

PHASE4E_FAILURE_CATEGORIES = (
    "accounts_api_empty_status_013",
    "accounts_api_empty_list",
    "corp_code_mapping_error",
    "reprt_code_not_available",
    "fs_div_not_available",
    "bsns_year_not_available",
    "accounts_present_alias_missing",
    "accounts_present_parser_error",
    "request_limit_or_api_error",
    "no_report",
    "no_corp_code",
)

FAILURE_ACTIONS: dict[str, str] = {
    "accounts_api_empty_status_013": "reprt_code/bsns_year/fs_div 조합 재시도 또는 실제 미공시",
    "accounts_api_empty_list": "API 응답 list 비어있음 — 조합 matrix 확장",
    "corp_code_mapping_error": "corp_code 테이블 갱신 및 8자리 검증",
    "reprt_code_not_available": "보고서 코드 탐색 로직 수정",
    "fs_div_not_available": "CFS/OFS fallback 강화",
    "bsns_year_not_available": "bsns_year 전년도 fallback",
    "accounts_present_alias_missing": "dart_account_aliases.py 확장",
    "accounts_present_parser_error": "raw response 파서 수정",
    "request_limit_or_api_error": "API 호출량/키/쿨다운 처리",
    "no_report": "list.json 보고서 탐색 로직",
    "no_corp_code": "ticker-corp_code 매핑",
}


@dataclass
class AccountsFetchAttempt:
    corp_code: str
    bsns_year: str
    reprt_code: str
    fs_div: str
    status: str
    message: str
    list_length: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @property
    def success(self) -> bool:
        return self.list_length > 0


@dataclass
class AccountsFetchResult:
    success: bool
    accounts: list[dict[str, Any]] = field(default_factory=list)
    meta: ReportMeta | None = None
    failure_category: str = ""
    failure_detail: str = ""
    attempts: list[AccountsFetchAttempt] = field(default_factory=list)
    winning_attempt: AccountsFetchAttempt | None = None
    tried_combinations_count: int = 0


def validate_corp_code(corp_code: str | None) -> tuple[bool, str]:
    if not corp_code or not str(corp_code).strip():
        return False, "corp_code_mapping_error"
    code = str(corp_code).strip()
    if len(code) != 8 or not code.isdigit():
        return False, "corp_code_mapping_error"
    return True, ""


def _years_for_as_of(as_of: str, *, extra_years: list[int] | None = None) -> list[str]:
    year = datetime.strptime(as_of[:10], "%Y-%m-%d").year
    years = [year, year - 1, year - 2]
    if extra_years:
        years = list(dict.fromkeys(extra_years + years))
    return [str(y) for y in years]


def _synthetic_rcept_dt(bsns_year: str, reprt_code: str) -> str:
    suffix = REPORT_CODES.get(reprt_code, ("", "12-31"))[1]
    parts = suffix.split("-")
    return f"{bsns_year}{parts[0]}{parts[1]}"


def fetch_accounts_raw(
    corp_code: str,
    bsns_year: str,
    reprt_code: str,
    fs_div: str,
    *,
    limiter: RateLimiter | None = None,
) -> AccountsFetchAttempt:
    if limiter:
        limiter.wait()
    try:
        data = dart_get(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
                "fs_div": fs_div,
            },
        )
        status = str(data.get("status", "000"))
        message = str(data.get("message", ""))
        rows = list(data.get("list") or [])
        return AccountsFetchAttempt(
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            fs_div=fs_div,
            status=status,
            message=message,
            list_length=len(rows),
            rows=rows,
        )
    except DartApiError as exc:
        err = str(exc)
        status = "020" if "020" in err else "error"
        return AccountsFetchAttempt(
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            fs_div=fs_div,
            status=status,
            message=err,
            list_length=0,
            error=err,
        )
    except Exception as exc:
        return AccountsFetchAttempt(
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            fs_div=fs_div,
            status="error",
            message=str(exc),
            list_length=0,
            error=str(exc),
        )


def classify_fetch_failure(attempts: list[AccountsFetchAttempt]) -> tuple[str, str]:
    if not attempts:
        return "accounts_api_empty_list", "no attempts"

    if any(a.status == "020" or "020" in a.error for a in attempts):
        return "request_limit_or_api_error", "DART status 020 or rate limit"

    if all(a.status == "013" for a in attempts):
        return "accounts_api_empty_status_013", "all combinations returned status 013"

    status_013 = sum(1 for a in attempts if a.status == "013")
    empty_list = sum(1 for a in attempts if a.list_length == 0 and a.status == "000")
    if status_013 > len(attempts) // 2:
        return "accounts_api_empty_status_013", f"status_013={status_013}/{len(attempts)}"

    cfs_fail = all(a.list_length == 0 for a in attempts if a.fs_div == "CFS")
    ofs_fail = all(a.list_length == 0 for a in attempts if a.fs_div == "OFS")
    if cfs_fail and not ofs_fail:
        return "fs_div_not_available", "CFS empty, check OFS path"
    if ofs_fail and not cfs_fail:
        return "fs_div_not_available", "OFS empty, check CFS path"

    if empty_list == len(attempts):
        return "accounts_api_empty_list", "all returned empty list"

    return "bsns_year_not_available", "no successful year/reprt/fs_div combination"


def fetch_financial_accounts_with_fallback(
    corp_code: str,
    as_of: str,
    *,
    limiter: RateLimiter | None = None,
    years: list[str] | None = None,
    reprt_codes: tuple[str, ...] = REPRT_CODE_PRIORITY,
    fs_divs: tuple[str, ...] = FS_DIV_PRIORITY,
    max_attempts: int | None = None,
) -> AccountsFetchResult:
    """CFS/OFS x reprt_code x bsns_year fallback matrix."""
    ok, cat = validate_corp_code(corp_code)
    if not ok:
        return AccountsFetchResult(success=False, failure_category=cat, failure_detail="invalid corp_code")

    year_list = years or _years_for_as_of(as_of)
    attempts: list[AccountsFetchAttempt] = []
    cap = max_attempts or len(year_list) * len(reprt_codes) * len(fs_divs)

    for bsns_year in year_list:
        for reprt_code in reprt_codes:
            for fs_div in fs_divs:
                if len(attempts) >= cap:
                    break
                att = fetch_accounts_raw(
                    corp_code, bsns_year, reprt_code, fs_div, limiter=limiter,
                )
                attempts.append(att)
                if att.success:
                    meta = ReportMeta(
                        corp_code=corp_code,
                        bsns_year=bsns_year,
                        reprt_code=reprt_code,
                        rcept_no="",
                        rcept_dt=_synthetic_rcept_dt(bsns_year, reprt_code),
                        report_nm=REPORT_CODES.get(reprt_code, ("", ""))[0],
                    )
                    return AccountsFetchResult(
                        success=True,
                        accounts=att.rows,
                        meta=meta,
                        attempts=attempts,
                        winning_attempt=att,
                        tried_combinations_count=len(attempts),
                    )
            if len(attempts) >= cap:
                break
        if len(attempts) >= cap:
            break

    cat, detail = classify_fetch_failure(attempts)
    return AccountsFetchResult(
        success=False,
        failure_category=cat,
        failure_detail=detail,
        attempts=attempts,
        tried_combinations_count=len(attempts),
    )


def check_accounts_alias_coverage(accounts: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """list > 0 but core fields missing => alias issue."""
    from src.data_refresh.dart_account_aliases import compute_hakedaka_metrics

    class _Meta:
        pass

    metrics = compute_hakedaka_metrics(accounts, _Meta())
    missing = str(metrics.get("missing_reason") or "").split(";")
    missing = [m for m in missing if m]
    core = {"ocf", "fcf", "debt_ratio", "net_cash", "cash"}
    if not missing:
        return True, []
    if core.intersection(set(missing)) and metrics.get("operating_cash_flow") is None:
        return False, missing
    return True, missing


def extract_account_names(accounts: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for row in accounts:
        name = str(row.get("account_nm", ""))
        sj = str(row.get("sj_div", ""))
        key = (name, sj)
        if name and key not in seen:
            seen.add(key)
            out.append({"account_nm": name, "sj_div": sj})
    return out
