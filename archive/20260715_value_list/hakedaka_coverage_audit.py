from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.value_list.hakedaka_coverage_targets import (
    DEFAULT_COVERAGE_TARGETS,
    ensure_coverage_targets,
    load_coverage_targets,
)
from src.value_list.hakedaka_manual_overrides import apply_manual_to_fundamentals, load_manual_overrides
from src.value_list.ticker_registry import resolve_hakedaka_registry

COVERAGE_AUDIT_DISCLAIMER = (
    "Shadow diagnostic only. Coverage WARN is not a buy/sell recommendation. "
    "Low coverage means hakedaka scores are preliminary research only. "
    "v1.0.2 execution authority unchanged."
)

MISSING_REASON_CATEGORIES = (
    "dart_api_no_response",
    "dart_report_not_found",
    "account_alias_not_matched",
    "financial_statement_not_available",
    "consolidated_vs_separate_mismatch",
    "parsing_error",
    "stale_cache",
    "ticker_mapping_error",
    "not_applicable",
    "accounts_api_empty_status_013",
    "accounts_api_empty_list",
    "corp_code_mapping_error",
    "reprt_code_not_available",
    "fs_div_not_available",
    "bsns_year_not_available",
    "accounts_present_alias_missing",
    "accounts_present_parser_error",
    "request_limit_or_api_error",
)

LEGACY_ERROR_MAP = {
    "no_accounts": "accounts_api_empty_list",
    "no_corp_code": "corp_code_mapping_error",
    "no_report": "dart_report_not_found",
}

MISSING_REASON_ACTIONS: dict[str, str] = {
    "dart_api_no_response": "DART API key/env/endpoint 확인",
    "dart_report_not_found": "사업/분기 보고서 선택 로직 점검",
    "account_alias_not_matched": "alias map 확장",
    "financial_statement_not_available": "공시 구조상 미제공 — 수동 보강 검토",
    "consolidated_vs_separate_mismatch": "연결/별도(CFS/OFS) 선택 로직 점검",
    "parsing_error": "파서/응답 파싱 디버깅",
    "stale_cache": "force enrich 재실행",
    "ticker_mapping_error": "종목코드-corp_code 매핑 점검",
    "not_applicable": "정상 — 해당 필드 이벤트 없음",
    "accounts_api_empty_status_013": "reprt/year/fs_div 조합 재시도",
    "accounts_api_empty_list": "fnlttSinglAcntAll fallback matrix 확장",
    "corp_code_mapping_error": "corp_code 8자리 매핑 갱신",
    "reprt_code_not_available": "보고서 코드 탐색 수정",
    "fs_div_not_available": "CFS/OFS fallback 강화",
    "bsns_year_not_available": "bsns_year 전년도 fallback",
    "accounts_present_alias_missing": "dart_account_aliases 확장",
    "accounts_present_parser_error": "raw response 파서 수정",
    "request_limit_or_api_error": "API 호출량/키/쿨다운",
}

LOW_COVERAGE_THRESHOLD_PCT = 10.0
FINANCIAL_DEBUG_FIELDS = ("ocf", "fcf", "debt", "cash", "net_cash")

AUDIT_CSV_FIELDS = [
    "ticker",
    "name",
    "price_available",
    "ocf_available",
    "fcf_available",
    "debt_available",
    "cash_available",
    "net_cash_available",
    "treasury_event_available",
    "treasury_scan_ok",
    "shareholder_return_available",
    "data_quality_score",
    "missing_critical_count",
    "missing_reason_summary",
    "enrichment_status",
]


def _load_treasury_scan_status(output_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    path = output_dir / "hakedaka_treasury_scan_status.json"
    if not path.exists():
        return {}, {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        tickers = {str(k).zfill(6): v for k, v in (doc.get("tickers") or {}).items()}
        return tickers, doc.get("summary") or {}
    except (json.JSONDecodeError, OSError):
        return {}, {}


def build_missing_reason_aggregation(
    field_category_detail: list[dict[str, Any]],
    category_counter: Counter[str],
    *,
    total_tickers: int,
) -> dict[str, Any]:
    """missing reason별 실패 원인 집계 + 권고 액션."""
    by_category: list[dict[str, Any]] = []
    for cat, count in category_counter.most_common():
        by_category.append({
            "category": cat,
            "count": count,
            "pct_of_gaps": round(count / max(sum(category_counter.values()), 1) * 100, 1),
            "recommended_action": MISSING_REASON_ACTIONS.get(cat, "investigate"),
        })

    by_field: dict[str, Counter[str]] = {f: Counter() for f in FINANCIAL_DEBUG_FIELDS + ("treasury",)}
    for item in field_category_detail:
        field = str(item.get("field", ""))
        cat = str(item.get("category", ""))
        if field in by_field and cat != "not_applicable":
            by_field[field][cat] += 1

    field_breakdown: list[dict[str, Any]] = []
    for field, counter in by_field.items():
        if not counter:
            continue
        top_cat, top_n = counter.most_common(1)[0]
        field_breakdown.append({
            "field": field,
            "gap_count": sum(counter.values()),
            "dominant_category": top_cat,
            "dominant_count": top_n,
            "recommended_action": MISSING_REASON_ACTIONS.get(top_cat, "investigate"),
        })
    field_breakdown.sort(key=lambda x: x["gap_count"], reverse=True)

    dominant = by_category[0] if by_category else None
    return {
        "total_gap_records": sum(category_counter.values()),
        "tier_h_count": total_tickers,
        "by_category": by_category,
        "by_field": field_breakdown,
        "dominant_category": dominant.get("category") if dominant else "",
        "dominant_recommended_action": dominant.get("recommended_action") if dominant else "",
    }


def build_low_coverage_diagnosis(
    coverage: dict[str, float],
    field_category_detail: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """OCF/FCF/debt 등 10% 미만이면 디버깅 우선순위 힌트."""
    metric_to_field = {
        "ocf_coverage": "ocf",
        "fcf_coverage": "fcf",
        "debt_coverage": "debt",
        "cash_coverage": "cash",
        "net_cash_coverage": "net_cash",
    }
    diagnosis: list[dict[str, Any]] = []
    for metric, field in metric_to_field.items():
        actual = coverage.get(metric, 0)
        if actual >= LOW_COVERAGE_THRESHOLD_PCT:
            continue
        field_cats = Counter(
            item["category"]
            for item in field_category_detail
            if item.get("field") == field and item.get("category") != "not_applicable"
        )
        top_causes = [
            {"category": c, "count": n, "action": MISSING_REASON_ACTIONS.get(c, "investigate")}
            for c, n in field_cats.most_common(3)
        ]
        primary = top_causes[0] if top_causes else None
        diagnosis.append({
            "metric": metric,
            "actual_pct": actual,
            "threshold_pct": LOW_COVERAGE_THRESHOLD_PCT,
            "priority": "P0",
            "interpretation": (
                f"{metric} below {LOW_COVERAGE_THRESHOLD_PCT}% — "
                f"likely {primary['category']}" if primary else f"{metric} critically low"
            ),
            "top_causes": top_causes,
            "recommended_action": primary["action"] if primary else "Run force enrich and inspect missing_reason",
        })
    return diagnosis


MANUAL_REVIEW_FIELDS = [
    "ticker",
    "name",
    "priority",
    "missing_fields",
    "suggested_manual_field",
    "reason",
    "evidence_pack_path",
]

STALE_ENRICH_DAYS = 10


def _has(val: Any) -> bool:
    return val not in (None, "", "nan", "None")


def _load_enrich_errors(data_dir: Path) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    path = data_dir / "hakedaka_enrich_last_errors.json"
    if not path.exists():
        return {}, {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        by_ticker = {str(k).zfill(6): str(v) for k, v in (doc.get("by_ticker") or {}).items()}
        details = {str(k).zfill(6): v for k, v in (doc.get("details") or {}).items()}
        return by_ticker, details
    except (json.JSONDecodeError, OSError):
        return {}, {}


def _normalize_enrich_error(error: str, details: dict[str, Any] | None = None) -> str:
    if details and details.get("category"):
        return str(details["category"])
    if error in LEGACY_ERROR_MAP:
        return LEGACY_ERROR_MAP[error]
    if error in MISSING_REASON_CATEGORIES:
        return error
    return error


def _days_since(d: str, as_of: str) -> int | None:
    if not d or not as_of:
        return None
    try:
        return (datetime.strptime(as_of[:10], "%Y-%m-%d") - datetime.strptime(d[:10], "%Y-%m-%d")).days
    except ValueError:
        return None


def _map_enrich_error_to_category(error: str) -> str:
    if error in LEGACY_ERROR_MAP:
        return LEGACY_ERROR_MAP[error]
    if error in MISSING_REASON_CATEGORIES:
        return error
    e = error.lower()
    if "no_corp_code" in e or "corp" in e and "mapping" in e:
        return "ticker_mapping_error"
    if "no_report" in e:
        return "dart_report_not_found"
    if "no_accounts" in e or "accounts_api" in e:
        return "accounts_api_empty_list"
    if "alias" in e:
        return "accounts_present_alias_missing"
    if "consolidated" in e or "ofs" in e or "cfs" in e:
        return "consolidated_vs_separate_mismatch"
    if "dart" in e and ("api" in e or "key" in e or "401" in e or "403" in e):
        return "dart_api_no_response"
    if "parse" in e or "json" in e or "decode" in e:
        return "parsing_error"
    return "dart_api_no_response"


def classify_field_missing(
    *,
    field: str,
    ticker: str,
    available: bool,
    fund: dict[str, Any] | None,
    enrich_error: str,
    dart_credentials: bool,
    has_corp_code: bool,
    as_of: str,
) -> str:
    if available:
        return "not_applicable"
    if field == "treasury" and not dart_credentials:
        return "dart_api_no_response"
    if not has_corp_code:
        return "ticker_mapping_error"
    if enrich_error:
        mapped = _map_enrich_error_to_category(enrich_error)
        if mapped in MISSING_REASON_CATEGORIES:
            return mapped
        if field in ("ocf", "fcf", "debt", "cash", "net_cash"):
            cat = _map_enrich_error_to_category(enrich_error)
            if cat != "dart_api_no_response":
                return cat
        return _map_enrich_error_to_category(enrich_error)
    if not dart_credentials:
        return "dart_api_no_response"
    if fund:
        enriched_at = str(fund.get("enriched_at") or fund.get("as_of") or "")
        age = _days_since(enriched_at[:10], as_of) if enriched_at else None
        if age is not None and age > STALE_ENRICH_DAYS:
            return "stale_cache"
        if _has(fund.get("report_date")) or _has(fund.get("period_end")):
            return "account_alias_not_matched"
        return "financial_statement_not_available"
    return "dart_report_not_found"


def _enrichment_status(
    fund: dict[str, Any] | None,
    enrich_error: str,
    *,
    as_of: str,
) -> str:
    if enrich_error:
        if "no_corp_code" in enrich_error:
            return "mapping_failed"
        if "no_report" in enrich_error or "no_accounts" in enrich_error:
            return "enrich_failed"
        return "enrich_error"
    if not fund:
        return "not_enriched"
    missing = str(fund.get("missing_reason") or "")
    if not missing:
        return "enriched"
    if missing and any(_has(fund.get(k)) for k in ("operating_cash_flow", "debt_ratio", "net_cash")):
        return "partial"
    age = _days_since(str(fund.get("enriched_at", ""))[:10], as_of)
    if age is not None and age > STALE_ENRICH_DAYS:
        return "stale"
    return "partial" if missing else "enriched"


def _suggest_manual_field(missing_fields: list[str]) -> str:
    if "net_cash" in missing_fields or "operating_cash_flow" in missing_fields:
        return "net_cash_override"
    if "treasury_share_ratio" in missing_fields:
        return "treasury_share_ratio_override"
    if "holding_company_discount_proxy" in missing_fields:
        return "holding_company_nav_discount_override"
    if "asset_value_discount_proxy" in missing_fields:
        return "real_estate_asset_value_override"
    return "evidence_note"


@dataclass
class CoverageAuditRow:
    ticker: str
    name: str
    price_available: bool
    ocf_available: bool
    fcf_available: bool
    debt_available: bool
    cash_available: bool
    net_cash_available: bool
    treasury_event_available: bool
    treasury_scan_ok: bool
    shareholder_return_available: bool
    data_quality_score: float
    missing_critical_count: int
    missing_reason_summary: str
    enrichment_status: str
    field_missing_categories: dict[str, str]


def build_coverage_audit_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    dart_credentials: bool = True,
) -> list[CoverageAuditRow]:
    from src.data_refresh.dart_corp_codes import build_ticker_corp_map
    from src.value_list.dart_disclosure import load_hakedaka_dart_signals
    from src.value_list.hakedaka_data_quality import build_hakedaka_data_quality_rows
    from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals

    registry = {
        str(r["ticker"]).zfill(6): str(r.get("name", ""))
        for r in resolve_hakedaka_registry(data_dir)
        if r.get("ticker")
    }
    tickers = list(registry.keys())
    corp_map = build_ticker_corp_map(data_dir, tickers)
    enrich_errors, enrich_details = _load_enrich_errors(data_dir)
    funds_raw = load_hakedaka_fundamentals(data_dir)
    manual = load_manual_overrides(data_dir)
    dart_by = (load_hakedaka_dart_signals(data_dir).get("tickers") or {})

    prices: set[str] = set()
    px_path = data_dir / "prices.csv"
    if px_path.exists():
        df = pd.read_csv(px_path, dtype=str, keep_default_na=False)
        prices = set(df["ticker"].astype(str).str.zfill(6))

    treasury_tickers: set[str] = set()
    tr_path = output_dir / "hakedaka_treasury_events.csv"
    if tr_path.exists():
        tr = pd.read_csv(tr_path, dtype=str, keep_default_na=False)
        treasury_tickers = set(tr["ticker"].astype(str).str.zfill(6))

    treasury_scan_by, _treasury_summary = _load_treasury_scan_status(output_dir)

    quality_by: dict[str, Any] = {}
    try:
        for q in build_hakedaka_data_quality_rows(data_dir, output_dir, as_of=as_of):
            quality_by[q.ticker] = q
    except Exception:
        pass

    evidence_missing: dict[str, int] = {}
    pack_path = output_dir / "hakedaka_top10_evidence_pack.json"
    if pack_path.exists():
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            for c in pack.get("candidates") or []:
                t = str(c.get("ticker", "")).zfill(6)
                evidence_missing[t] = len(c.get("missing_critical_fields") or [])
        except (json.JSONDecodeError, OSError):
            pass

    rows: list[CoverageAuditRow] = []
    for ticker, name in sorted(registry.items()):
        fund = apply_manual_to_fundamentals(funds_raw.get(ticker), manual.get(ticker))
        dart = dart_by.get(ticker, {})
        err_raw = enrich_errors.get(ticker, "")
        err = _normalize_enrich_error(err_raw, enrich_details.get(ticker))
        has_corp = ticker in corp_map

        ocf_ok = _has(fund.get("operating_cash_flow"))
        fcf_ok = _has(fund.get("free_cash_flow"))
        debt_ok = _has(fund.get("debt_ratio"))
        cash_ok = _has(fund.get("cash_and_equivalents"))
        net_cash_ok = _has(fund.get("net_cash"))
        treasury_ok = ticker in treasury_tickers
        treasury_scan = treasury_scan_by.get(ticker, {})
        treasury_scan_ok = bool(treasury_scan.get("scan_ok"))
        shr_ok = treasury_ok or bool(dart.get("cancel_disclosure") or dart.get("return_disclosure")) or _has(
            fund.get("shareholder_return_yield")
        )

        if treasury_scan_ok and not treasury_ok:
            treasury_field_cat = "not_applicable"
        else:
            treasury_field_cat = classify_field_missing(
                field="treasury", ticker=ticker, available=treasury_ok, fund=funds_raw.get(ticker),
                enrich_error=err, dart_credentials=dart_credentials, has_corp_code=has_corp, as_of=as_of,
            )

        field_cats = {
            "ocf": classify_field_missing(
                field="ocf", ticker=ticker, available=ocf_ok, fund=funds_raw.get(ticker),
                enrich_error=err, dart_credentials=dart_credentials, has_corp_code=has_corp, as_of=as_of,
            ),
            "fcf": classify_field_missing(
                field="fcf", ticker=ticker, available=fcf_ok, fund=funds_raw.get(ticker),
                enrich_error=err, dart_credentials=dart_credentials, has_corp_code=has_corp, as_of=as_of,
            ),
            "debt": classify_field_missing(
                field="debt", ticker=ticker, available=debt_ok, fund=funds_raw.get(ticker),
                enrich_error=err, dart_credentials=dart_credentials, has_corp_code=has_corp, as_of=as_of,
            ),
            "cash": classify_field_missing(
                field="cash", ticker=ticker, available=cash_ok, fund=funds_raw.get(ticker),
                enrich_error=err, dart_credentials=dart_credentials, has_corp_code=has_corp, as_of=as_of,
            ),
            "net_cash": classify_field_missing(
                field="net_cash", ticker=ticker, available=net_cash_ok, fund=funds_raw.get(ticker),
                enrich_error=err, dart_credentials=dart_credentials, has_corp_code=has_corp, as_of=as_of,
            ),
            "treasury": treasury_field_cat,
            "shareholder_return": (
                "not_applicable" if shr_ok else classify_field_missing(
                    field="shareholder_return", ticker=ticker, available=False, fund=funds_raw.get(ticker),
                    enrich_error=err, dart_credentials=dart_credentials, has_corp_code=has_corp, as_of=as_of,
                )
            ),
        }

        missing_cats = [f"{k}:{v}" for k, v in field_cats.items() if v != "not_applicable"]
        q = quality_by.get(ticker)
        missing_critical = evidence_missing.get(ticker)
        if missing_critical is None:
            missing_critical = sum(
                1 for ok in (ocf_ok, fcf_ok, debt_ok, net_cash_ok) if not ok
            ) + (0 if treasury_ok else 1)

        rows.append(
            CoverageAuditRow(
                ticker=ticker,
                name=name,
                price_available=ticker in prices,
                ocf_available=ocf_ok,
                fcf_available=fcf_ok,
                debt_available=debt_ok,
                cash_available=cash_ok,
                net_cash_available=net_cash_ok,
                treasury_event_available=treasury_ok,
                treasury_scan_ok=treasury_scan_ok,
                shareholder_return_available=shr_ok,
                data_quality_score=float(q.data_quality_score) if q else 0.0,
                missing_critical_count=int(missing_critical),
                missing_reason_summary=";".join(missing_cats[:8]),
                enrichment_status=_enrichment_status(funds_raw.get(ticker), err, as_of=as_of),
                field_missing_categories=field_cats,
            )
        )
    return rows


def _coverage_pct(rows: list[CoverageAuditRow], attr: str) -> float:
    if not rows:
        return 0.0
    ok = sum(1 for r in rows if getattr(r, attr))
    return round(ok / len(rows) * 100, 1)


def _treasury_scan_coverage_pct(rows: list[CoverageAuditRow]) -> float:
    if not rows:
        return 0.0
    ok = sum(1 for r in rows if r.treasury_scan_ok)
    return round(ok / len(rows) * 100, 1)


def _treasury_event_found_rate_pct(rows: list[CoverageAuditRow]) -> float:
    if not rows:
        return 0.0
    ok = sum(1 for r in rows if r.treasury_event_available)
    return round(ok / len(rows) * 100, 1)


def _compare_targets(coverage: dict[str, float], targets: dict[str, float]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for target_key in DEFAULT_COVERAGE_TARGETS:
        target = targets.get(target_key, DEFAULT_COVERAGE_TARGETS.get(target_key, 0))
        actual = coverage.get(target_key, 0)
        if actual < target:
            warnings.append({
                "metric": target_key,
                "target_pct": target,
                "actual_pct": actual,
                "gap_pct": round(target - actual, 1),
                "level": "WARN",
            })
    return warnings


def build_manual_review_queue(
    data_dir: Path,
    output_dir: Path,
    audit_rows: list[CoverageAuditRow],
    *,
    as_of: str,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    score_by: dict[str, float] = {}
    for path in (output_dir / "hakedaka_preliminary_hunt_list.csv", output_dir / "hakedaka_primary_hunt_list.csv"):
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        col = "hakedaka_total_score" if "hakedaka_total_score" in df.columns else "total_score"
        for _, row in df.iterrows():
            t = str(row["ticker"]).zfill(6)
            try:
                score_by[t] = max(score_by.get(t, 0), float(row.get(col) or 0))
            except (TypeError, ValueError):
                pass

    evidence_by: dict[str, list[str]] = {}
    pack_path = output_dir / "hakedaka_top10_evidence_pack.json"
    if pack_path.exists():
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            for c in pack.get("candidates") or []:
                t = str(c.get("ticker", "")).zfill(6)
                evidence_by[t] = list(c.get("missing_critical_fields") or [])
        except (json.JSONDecodeError, OSError):
            pass

    queue: list[dict[str, Any]] = []
    for row in audit_rows:
        h_score = score_by.get(row.ticker, 0)
        if h_score < 50 and row.data_quality_score >= 60:
            continue
        missing = evidence_by.get(row.ticker) or []
        if not missing:
            missing = []
            if not row.ocf_available:
                missing.append("operating_cash_flow")
            if not row.net_cash_available:
                missing.append("net_cash")
            if not row.treasury_event_available:
                missing.append("treasury_share_ratio")
            if not row.debt_available:
                missing.append("debt_ratio")
            if not row.fcf_available:
                missing.append("free_cash_flow")
            if not row.cash_available:
                missing.append("holding_company_discount_proxy")

        if row.data_quality_score >= 75 and row.missing_critical_count <= 1:
            continue
        if not missing and row.data_quality_score >= 60:
            continue

        priority = round(h_score * 0.4 + (100 - row.data_quality_score) * 0.3 + row.missing_critical_count * 5, 1)
        queue.append({
            "ticker": row.ticker,
            "name": row.name,
            "priority": priority,
            "missing_fields": ";".join(missing),
            "suggested_manual_field": _suggest_manual_field(missing),
            "reason": (
                f"score={h_score:.0f} quality={row.data_quality_score:.0f} "
                f"missing_critical={row.missing_critical_count}"
            ),
            "evidence_pack_path": str(pack_path.relative_to(output_dir.parent)) if pack_path.exists() else "",
        })

    queue.sort(key=lambda x: float(x["priority"]), reverse=True)
    return queue[:top_n]


def write_hakedaka_coverage_audit(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    dart_credentials: bool | None = None,
    top_n_review: int = 10,
) -> dict[str, Any]:
    """Phase 4d — coverage audit CSV/JSON + manual review queue."""
    from src.settings.user_secrets import credential_status

    as_of_date = as_of or date.today().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_coverage_targets(data_dir)
    targets = load_coverage_targets(data_dir)

    if dart_credentials is None:
        dart_credentials = bool(credential_status(data_dir).get("dart"))

    audit_rows = build_coverage_audit_rows(
        data_dir, output_dir, as_of=as_of_date, dart_credentials=dart_credentials,
    )
    total = len(audit_rows) or 1

    coverage = {
        "price_coverage": _coverage_pct(audit_rows, "price_available"),
        "ocf_coverage": _coverage_pct(audit_rows, "ocf_available"),
        "fcf_coverage": _coverage_pct(audit_rows, "fcf_available"),
        "debt_coverage": _coverage_pct(audit_rows, "debt_available"),
        "cash_coverage": _coverage_pct(audit_rows, "cash_available"),
        "net_cash_coverage": _coverage_pct(audit_rows, "net_cash_available"),
        "treasury_scan_coverage": _treasury_scan_coverage_pct(audit_rows),
        "treasury_event_found_rate": _treasury_event_found_rate_pct(audit_rows),
    }

    category_counter: Counter[str] = Counter()
    field_category_detail: list[dict[str, Any]] = []
    for row in audit_rows:
        for field, cat in row.field_missing_categories.items():
            if cat != "not_applicable":
                category_counter[cat] += 1
                field_category_detail.append({"ticker": row.ticker, "field": field, "category": cat})

    missing_reason_agg = build_missing_reason_aggregation(
        field_category_detail, category_counter, total_tickers=len(audit_rows),
    )
    low_coverage_diagnosis = build_low_coverage_diagnosis(coverage, field_category_detail)
    target_warnings = _compare_targets(coverage, targets)

    from src.value_list.hakedaka_data_quality import build_hakedaka_data_quality_rows

    try:
        quality_rows = build_hakedaka_data_quality_rows(data_dir, output_dir, as_of=as_of_date)
        actionable_count = sum(1 for q in quality_rows if q.hunt_tier == "actionable_candidate")
    except Exception:
        actionable_count = sum(
            1 for r in audit_rows if r.data_quality_score >= 75 and r.missing_critical_count < 3
        )
    evidence_ready_count = actionable_count

    csv_path = output_dir / "hakedaka_coverage_audit.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_CSV_FIELDS)
        writer.writeheader()
        for row in audit_rows:
            writer.writerow({
                "ticker": row.ticker,
                "name": row.name,
                "price_available": row.price_available,
                "ocf_available": row.ocf_available,
                "fcf_available": row.fcf_available,
                "debt_available": row.debt_available,
                "cash_available": row.cash_available,
                "net_cash_available": row.net_cash_available,
                "treasury_event_available": row.treasury_event_available,
                "treasury_scan_ok": row.treasury_scan_ok,
                "shareholder_return_available": row.shareholder_return_available,
                "data_quality_score": row.data_quality_score,
                "missing_critical_count": row.missing_critical_count,
                "missing_reason_summary": row.missing_reason_summary,
                "enrichment_status": row.enrichment_status,
            })

    review_queue = build_manual_review_queue(
        data_dir, output_dir, audit_rows, as_of=as_of_date, top_n=top_n_review,
    )
    review_path = output_dir / "hakedaka_manual_review_queue.csv"
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANUAL_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(review_queue)

    avg_missing_critical = round(
        sum(r.missing_critical_count for r in audit_rows) / total, 2,
    )
    top10_missing = 0.0
    pack_path = output_dir / "hakedaka_top10_evidence_pack.json"
    if pack_path.exists():
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            cands = pack.get("candidates") or []
            if cands:
                top10_missing = round(
                    sum(len(c.get("missing_critical_fields") or []) for c in cands) / len(cands), 2,
                )
        except (json.JSONDecodeError, OSError):
            pass

    doc = {
        "mode": "shadow_coverage_audit",
        "authority": "none",
        "shadow_only": True,
        "as_of": as_of_date,
        "disclaimer": COVERAGE_AUDIT_DISCLAIMER,
        "tier_h_count": len(audit_rows),
        "coverage": coverage,
        "coverage_counts": {
            "ocf": sum(1 for r in audit_rows if r.ocf_available),
            "fcf": sum(1 for r in audit_rows if r.fcf_available),
            "debt": sum(1 for r in audit_rows if r.debt_available),
            "cash": sum(1 for r in audit_rows if r.cash_available),
            "net_cash": sum(1 for r in audit_rows if r.net_cash_available),
            "treasury_scan_ok": sum(1 for r in audit_rows if r.treasury_scan_ok),
            "treasury_event_found": sum(1 for r in audit_rows if r.treasury_event_available),
        },
        "targets_pct": targets,
        "target_warnings": target_warnings,
        "below_target": len(target_warnings) > 0,
        "missing_reason_aggregation": missing_reason_agg,
        "low_coverage_diagnosis": low_coverage_diagnosis,
        "financial_coverage_critical": any(
            coverage.get(k, 100) < LOW_COVERAGE_THRESHOLD_PCT
            for k in ("ocf_coverage", "fcf_coverage", "debt_coverage", "cash_coverage", "net_cash_coverage")
        ),
        "top_missing_reason_categories": [
            {"category": k, "count": v} for k, v in category_counter.most_common(8)
        ],
        "field_missing_categories": field_category_detail,
        "enrichment_status_counts": dict(Counter(r.enrichment_status for r in audit_rows)),
        "evidence_ready_candidate_count": evidence_ready_count,
        "execution_actionable_count": 0,
        "investment_actionable_count": 0,
        "actionable_candidate_count": evidence_ready_count,
        "avg_missing_critical_count": avg_missing_critical,
        "top10_avg_missing_critical_fields": top10_missing,
        "manual_review_queue_count": len(review_queue),
        "manual_review_top5": review_queue[:5],
        "dart_credentials_available": dart_credentials,
        "phase4e_enrich_categories": [
            c for c in MISSING_REASON_CATEGORIES
            if c.startswith("accounts_") or c in ("corp_code_mapping_error", "request_limit_or_api_error")
        ],
    }
    json_path = output_dir / "hakedaka_coverage_audit.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def run_hakedaka_coverage_audit_pipeline(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    force_fundamentals: bool = False,
    lookback_days: int = 90,
    top_n_evidence: int = 10,
    fetch_treasury: bool = True,
) -> dict[str, Any]:
    """Force enrich + evidence refresh + coverage audit (graceful fail on DART errors)."""
    from datetime import date as date_cls

    from src.settings.user_secrets import apply_secrets_to_env, credential_status
    from src.value_list.hakedaka_evidence_enrichment import (
        build_hakedaka_top10_evidence_pack,
        run_hakedaka_evidence_enrichment,
    )
    from src.value_list.ticker_registry import resolve_hakedaka_registry

    as_of_date = as_of or date_cls.today().isoformat()
    apply_secrets_to_env(data_dir)
    report: dict[str, Any] = {"as_of": as_of_date, "mode": "shadow_only", "phase": "4d-1", "steps": {}}

    try:
        ev = run_hakedaka_evidence_enrichment(
            data_dir,
            output_dir,
            as_of=as_of_date,
            force_fundamentals=force_fundamentals,
            build_evidence_pack=False,
            fetch_treasury=fetch_treasury and bool(credential_status(data_dir).get("dart")),
        )
        report["steps"]["evidence_enrichment"] = ev.get("steps", {})
    except Exception as exc:
        report["steps"]["evidence_enrichment"] = {"error": str(exc), "graceful": True}

    if fetch_treasury and credential_status(data_dir).get("dart"):
        try:
            from src.value_list.hakedaka_treasury_events import scan_hakedaka_treasury_events

            registry = resolve_hakedaka_registry(data_dir)
            tr = scan_hakedaka_treasury_events(
                data_dir, output_dir, registry, as_of=as_of_date, lookback_days=lookback_days,
            )
            report["steps"]["treasury_rescan"] = tr
        except Exception as exc:
            report["steps"]["treasury_rescan"] = {"error": str(exc), "graceful": True}

    try:
        from src.value_list.rerating_screener import write_hakedaka_rerating_outputs

        write_hakedaka_rerating_outputs(data_dir, output_dir, as_of=as_of_date)
        report["steps"]["rerating"] = {"ok": True}
    except Exception as exc:
        report["steps"]["rerating"] = {"error": str(exc), "graceful": True}

    try:
        pack = build_hakedaka_top10_evidence_pack(data_dir, output_dir, as_of=as_of_date)
        report["steps"]["evidence_pack"] = {"candidate_count": pack.get("candidate_count", 0)}
    except Exception as exc:
        report["steps"]["evidence_pack"] = {"error": str(exc), "graceful": True}

    try:
        audit = write_hakedaka_coverage_audit(
            data_dir, output_dir, as_of=as_of_date, top_n_review=top_n_evidence,
        )
        report["steps"]["coverage_audit"] = {
            "coverage": audit.get("coverage"),
            "target_warnings": audit.get("target_warnings"),
            "below_target": audit.get("below_target"),
        }
    except Exception as exc:
        report["steps"]["coverage_audit"] = {"error": str(exc), "graceful": True}

    return report


def write_coverage_runbook_markdown(output_dir: Path, audit: dict[str, Any]) -> Path:
    """Human-readable runbook snapshot."""
    path = output_dir / "hakedaka_coverage_runbook.md"
    cov = audit.get("coverage") or {}
    targets = audit.get("targets_pct") or {}
    warnings = audit.get("target_warnings") or []
    lines = [
        "# Hakedaka Coverage Runbook (shadow only)",
        "",
        f"> {COVERAGE_AUDIT_DISCLAIMER}",
        "",
        f"- **as_of**: {audit.get('as_of', '')}",
        f"- **Tier H count**: {audit.get('tier_h_count', 0)}",
        "",
        "## Coverage vs Target",
        "",
        "| Metric | Actual | Target | Status |",
        "|--------|-------:|-------:|--------|",
    ]
    for key in (
        "price_coverage", "ocf_coverage", "fcf_coverage", "debt_coverage",
        "cash_coverage", "net_cash_coverage", "treasury_scan_coverage",
    ):
        actual = cov.get(key, 0)
        target = targets.get(key, 0)
        status = "OK" if actual >= target else "WARN"
        lines.append(f"| {key} | {actual}% | {target}% | {status} |")
    lines.append(
        f"| treasury_event_found_rate (info) | {cov.get('treasury_event_found_rate', 0)}% | — | INFO |"
    )
    lines.extend(["", "## Target WARNs", ""])
    if warnings:
        for w in warnings:
            lines.append(f"- **WARN** {w.get('metric')}: actual {w.get('actual_pct')}% < target {w.get('target_pct')}%")
    else:
        lines.append("- All targets met.")
    lines.extend(["", "## Top Missing Reason Categories", ""])
    agg = audit.get("missing_reason_aggregation") or {}
    for item in agg.get("by_category") or audit.get("top_missing_reason_categories") or []:
        action = item.get("recommended_action", "")
        lines.append(f"- {item.get('category')}: {item.get('count')} — {action}")
    lines.extend(["", "## Low Coverage Diagnosis (P0)", ""])
    for item in audit.get("low_coverage_diagnosis") or []:
        lines.append(
            f"- **{item.get('metric')}** {item.get('actual_pct')}% — {item.get('recommended_action')}"
        )
    if not audit.get("low_coverage_diagnosis"):
        lines.append("- No financial metric below critical threshold.")
    lines.extend(["", "## Manual Review Queue (top 5)", ""])
    for item in audit.get("manual_review_top5") or []:
        lines.append(
            f"- {item.get('ticker')} {item.get('name')} — priority {item.get('priority')} — "
            f"{item.get('missing_fields')}"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
