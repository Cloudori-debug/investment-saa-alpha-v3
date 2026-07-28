from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.alpha_v0_2.classifier import classify_row
from src.alpha_v0_2.pipeline import run_alpha_v0_2_shadow
from src.alpha_v0_2.risk_budget import portfolio_risk_budget
from src.alpha_v0_2.schemas import ScoredRow
from src.models import PositionRow


def _write_minimal_alpha_v02_fixtures(data_dir: Path, output_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "alpha_v0_2.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "data" / "alpha_v0_2.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (data_dir / "universe_filter.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "data" / "universe_filter.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (data_dir / "universe.csv").write_text(
        "ticker,name,market,security_type,sector\n"
        "005830,DB손해보험,KOSPI,common_stock,insurance\n"
        "069500,KODEX200,KOSPI,etf,etf\n",
        encoding="utf-8",
    )
    (data_dir / "fundamentals.csv").write_text(
        "ticker,period_end,report_date,usable_from_date,roe,roa,operating_margin,"
        "gross_profitability,debt_ratio,interest_coverage,per,pbr,fcf,operating_cash_flow,"
        "earnings_yoy,dividend_yield,ev_ebitda\n"
        "005830,2025-12-31,2026-03-01,2026-03-01,12,8,10,0.3,80,5,8,1.2,100,200,0.1,0.02,6\n",
        encoding="utf-8",
    )
    (data_dir / "prices.csv").write_text(
        "date,ticker,close,market_cap,trading_value_20d,trading_value_60d,"
        "return_1m,return_3m,return_6m,return_12m,return_12m_ex_1m,"
        "high_52w,distance_from_52w_high,volatility_60d\n"
        "2026-06-19,069500,40000,0,0,0,0.01,0.05,0.08,0.15,0.14,45000,0.9,0.2\n"
        "2026-06-19,005830,130000,8000000000000,3000000000,2500000000,"
        "0.02,0.06,0.09,0.12,0.11,140000,0.93,0.25\n",
        encoding="utf-8",
    )
    (output_dir / "alpha_candidates.csv").write_text(
        "rank,ticker,name,sector,quality_score,valuation_score,momentum_score,"
        "shareholder_return_score,base_score,penalty,total_score,grade,key_reason,eligible_action\n"
        "1,005830,DB손해보험,insurance,70,65,60,55,62,0,62,A,test,BUY_CANDIDATE\n",
        encoding="utf-8",
    )


def test_portfolio_overweight_blocks_new_buy() -> None:
    positions = [
        PositionRow(
            ticker="005830",
            name="DB손해보험",
            asset_group="kr_alpha",
            sector="insurance",
            current_value=30_000_000,
        ),
        PositionRow(
            ticker="CASH",
            name="예수금",
            asset_group="cash_short_bond",
            sector="cash",
            current_value=20_000_000,
        ),
    ]
    cfg = {
        "risk_budget": {
            "alpha_target_pct": 12.5,
            "alpha_max_pct": 22.5,
            "overweight_tolerance_pct": 1.0,
        }
    }
    budget = portfolio_risk_budget(positions, cfg)
    assert budget["alpha_budget_status"] == "OVERWEIGHT"
    assert budget["new_alpha_buy_allowed"] is False


def test_quality_fail_blocks_new_buy() -> None:
    row = classify_row(
        ScoredRow(
            ticker="X",
            name="X",
            exclusion_pass=True,
            quality_pass=False,
            momentum_pass=True,
            total_score=75,
        ),
        portfolio_new_buy_allowed=True,
        cfg={"score_bands": {"core_min": 80, "active_min": 70, "candidate_min": 60, "watch_min": 50}},
    )
    assert row.new_buy_status == "forbidden"


def test_momentum_fail_blocks_new_buy() -> None:
    row = classify_row(
        ScoredRow(
            ticker="X",
            name="X",
            exclusion_pass=True,
            quality_pass=True,
            momentum_pass=False,
            total_score=82,
            rel_return_90d=-3,
            rel_return_120d=-4,
        ),
        portfolio_new_buy_allowed=True,
        cfg={"score_bands": {"core_min": 80, "active_min": 70, "candidate_min": 60, "watch_min": 50}},
    )
    assert row.new_buy_status == "forbidden"


def test_run_alpha_v0_2_shadow_outputs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _write_minimal_alpha_v02_fixtures(data_dir, output_dir)

    positions = [
        PositionRow(
            ticker="005830",
            name="DB손해보험",
            asset_group="kr_alpha",
            sector="insurance",
            current_value=30_000_000,
        ),
        PositionRow(
            ticker="CASH",
            name="예수금",
            asset_group="cash_short_bond",
            sector="cash",
            current_value=20_000_000,
        ),
    ]
    result = run_alpha_v0_2_shadow(
        data_dir,
        output_dir,
        as_of="2026-06-19",
        positions=positions,
        targets=[],
        legacy_output_dir=output_dir,
    )

    assert result.mode == "shadow"
    assert result.execution_authority == "v1.0.2"
    assert (output_dir / "alpha_v0_2_classification.csv").exists()
    assert (output_dir / "alpha_v0_2_shadow.json").exists()
    assert (output_dir / "alpha_v0_2_legacy_diff.json").exists()

    doc = json.loads((output_dir / "alpha_v0_2_shadow.json").read_text(encoding="utf-8"))
    assert doc["alpha_budget_status"] == "OVERWEIGHT"
    row = next(r for r in doc["rows"] if r["ticker"] == "005830")
    assert row["classification"] in {"Core", "Active", "Candidate", "Legacy", "Exit", "Watch", "Excluded"}
    assert row["new_buy_status"] != "allowed_if_budget"
