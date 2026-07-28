from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_refresh.tier_h import collect_tier_h_tickers
from src.value_list.hakedaka_data_quality import (
    apply_score_caps,
    compute_data_quality_row,
    write_hakedaka_data_quality_report,
    HakedakaDataQualityRow,
)
from src.value_list.hakedaka_refresh_pipeline import run_hakedaka_data_refresh

DATA = Path(__file__).resolve().parents[1] / "data"


def test_collect_tier_h_count() -> None:
    tickers = collect_tier_h_tickers(DATA)
    assert len(tickers) >= 45


def test_data_quality_score_low_without_price() -> None:
    row = compute_data_quality_row(
        ticker="999999",
        name="test",
        as_of="2026-06-26",
        has_price=False,
        price_date="",
        dart={},
        hk_fund=None,
        generic_fund=None,
        governance_events=0,
    )
    assert row.data_quality_score < 60
    assert row.hunt_tier == "preliminary"
    assert row.missing_price_flag is True


def test_apply_score_caps_without_ocf() -> None:
    quality = HakedakaDataQualityRow(
        ticker="1", name="t", price_fresh=True, missing_price_flag=False,
        dart_event_fresh=True, fundamentals_fresh=True,
        ocf_available=False, fcf_available=False, debt_available=False,
        net_cash_available=False, shareholder_return_available=False,
        governance_event_checked=True,
        financial_safety_verified=False,
        shareholder_return_verified=False,
        evidence_completeness_pct=10.0,
        data_incomplete=True,
        data_quality_score=35.0, hunt_tier="preliminary", missing_fields="ocf",
    )
    capped = apply_score_caps(
        {"value_trap_safety_score": 80.0, "valuation_asset_score": 90.0, "shareholder_return_score": 85.0},
        quality,
        dart={},
        hk_fund=None,
    )
    assert capped["value_trap_safety_score"] <= 55.0
    assert capped["valuation_asset_score"] <= 70.0


def test_quality_report_writes(tmp_path: Path) -> None:
    out = write_hakedaka_data_quality_report(DATA, tmp_path, as_of="2026-06-26", tier_h_coverage_pct=78.0)
    assert (tmp_path / "hakedaka_data_quality_report.json").exists()
    assert (tmp_path / "hakedaka_data_quality_report.csv").exists()
    assert out["tier_h_price_coverage_pct"] == 78.0


def test_refresh_pipeline_shadow_only(tmp_path: Path) -> None:
    report = run_hakedaka_data_refresh(DATA, tmp_path, as_of="2026-06-26")
    assert report["mode"] == "shadow_only"
    assert "tier_h_prices" in report["steps"]
    assert (tmp_path / "hakedaka_data_quality_report.json").exists()


def test_primary_hunt_requires_quality_60(tmp_path: Path) -> None:
    from src.value_list.rerating_screener import write_hakedaka_rerating_outputs

    write_hakedaka_rerating_outputs(DATA, tmp_path, as_of="2026-06-26", run_id="t")
    pre = pd.read_csv(tmp_path / "hakedaka_preliminary_hunt_list.csv")
    pri = pd.read_csv(tmp_path / "hakedaka_primary_hunt_list.csv")
    assert not pre.empty
    if not pri.empty:
        assert (pri["data_quality_score"].astype(float) >= 60).all()
