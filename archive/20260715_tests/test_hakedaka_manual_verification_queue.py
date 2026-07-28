from __future__ import annotations

import csv
from pathlib import Path

from src.value_list.hakedaka_treasury_extraction import (
    enrich_event_row,
    extract_amount_from_text,
    extract_shares_from_text,
    extract_treasury_event_details,
)


def test_extract_억원_and_shares() -> None:
    text = "자기주식취득결정 50억원 100만주 2026-01-01~2026-06-30"
    details = extract_treasury_event_details(text, "treasury_acquire")
    assert details["amount"] == 5_000_000_000.0
    assert details["shares"] == 1_000_000.0
    assert details["treasury_event_confidence"] in ("high", "medium")
    assert details["period_start"] == "2026-01-01"


def test_extract_amount_억() -> None:
    assert extract_amount_from_text("소각금액 12.5억원") == 1_250_000_000.0


def test_extract_shares_천주() -> None:
    assert extract_shares_from_text("소각주식수 500천주") == 500_000.0


def test_enrich_event_row_from_title() -> None:
    row = {
        "event_type": "treasury_acquire",
        "source_report_name": "주요사항보고서(자기주식취득결정) 30억원 50,000주",
        "text_evidence": "",
        "extraction_confidence": "text_only",
    }
    out = enrich_event_row(row)
    assert out.get("announced_amount") == 3_000_000_000.0
    assert out.get("announced_share_count") == 50_000.0
    assert out.get("treasury_event_confidence") in ("high", "medium")


def test_reanalyze_writes_confidence(tmp_path) -> None:
    from src.value_list.hakedaka_manual_verification_queue import reanalyze_treasury_events_csv

    path = tmp_path / "hakedaka_treasury_events.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
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
            "source_url_or_receipt_no": "123",
            "text_evidence": "자기주식취득결정",
            "extraction_confidence": "text_only",
        })
    result = reanalyze_treasury_events_csv(tmp_path, as_of="2026-06-28")
    assert result["events"] == 1
    text = path.read_text(encoding="utf-8-sig")
    assert "treasury_event_confidence" in text


def test_top_candidate_verification_fields(tmp_path) -> None:
    from src.value_list.hakedaka_manual_verification_queue import (
        TOP_CANDIDATE_VERIFICATION_FIELDS,
        run_hakedaka_manual_verification_queue,
    )

    out = tmp_path / "outputs"
    out.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    report = run_hakedaka_manual_verification_queue(data, out, as_of="2026-06-28", top_n=5)
    assert report["phase"] == "4g"
    assert (out / "hakedaka_nav_manual_review_queue.csv").exists()
    assert (out / "hakedaka_top_candidate_verification.csv").exists()
    assert "verification_status" in TOP_CANDIDATE_VERIFICATION_FIELDS
