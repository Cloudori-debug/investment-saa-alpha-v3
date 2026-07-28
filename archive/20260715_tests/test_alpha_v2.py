"""Alpha v2 Shadow Engine tests."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.alpha.schemas import PriceRecord, UniverseRecord
from src.alpha_v2.export_alpha_v2 import build_alpha_v2_export_sections, build_daily_report_alpha_v2_section
from src.alpha_v2.flow_overlay import apply_flow_overlay
from src.alpha_v2.institutional_flow_loader import InstitutionalFlowRow
from src.alpha_v2.market_filters import classify_market_tier
from src.alpha_v2.final_selector import select_final_candidates, select_top30
from src.alpha_v2.pipeline import run_alpha_v2_shadow
from src.alpha_v2.schemas import FLOW_SCORE_MAX, FLOW_SCORE_MIN
from src.alpha_v2.trigger_engine import build_flow_triggers
from src.models import PositionRow


def _universe_row(ticker: str, market: str = "KOSPI", sector: str = "tech") -> UniverseRecord:
    return UniverseRecord(
        ticker=ticker,
        name=ticker,
        market=market,
        security_type="common_stock",
        sector=sector,
        industry="",
        listed_date="2010-01-01",
        is_preferred=False,
        is_etf_etn=False,
        is_reit=False,
        is_spac=False,
        is_trading_halt=False,
        is_administrative_issue=False,
        audit_opinion="clean",
        capital_impairment=False,
    )


def _price(ticker: str, mcap: float, turnover: float) -> PriceRecord:
    return PriceRecord(
        ticker=ticker,
        date="2026-07-03",
        close=10000.0,
        market_cap=mcap,
        trading_value_20d=turnover,
        trading_value_60d=turnover,
        return_1m=0.0,
        return_3m=0.0,
        return_6m=0.0,
        return_12m=0.0,
        return_12m_ex_1m=0.0,
        high_52w=12000.0,
        distance_from_52w_high=-0.1,
        volatility_60d=0.2,
    )


def test_kospi_kosdaq_market_filter_separate_thresholds() -> None:
    kospi = classify_market_tier(_universe_row("005830", "KOSPI"), _price("005830", 600_000_000_000, 4_000_000_000))
    kosdaq_core = classify_market_tier(
        _universe_row("035720", "KOSDAQ"),
        _price("035720", 600_000_000_000, 6_000_000_000),
    )
    assert kospi.tier == "Mid"
    assert kosdaq_core.tier == "Core"


def test_kosdaq_1000_3000_shadow_watch() -> None:
    r = classify_market_tier(
        _universe_row("123456", "KOSDAQ"),
        _price("123456", 2_000_000_000_000, 2_000_000_000),
    )
    assert r.tier == "Shadow"
    assert r.shadow_watch is True
    assert r.buy_permission is False


def test_flow_score_range_minus20_plus20() -> None:
    rows = [{
        "ticker": "005830",
        "total_score_v1": 70.0,
        "market_cap": 10_000_000_000_000,
        "avg_turnover_20d": 50_000_000_000,
    }]
    flow = InstitutionalFlowRow(
        ticker="005830",
        name="DB손해보험",
        market="KOSPI",
        date="2026-07-03",
        pension_net_buy_1d=1e9,
        pension_net_buy_5d=5e9,
        pension_net_buy_20d=20e9,
        pension_net_buy_60d=40e9,
        foreign_net_buy_1d=1e9,
        foreign_net_buy_5d=5e9,
        foreign_net_buy_20d=15e9,
        institution_net_buy_1d=1e9,
        data_source="test",
        data_as_of="2026-07-03",
        stale_flag=False,
    )
    out = apply_flow_overlay(rows, {"005830": flow})
    assert FLOW_SCORE_MIN <= out[0]["flow_score"] <= FLOW_SCORE_MAX


def test_flow_to_market_cap_calculated() -> None:
    rows = [{"ticker": "005830", "total_score_v1": 60.0, "market_cap": 10_000_000_000_000, "avg_turnover_20d": 1e10}]
    flow = InstitutionalFlowRow(
        ticker="005830", name="x", market="KOSPI", date="2026-07-03",
        pension_net_buy_1d=1e9, pension_net_buy_5d=5e9, pension_net_buy_20d=20e9, pension_net_buy_60d=20e9,
        foreign_net_buy_1d=0, foreign_net_buy_5d=0, foreign_net_buy_20d=0,
        institution_net_buy_1d=1e9, data_source="t", data_as_of="2026-07-03", stale_flag=False,
    )
    out = apply_flow_overlay(rows, {"005830": flow})
    assert out[0]["pension_flow_to_market_cap"] == pytest.approx(20e9 / 10_000_000_000_000)


def test_flow_to_turnover_calculated() -> None:
    rows = [{"ticker": "005830", "total_score_v1": 60.0, "market_cap": 1e12, "avg_turnover_20d": 5e10}]
    flow = InstitutionalFlowRow(
        ticker="005830", name="x", market="KOSPI", date="2026-07-03",
        pension_net_buy_1d=1e9, pension_net_buy_5d=5e9, pension_net_buy_20d=10e9, pension_net_buy_60d=10e9,
        foreign_net_buy_1d=0, foreign_net_buy_5d=0, foreign_net_buy_20d=0,
        institution_net_buy_1d=1e9, data_source="t", data_as_of="2026-07-03", stale_flag=False,
    )
    out = apply_flow_overlay(rows, {"005830": flow})
    assert out[0]["pension_flow_to_turnover"] == pytest.approx(10e9 / 5e10)


def test_co_buy_and_co_sell_flags() -> None:
    rows = [{"ticker": "005830", "total_score_v1": 60.0, "market_cap": 1e12, "avg_turnover_20d": 5e10}]
    buy_flow = InstitutionalFlowRow(
        ticker="005830", name="x", market="KOSPI", date="2026-07-03",
        pension_net_buy_1d=1e9, pension_net_buy_5d=5e9, pension_net_buy_20d=10e9, pension_net_buy_60d=10e9,
        foreign_net_buy_1d=1e9, foreign_net_buy_5d=5e9, foreign_net_buy_20d=5e9,
        institution_net_buy_1d=1e9, data_source="t", data_as_of="2026-07-03", stale_flag=False,
    )
    sell_flow = InstitutionalFlowRow(
        ticker="005830", name="x", market="KOSPI", date="2026-07-03",
        pension_net_buy_1d=-1e9, pension_net_buy_5d=-5e9, pension_net_buy_20d=-10e9, pension_net_buy_60d=-10e9,
        foreign_net_buy_1d=-1e9, foreign_net_buy_5d=-5e9, foreign_net_buy_20d=-5e9,
        institution_net_buy_1d=-1e9, data_source="t", data_as_of="2026-07-03", stale_flag=False,
    )
    assert apply_flow_overlay(rows, {"005830": buy_flow})[0]["pension_foreign_co_buy"] is True
    assert apply_flow_overlay(rows, {"005830": sell_flow})[0]["pension_foreign_co_sell"] is True


def test_actual_buy_allowed_zero_forces_buy_permission_false() -> None:
    row = {
        "ticker": "005830",
        "name": "DB",
        "market": "KOSPI",
        "grade": "B",
        "executable_universe": True,
        "value_trap_flag": False,
        "liquidity_flag": True,
        "flow_score": 5,
        "pension_net_buy_20d": 1e9,
        "pension_streak_direction": "buy",
        "pension_streak_days": 6,
        "flow_signal_state": "accumulation",
        "flow_confidence": "HIGH",
        "flow_data_stale": False,
    }
    buy, _, _ = build_flow_triggers([row], actual_buy_allowed=0, no_trade=True, execution_scope="NO_TRADE")
    assert buy
    assert buy[0]["buy_permission"] is False


def test_no_trade_forces_review_only() -> None:
    row = {
        "ticker": "005830", "name": "DB", "market": "KOSPI", "grade": "B",
        "executable_universe": True, "value_trap_flag": False, "liquidity_flag": True,
        "flow_score": 5, "pension_net_buy_20d": 1e9, "pension_streak_direction": "buy",
        "pension_streak_days": 3, "flow_signal_state": "accumulation",
        "flow_confidence": "HIGH", "flow_data_stale": False,
    }
    buy, _, _ = build_flow_triggers([row], actual_buy_allowed=0, no_trade=True, execution_scope="NO_TRADE")
    assert buy[0]["review_only"] is True
    assert buy[0]["new_buy_allowed"] is False


def test_final_candidates_max_8() -> None:
    top30 = [
        {
            "ticker": f"{i:06d}",
            "market": "KOSPI" if i < 7 else "KOSDAQ",
            "sector": f"s{i % 4}",
            "total_score_v2_shadow": 100 - i,
            "grade": "B",
            "tier": "Core",
            "executable_universe": True,
            "shadow_watch": i >= 7,
        }
        for i in range(20)
    ]
    final = select_final_candidates(top30)
    assert len(final) <= 8


def test_kosdaq_candidates_max_3() -> None:
    top30 = [
        {
            "ticker": f"{i:06d}",
            "market": "KOSDAQ",
            "sector": f"s{i}",
            "total_score_v2_shadow": 100 - i,
            "grade": "B",
            "tier": "Shadow",
            "executable_universe": True,
            "shadow_watch": True,
        }
        for i in range(10)
    ]
    final = select_final_candidates(top30)
    assert sum(1 for r in final if r.get("market") == "KOSDAQ") <= 3


def test_sector_cap_30() -> None:
    top30 = [
        {
            "ticker": f"{i:06d}",
            "market": "KOSPI",
            "sector": "same",
            "total_score_v2_shadow": 100 - i,
            "grade": "A",
            "tier": "Core",
            "executable_universe": True,
            "shadow_watch": False,
        }
        for i in range(15)
    ]
    final = select_final_candidates(top30)
    assert len(final) >= 5


def test_reject_not_promoted_by_flow_only() -> None:
    top30 = select_top30([
        {"ticker": "005830", "grade": "Reject", "tier": "Core", "total_score_v2_shadow": 99, "flow_score": 20},
        {"ticker": "000660", "grade": "B", "tier": "Core", "total_score_v2_shadow": 80, "flow_score": 0},
    ])
    tickers = {r["ticker"] for r in top30}
    assert "005830" not in tickers


def _setup_pipeline_fixture(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    uni = pd.DataFrame([
        {"ticker": "005830", "name": "DB손해보험", "market": "KOSPI", "security_type": "common_stock",
         "sector": "insurance", "industry": "", "listed_date": "2010-01-01",
         "is_preferred": "false", "is_etf_etn": "false", "is_reit": "false", "is_spac": "false",
         "is_trading_halt": "false", "is_administrative_issue": "false", "audit_opinion": "clean", "capital_impairment": "false"},
        {"ticker": "035720", "name": "카카오", "market": "KOSDAQ", "security_type": "common_stock",
         "sector": "tech", "industry": "", "listed_date": "2010-01-01",
         "is_preferred": "false", "is_etf_etn": "false", "is_reit": "false", "is_spac": "false",
         "is_trading_halt": "false", "is_administrative_issue": "false", "audit_opinion": "clean", "capital_impairment": "false"},
    ])
    uni.to_csv(data / "universe.csv", index=False)
    prices = pd.DataFrame([
        {"date": "2026-07-03", "ticker": "005830", "close": 100000, "market_cap": 2_000_000_000_000,
         "trading_value_20d": 6_000_000_000, "trading_value_60d": 6e9,
         "return_1m": 0, "return_3m": 0, "return_6m": 0, "return_12m": 0, "return_12m_ex_1m": 0,
         "high_52w": 110000, "distance_from_52w_high": -0.05, "volatility_60d": 0.2},
        {"date": "2026-07-03", "ticker": "035720", "close": 50000, "market_cap": 2_500_000_000_000,
         "trading_value_20d": 6_000_000_000, "trading_value_60d": 6e9,
         "return_1m": 0, "return_3m": 0, "return_6m": 0, "return_12m": 0, "return_12m_ex_1m": 0,
         "high_52w": 60000, "distance_from_52w_high": -0.05, "volatility_60d": 0.25},
    ])
    prices.to_csv(data / "prices.csv", index=False)
    pd.DataFrame(columns=["ticker"]).to_csv(data / "fundamentals.csv", index=False)
    scored = pd.DataFrame([
        {"ticker": "005830", "name": "DB손해보험", "sector": "insurance", "quality_score": 70, "valuation_score": 65,
         "momentum_score": 60, "shareholder_return_score": 55, "base_score": 63, "penalty": 0, "total_score": 63,
         "grade": "B", "rank": 1, "eligible_action": "WATCH", "key_reason": ""},
        {"ticker": "035720", "name": "카카오", "sector": "tech", "quality_score": 68, "valuation_score": 62,
         "momentum_score": 58, "shareholder_return_score": 50, "base_score": 60, "penalty": 0, "total_score": 60,
         "grade": "B", "rank": 2, "eligible_action": "WATCH", "key_reason": ""},
    ])
    scored.to_csv(out / "alpha_scored_universe.csv", index=False)
    (out / "final_execution_decision.json").write_text(
        json.dumps({"execution_scope": "NO_TRADE", "system_status": "RED"}),
        encoding="utf-8",
    )
    return data, out


def test_ai_export_contains_alpha_v2_sections(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    sections = build_alpha_v2_export_sections(out)
    assert "alpha_v2_top30" in sections
    assert "alpha_v2_final_5_8" in sections
    assert "alpha_v2_policy_notes" in sections


def test_daily_report_contains_shadow_warning(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    lines = build_daily_report_alpha_v2_section(out)
    text = "\n".join(lines)
    assert "Alpha v2 is shadow-only" in text
    assert "Flow signal is not buy permission" in text


def test_no_target_write_from_alpha_v2(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    target_before = (data / "target_portfolio.csv").exists()
    run_alpha_v2_shadow(
        data,
        out,
        as_of="2026-07-03",
        positions=[PositionRow(
            ticker="005830", name="DB", asset_group="kr_alpha", sector="insurance",
            style="core", quantity=10, current_price=100000, avg_price=90000, current_value=1_000_000,
        )],
        targets=[],
    )
    summary = json.loads((out / "alpha_v2_summary.json").read_text(encoding="utf-8"))
    assert summary["target_write_occurred"] is False
    assert target_before is False


def test_stale_flow_data_does_not_create_trim_watch() -> None:
    stale_row = {
        "ticker": "005830", "name": "DB", "market": "KOSPI", "grade": "C",
        "flow_data_stale": True, "flow_signal_state": "stale", "flow_confidence": "LOW",
        "pension_net_buy_20d": None, "pension_streak_direction": "neutral",
    }
    _, trim, _ = build_flow_triggers([stale_row], actual_buy_allowed=0, no_trade=True, execution_scope="NO_TRADE")
    assert trim == []


def test_stale_flow_data_creates_confidence_low() -> None:
    rows = [{"ticker": "005830", "total_score_v1": 60.0, "market_cap": 1e12, "avg_turnover_20d": 5e10}]
    flow = InstitutionalFlowRow(
        ticker="005830", name="x", market="KOSPI", date="2026-07-03",
        pension_net_buy_1d=None, pension_net_buy_5d=None, pension_net_buy_20d=None, pension_net_buy_60d=None,
        foreign_net_buy_1d=None, foreign_net_buy_5d=None, foreign_net_buy_20d=None,
        institution_net_buy_1d=None, data_source="t", data_as_of="2026-07-03", stale_flag=True,
    )
    out = apply_flow_overlay(rows, {"005830": flow})
    assert out[0]["flow_confidence"] == "LOW"
    assert out[0]["flow_signal_state"] == "stale"


def test_kosdaq_universe_loaded_sets_missing_false(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    summary = run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    assert summary["kosdaq_universe_missing"] is False
    assert summary["coverage"]["kosdaq_universe_count"] >= 1


def test_kosdaq_unified_validation_requires_gates(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    summary = run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    assert summary["coverage"]["kosdaq_universe_count"] > 0
    assert "kosdaq_core_count" in summary["coverage"]
    assert summary["execution_context"]["no_trade"] is True
    final = pd.read_csv(out / "alpha_v2_final_candidates.csv", dtype=str, keep_default_na=False)
    if not final.empty:
        kosdaq = final[final["market"].str.upper() == "KOSDAQ"]
        if not kosdaq.empty:
            assert all(str(v).lower() in {"false", "0", ""} for v in kosdaq.get("buy_permission", []))


def test_kosdaq_shadow_not_buy_candidate() -> None:
    top30 = [
        {
            "ticker": "035720",
            "market": "KOSDAQ",
            "sector": "tech",
            "total_score_v2_shadow": 90,
            "grade": "B",
            "tier": "Shadow",
            "executable_universe": True,
            "shadow_watch": True,
        },
        {
            "ticker": "005830",
            "market": "KOSPI",
            "sector": "insurance",
            "total_score_v2_shadow": 85,
            "grade": "B",
            "tier": "Core",
            "executable_universe": True,
            "shadow_watch": False,
        },
    ]
    final = select_final_candidates(top30)
    kosdaq = [r for r in final if r.get("market") == "KOSDAQ"]
    for row in kosdaq:
        assert row.get("shadow_watch") is True
        assert row.get("suggested_shadow_weight", 99) <= 4.0


def test_kosdaq_single_weight_lower_than_kospi() -> None:
    kospi_w = None
    kosdaq_w = None
    top30 = [
        {"ticker": "005830", "market": "KOSPI", "sector": "a", "total_score_v2_shadow": 90,
         "grade": "B", "tier": "Core", "executable_universe": True, "shadow_watch": False},
        {"ticker": "035720", "market": "KOSDAQ", "sector": "b", "total_score_v2_shadow": 88,
         "grade": "B", "tier": "Mid", "executable_universe": True, "shadow_watch": False},
    ]
    final = select_final_candidates(top30)
    for row in final:
        if row.get("market") == "KOSPI":
            kospi_w = row.get("suggested_shadow_weight")
        if row.get("market") == "KOSDAQ":
            kosdaq_w = row.get("suggested_shadow_weight")
    if kospi_w is not None and kosdaq_w is not None:
        assert float(kosdaq_w) < float(kospi_w)


def test_ai_export_final_has_kosdaq_count(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    sections = build_alpha_v2_export_sections(out)
    final_section = sections.get("alpha_v2_final_5_8") or {}
    assert "kosdaq_final_count" in final_section
    assert "candidates" in final_section
    coverage = sections.get("alpha_v2_coverage") or {}
    assert "kosdaq_universe_count" in coverage


def test_daily_report_kosdaq_policy_lines(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    text = "\n".join(build_daily_report_alpha_v2_section(out))
    assert "KOSDAQ candidates are shadow/review-only" in text
    assert "KOSDAQ Shadow Watch is not buy permission" in text


def test_kosdaq_missing_creates_warning_not_failure(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    uni = pd.read_csv(data / "universe.csv", dtype=str)
    uni = uni[uni["market"] == "KOSPI"]
    uni.to_csv(data / "universe.csv", index=False)
    summary = run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    assert summary["kosdaq_universe_missing"] is True
    assert summary["kospi_kosdaq_unified_validation_complete"] is False


def test_v1_v2_scored_count_comparison_exists(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    summary = run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    cmp = summary.get("scored_count_comparison") or {}
    assert "v1_scored_count" in cmp
    assert "v2_scored_count" in cmp
    assert "difference_count" in cmp
    assert "filter_policy_diff" in cmp


def test_no_trade_keeps_all_alpha_v2_candidates_review_only(tmp_path: Path) -> None:
    data, out = _setup_pipeline_fixture(tmp_path)
    summary = run_alpha_v2_shadow(data, out, as_of="2026-07-03", positions=[], targets=[])
    assert summary["execution_context"]["no_trade"] is True
    df = pd.read_csv(out / "alpha_v2_final_candidates.csv", dtype=str, keep_default_na=False)
    if not df.empty and "review_only" in df.columns:
        assert all(str(v).lower() in {"true", "1"} for v in df["review_only"])


def test_stale_held_position_gets_warning_only() -> None:
    stale_row = {
        "ticker": "005830", "name": "DB", "market": "KOSPI", "grade": "B",
        "flow_data_stale": True, "flow_signal_state": "stale", "flow_confidence": "LOW",
    }
    _, trim, warnings = build_flow_triggers(
        [stale_row],
        actual_buy_allowed=0,
        no_trade=True,
        execution_scope="NO_TRADE",
        held_tickers={"005830"},
    )
    assert trim == []
    assert len(warnings) == 1
    assert warnings[0]["flow_data_stale_warning"] is True


def test_grade_c_alone_does_not_create_trim_without_fresh_flow() -> None:
    row = {
        "ticker": "005830", "name": "DB", "market": "KOSPI", "grade": "C", "grade_v1": "C",
        "flow_data_stale": False, "flow_confidence": "MEDIUM", "flow_signal_state": "neutral",
        "pension_net_buy_20d": 1e9, "pension_streak_direction": "buy", "pension_streak_days": 1,
    }
    _, trim, _ = build_flow_triggers([row], actual_buy_allowed=0, no_trade=True, execution_scope="NO_TRADE")
    assert trim == []


def test_trim_watch_detail_validation_passes_fresh_trim() -> None:
    from src.alpha_v2.trim_watch_audit import build_trim_watch_detail_rows, validate_trim_watch_detail

    scored = {
        "005830": {
            "ticker": "005830", "name": "DB", "sector": "insurance", "market": "KOSPI",
            "grade_v1": "B", "grade": "C", "total_score_v1": 55, "total_score_v2_shadow": 50,
            "flow_confidence": "HIGH", "flow_data_stale": False,
            "pension_streak_direction": "sell", "pension_streak_days": 6,
            "pension_net_buy_20d": -1e9, "pension_foreign_co_sell": True,
            "turning_sell_signal": False,
        }
    }
    trim = [{
        "ticker": "005830", "name": "DB", "market": "KOSPI", "grade": "C",
        "flow_confidence": "HIGH", "reason": "trim review only — pension_sell_streak>=5; pension_foreign_co_sell",
        "buy_permission": False, "review_only": True,
    }]
    detail = build_trim_watch_detail_rows(trim, scored, positions=[], targets=[], positions_meta={})
    result = validate_trim_watch_detail(detail)
    assert result["passed"] is True
    assert detail[0]["trim_category"] == "informational"
