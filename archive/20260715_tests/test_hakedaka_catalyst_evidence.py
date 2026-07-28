from __future__ import annotations

import io
import zipfile
from pathlib import Path

from src.data_refresh.dart_document_fetch import (
    _extract_text_from_zip,
    normalize_document_text,
)
from src.value_list.hakedaka_treasury_extraction import (
    enrich_event_row,
    extract_catalyst_from_body,
)


def test_normalize_document_text_strips_tags() -> None:
    raw = "<html><body><p>취득예정금액 10억원</p><p>취득예정주식수 50,000주</p></body></html>"
    text = normalize_document_text(raw)
    assert "10억원" in text
    assert "<p>" not in text


def test_extract_catalyst_from_body_acquire() -> None:
    body = (
        "이사회 결의일 2026-06-01 자기주식 취득 결정 "
        "취득예정금액 30억원 취득예정주식수 100,000주 "
        "취득기간 2026-06-01 ~ 2026-09-30 취득목적 주주환원"
    )
    cat = extract_catalyst_from_body(body, "treasury_acquire")
    assert cat["buyback_announced_amount"] == 3_000_000_000.0
    assert cat["buyback_announced_shares"] == 100_000.0
    assert cat["extraction_confidence"] == "high"
    assert cat["board_resolution_date"] == "2026-06-01"


def test_enrich_event_row_with_body() -> None:
    row = {
        "event_type": "treasury_cancel",
        "source_report_name": "주식소각결정",
        "extraction_confidence": "text_only",
    }
    body = "소각주식수 20,000주 소각금액 5억원 소각완료"
    out = enrich_event_row(row, body_text=body)
    assert out["cancellation_announced_shares"] == 20_000.0
    assert out["extraction_confidence"] in ("high", "medium")
    assert out.get("body_extraction_used") is True


def test_extract_text_from_zip() -> None:
    buf = io.BytesIO()
    xml = "<?xml version='1.0'?><root>소각주식수 1,000주 소각금액 2억원</root>"
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("20260617000178.xml", xml.encode("utf-8"))
    text = _extract_text_from_zip(buf.getvalue())
    assert "소각주식수" in text
    assert "2억원" in text


def test_extract_shinil_acquire_body() -> None:
    body = (
        "취득예정주식(주) 보통주식 1,651,000 "
        "취득예정금액(원) 보통주식 1,999,361,000 "
        "취득예상기간 시작일 2026년 06월 18일 종료일 2026년 09월 17일"
    )
    cat = extract_catalyst_from_body(body, "treasury_acquire")
    assert cat["buyback_announced_shares"] == 1_651_000.0
    assert cat["buyback_announced_amount"] == 1_999_361_000.0
    assert cat["extraction_confidence"] == "high"


def test_run_catalyst_evidence_offline(tmp_path) -> None:
    import csv

    from src.value_list.hakedaka_catalyst_evidence import run_hakedaka_catalyst_evidence

    out = tmp_path / "outputs"
    out.mkdir()
    data = tmp_path / "data"
    data.mkdir()

    events_path = out / "hakedaka_treasury_events.csv"
    with events_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "as_of", "ticker", "name", "event_date", "event_type",
                "announced_amount", "announced_share_count",
                "cancellation_amount", "cancellation_share_count",
                "buyback_period_start", "buyback_period_end",
                "source_report_name", "source_url_or_receipt_no",
                "text_evidence", "extraction_confidence",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "as_of": "2026-06-28",
            "ticker": "002700",
            "name": "신일전자",
            "event_date": "2026-06-17",
            "event_type": "treasury_acquire",
            "announced_amount": "",
            "announced_share_count": "",
            "cancellation_amount": "",
            "cancellation_share_count": "",
            "buyback_period_start": "",
            "buyback_period_end": "",
            "source_report_name": "자기주식취득결정 10억원 20,000주",
            "source_url_or_receipt_no": "20260617000178",
            "text_evidence": "",
            "extraction_confidence": "text_only",
        })

    doc_dir = out / "dart_documents" / "hakedaka"
    doc_dir.mkdir(parents=True)
    (doc_dir / "002700_20260617000178.txt").write_text(
        "취득예정금액 10억원 취득예정주식수 20,000주 취득목적 주주환원",
        encoding="utf-8",
    )

    report = run_hakedaka_catalyst_evidence(
        data, out, as_of="2026-06-28", fetch_documents=False, use_cache=True,
    )
    assert report["phase"] == "4h"
    assert (out / "hakedaka_catalyst_evidence.csv").exists()
    assert (out / "hakedaka_phase4h_report.json").exists()

    cat = (out / "hakedaka_catalyst_evidence.json").read_text(encoding="utf-8")
    assert "buyback_announced_amount" in cat
