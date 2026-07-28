from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_refresh.dart_account_aliases import (
    ACCOUNT_ALIASES,
    compute_hakedaka_metrics,
    find_amount_aliases,
    normalize_account_name,
)
from src.value_list.hakedaka_evidence_enrichment import (
    build_hakedaka_top10_evidence_pack,
    run_hakedaka_evidence_enrichment,
    write_hakedaka_financial_enrich_report,
)
from src.value_list.hakedaka_manual_overrides import (
    ensure_manual_overrides_template,
    load_manual_overrides,
    validate_manual_overrides,
)
from src.value_list.hakedaka_treasury_events import (
    TREASURY_CSV_FIELDS,
    _classify_treasury_event,
)
from src.value_list.hakedaka_treasury_extraction import extract_treasury_event_details

DATA = Path(__file__).resolve().parents[1] / "data"


def test_account_alias_normalize() -> None:
    assert normalize_account_name("영업활동 현금흐름") == normalize_account_name("영업활동현금흐름")


def test_find_amount_aliases_operating_cash_flow() -> None:
    rows = [
        {
            "account_nm": "영업활동으로인한현금흐름",
            "sj_div": "CF",
            "thstrm_amount": "1,000,000",
        }
    ]
    val, name = find_amount_aliases(rows, "operating_cash_flow", sj_div="CF")
    assert val == 1_000_000.0
    assert "영업" in name


def test_compute_hakedaka_metrics_missing_reason() -> None:
    class Meta:
        pass

    metrics = compute_hakedaka_metrics([], Meta())
    assert "ocf" in metrics["missing_reason"]
    assert metrics["operating_cash_flow"] is None


def test_treasury_event_classification() -> None:
    assert _classify_treasury_event("자기주식취득결정") == "treasury_acquire"
    assert _classify_treasury_event("자기주식소각결정") == "treasury_cancel"


def test_treasury_amount_extraction() -> None:
    details = extract_treasury_event_details("총 10,000주, 500,000,000원 규모", "treasury_acquire")
    amt = details.get("amount")
    shares = details.get("shares")
    assert shares == 10_000.0
    assert amt == 500_000_000.0


def test_manual_overrides_template(tmp_path: Path) -> None:
    path = ensure_manual_overrides_template(tmp_path)
    assert path.exists()
    df = pd.read_csv(path)
    assert "net_cash_override" in df.columns


def test_manual_override_validation_warns(tmp_path: Path) -> None:
    path = ensure_manual_overrides_template(tmp_path)
    pd.DataFrame([{
        "ticker": "005930",
        "name": "Samsung",
        "net_cash_override": "1000",
        "manual_override_flag": "true",
        "source_date": "",
        "source_url": "",
        "evidence_note": "",
    }]).to_csv(path, index=False, encoding="utf-8-sig")
    warnings = validate_manual_overrides(tmp_path)
    assert any("missing_source_date" in w for w in warnings)


def test_financial_enrich_report_writes(tmp_path: Path) -> None:
    report = write_hakedaka_financial_enrich_report(DATA, tmp_path, as_of="2026-06-26")
    assert (tmp_path / "hakedaka_financial_enrich_report.json").exists()
    assert "coverage" in report
    assert "ocf_pct" in report["coverage"]


def test_evidence_enrichment_shadow_only(tmp_path: Path) -> None:
    report = run_hakedaka_evidence_enrichment(
        DATA, tmp_path, as_of="2026-06-26", build_evidence_pack=False, fetch_treasury=False,
    )
    assert report["mode"] == "shadow_only"
    assert report["phase"] == "4c"
    assert (tmp_path / "hakedaka_financial_enrich_report.json").exists()
    assert (DATA / "hakedaka_manual_overrides.csv").exists()


def test_top10_evidence_pack_from_hunt_lists(tmp_path: Path) -> None:
    pre = tmp_path / "hakedaka_preliminary_hunt_list.csv"
    pd.DataFrame([
        {"ticker": "005930", "name": "A", "hakedaka_total_score": 80, "data_quality_score": 55, "hunt_tier": "preliminary"},
        {"ticker": "000660", "name": "B", "hakedaka_total_score": 75, "data_quality_score": 62, "hunt_tier": "verified"},
    ]).to_csv(pre, index=False, encoding="utf-8-sig")
    pack = build_hakedaka_top10_evidence_pack(DATA, tmp_path, as_of="2026-06-26")
    assert (tmp_path / "hakedaka_top10_evidence_pack.json").exists()
    assert pack["candidate_count"] == 2
    assert pack["candidates"][0]["why_not_actionable_yet"]


def test_treasury_csv_fields_complete() -> None:
    assert "extraction_confidence" in TREASURY_CSV_FIELDS
    assert "text_evidence" in TREASURY_CSV_FIELDS


def test_account_aliases_cover_core_fields() -> None:
    for key in ("operating_cash_flow", "cash_and_equivalents", "short_term_borrowings", "capex"):
        assert key in ACCOUNT_ALIASES
        assert len(ACCOUNT_ALIASES[key]) >= 2
