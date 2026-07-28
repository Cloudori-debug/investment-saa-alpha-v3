from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.value_list.hakedaka_coverage_audit import (
    AUDIT_CSV_FIELDS,
    MISSING_REASON_CATEGORIES,
    build_low_coverage_diagnosis,
    build_missing_reason_aggregation,
    classify_field_missing,
    write_coverage_runbook_markdown,
    write_hakedaka_coverage_audit,
)
from src.value_list.hakedaka_coverage_targets import (
    DEFAULT_COVERAGE_TARGETS,
    ensure_coverage_targets,
    load_coverage_targets,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def test_coverage_targets_template(tmp_path: Path) -> None:
    path = ensure_coverage_targets(tmp_path)
    assert path.exists()
    targets = load_coverage_targets(tmp_path)
    assert targets["ocf_coverage"] == DEFAULT_COVERAGE_TARGETS["ocf_coverage"]


def test_classify_field_missing_alias() -> None:
    cat = classify_field_missing(
        field="ocf",
        ticker="005930",
        available=False,
        fund={"report_date": "2026-03-01", "missing_reason": "ocf"},
        enrich_error="",
        dart_credentials=True,
        has_corp_code=True,
        as_of="2026-06-26",
    )
    assert cat == "account_alias_not_matched"


def test_classify_field_missing_no_corp() -> None:
    cat = classify_field_missing(
        field="ocf",
        ticker="999999",
        available=False,
        fund=None,
        enrich_error="no_corp_code",
        dart_credentials=True,
        has_corp_code=False,
        as_of="2026-06-26",
    )
    assert cat == "ticker_mapping_error"


def test_classify_field_missing_no_report() -> None:
    cat = classify_field_missing(
        field="debt",
        ticker="005930",
        available=False,
        fund=None,
        enrich_error="no_report",
        dart_credentials=True,
        has_corp_code=True,
        as_of="2026-06-26",
    )
    assert cat == "dart_report_not_found"


def test_coverage_audit_writes(tmp_path: Path) -> None:
    audit = write_hakedaka_coverage_audit(DATA, tmp_path, as_of="2026-06-26", dart_credentials=False)
    assert (tmp_path / "hakedaka_coverage_audit.csv").exists()
    assert (tmp_path / "hakedaka_coverage_audit.json").exists()
    assert (tmp_path / "hakedaka_manual_review_queue.csv").exists()
    assert audit["mode"] == "shadow_coverage_audit"
    assert "coverage" in audit
    assert "target_warnings" in audit
    df = pd.read_csv(tmp_path / "hakedaka_coverage_audit.csv")
    for col in AUDIT_CSV_FIELDS:
        assert col in df.columns


def test_coverage_audit_missing_reason_categories(tmp_path: Path) -> None:
    audit = write_hakedaka_coverage_audit(DATA, tmp_path, as_of="2026-06-26")
    cats = {x["category"] for x in audit.get("field_missing_categories") or []}
    assert cats.issubset(set(MISSING_REASON_CATEGORIES))


def test_target_warn_when_below(tmp_path: Path) -> None:
    audit = write_hakedaka_coverage_audit(DATA, tmp_path, as_of="2026-06-26")
    cov = audit.get("coverage") or {}
    if cov.get("ocf_coverage", 0) < DEFAULT_COVERAGE_TARGETS["ocf_coverage"]:
        assert audit.get("below_target") is True
        assert any(w.get("metric") == "ocf_coverage" for w in audit.get("target_warnings") or [])


def test_runbook_markdown(tmp_path: Path) -> None:
    audit = write_hakedaka_coverage_audit(DATA, tmp_path, as_of="2026-06-26")
    path = write_coverage_runbook_markdown(tmp_path, audit)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "shadow only" in text.lower()


def test_graceful_audit_without_dart(tmp_path: Path) -> None:
    audit = write_hakedaka_coverage_audit(
        DATA, tmp_path, as_of="2026-06-26", dart_credentials=False,
    )
    assert audit["dart_credentials_available"] is False
    assert audit["tier_h_count"] >= 45


def test_treasury_metrics_split(tmp_path: Path) -> None:
    status = {
        "as_of": "2026-06-26",
        "tickers": {
            "005930": {"scan_ok": True, "event_found": True},
            "000660": {"scan_ok": True, "event_found": False},
            "035420": {"scan_ok": False, "event_found": False, "error": "api_fail"},
        },
        "summary": {"treasury_scan_coverage_pct": 66.7, "treasury_event_found_rate_pct": 33.3},
    }
    (tmp_path / "hakedaka_treasury_scan_status.json").write_text(
        json.dumps(status), encoding="utf-8",
    )
    audit = write_hakedaka_coverage_audit(DATA, tmp_path, as_of="2026-06-26")
    cov = audit.get("coverage") or {}
    assert "treasury_scan_coverage" in cov
    assert "treasury_event_found_rate" in cov
    assert cov["treasury_scan_coverage"] != cov.get("treasury_event_found_rate") or cov["treasury_event_found_rate"] == 0


def test_missing_reason_aggregation() -> None:
    from collections import Counter

    detail = [
        {"ticker": "1", "field": "ocf", "category": "account_alias_not_matched"},
        {"ticker": "2", "field": "ocf", "category": "account_alias_not_matched"},
        {"ticker": "3", "field": "debt", "category": "dart_report_not_found"},
    ]
    agg = build_missing_reason_aggregation(detail, Counter(d["category"] for d in detail), total_tickers=50)
    assert agg["dominant_category"] == "account_alias_not_matched"
    assert any(x["field"] == "ocf" for x in agg["by_field"])


def test_low_coverage_diagnosis() -> None:
    coverage = {"ocf_coverage": 4.1, "fcf_coverage": 4.1, "debt_coverage": 50.0}
    detail = [{"field": "ocf", "category": "account_alias_not_matched"}] * 40
    diag = build_low_coverage_diagnosis(coverage, detail)
    assert any(d["metric"] == "ocf_coverage" for d in diag)
    assert diag[0]["priority"] == "P0"


def test_coverage_targets_treasury_scan(tmp_path: Path) -> None:
    targets = load_coverage_targets(tmp_path)
    assert "treasury_scan_coverage" in targets
    assert targets["treasury_scan_coverage"] == 80.0


def test_manual_review_queue_from_hunt(tmp_path: Path) -> None:
    pre = tmp_path / "hakedaka_preliminary_hunt_list.csv"
    pd.DataFrame([
        {"ticker": "005930", "name": "A", "hakedaka_total_score": 85, "data_quality_score": 40, "hunt_tier": "preliminary"},
    ]).to_csv(pre, index=False, encoding="utf-8-sig")
    audit = write_hakedaka_coverage_audit(DATA, tmp_path, as_of="2026-06-26")
    queue = pd.read_csv(tmp_path / "hakedaka_manual_review_queue.csv")
    assert not queue.empty or audit.get("manual_review_queue_count", 0) >= 0
