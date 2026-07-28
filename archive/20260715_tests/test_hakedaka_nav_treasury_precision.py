from __future__ import annotations

from src.data_refresh.dart_account_aliases import compute_hakedaka_metrics, find_amount_aliases


def test_alias_178320_operating_cash_flow() -> None:
    rows = [
        {
            "account_nm": "영업활동으로 인한 순현금흐름액",
            "sj_div": "CF",
            "thstrm_amount": "5000000",
        },
        {"account_nm": "유형자산의 취득", "sj_div": "CF", "thstrm_amount": "-1000000"},
        {"account_nm": "현금및현금성자산", "sj_div": "BS", "thstrm_amount": "2000000"},
        {"account_nm": "부채총계", "sj_div": "BS", "thstrm_amount": "3000000"},
        {"account_nm": "자본총계", "sj_div": "BS", "thstrm_amount": "8000000"},
        {"account_nm": "단기차입부채", "sj_div": "BS", "thstrm_amount": "500000"},
        {"account_nm": "분기순이익(손실)", "sj_div": "CIS", "thstrm_amount": "100000"},
    ]
    val, name = find_amount_aliases(rows, "operating_cash_flow", sj_div="CF")
    assert val == 5_000_000.0
    assert "순현금" in name

    class Meta:
        pass

    metrics = compute_hakedaka_metrics(rows, Meta())
    assert metrics["operating_cash_flow"] == 5_000_000.0
    assert metrics["fcf_confidence"] == "high"
    assert metrics["debt_ratio"] is not None


def test_treasury_precision_fields(tmp_path) -> None:
    from src.value_list.hakedaka_nav_treasury_precision import (
        TREASURY_PRECISION_FIELDS,
        build_treasury_precision_rows,
        write_treasury_precision_csv,
    )

    rows = build_treasury_precision_rows(tmp_path, tmp_path, as_of="2026-06-28")
    path = write_treasury_precision_csv(tmp_path, rows)
    assert path.exists()
    assert "treasury_share_ratio" in TREASURY_PRECISION_FIELDS
    assert "cancellation_progress_pct" in TREASURY_PRECISION_FIELDS


def test_merge_treasury_events_with_precision(tmp_path) -> None:
    import csv

    from src.value_list.hakedaka_nav_treasury_precision import merge_treasury_events_with_precision
    from src.value_list.hakedaka_treasury_events import TREASURY_CSV_FIELDS_EXTENDED

    events_path = tmp_path / "hakedaka_treasury_events.csv"
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
            "ticker": "005930",
            "name": "삼성전자",
            "event_date": "2026-06-01",
            "event_type": "treasury_acquire",
            "announced_amount": "1000000",
            "announced_share_count": "1000",
            "cancellation_amount": "",
            "cancellation_share_count": "",
            "buyback_period_start": "2026-06-01",
            "buyback_period_end": "2026-06-30",
            "source_report_name": "자기주식취득결정",
            "source_url_or_receipt_no": "123",
            "text_evidence": "자기주식취득결정",
            "extraction_confidence": "high",
        })
    precision = [{
        "as_of": "2026-06-28",
        "ticker": "005930",
        "name": "삼성전자",
        "treasury_share_count": None,
        "treasury_share_ratio": 0.05,
        "treasury_share_value": None,
        "buyback_announced_amount": None,
        "buyback_announced_shares": None,
        "cancellation_announced_amount": None,
        "cancellation_announced_shares": None,
        "cancellation_completed_amount": None,
        "cancellation_completed_shares": None,
        "cancellation_progress_pct": None,
        "buyback_period_start": "",
        "buyback_period_end": "",
        "extraction_confidence": "high",
        "text_evidence": "",
        "missing_reason": "",
    }]
    out = merge_treasury_events_with_precision(tmp_path, precision)
    assert out is not None
    text = out.read_text(encoding="utf-8-sig")
    assert "treasury_share_ratio" in text
    assert "buyback_announced_amount" in TREASURY_CSV_FIELDS_EXTENDED


def test_nav_proxy_group1_only(tmp_path) -> None:
    from src.value_list.hakedaka_nav_treasury_precision import build_nav_proxy_rows

    rows = build_nav_proxy_rows(tmp_path, as_of="2026-06-28")
    assert all(int(r.get("group_id", 0)) == 1 for r in rows) or rows == []
