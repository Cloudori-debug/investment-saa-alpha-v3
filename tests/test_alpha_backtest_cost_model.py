from __future__ import annotations

from pathlib import Path

from src.backtest.cost_model import (
    apply_round_trip_cost,
    apply_round_trip_cost_fraction,
    load_cost_assumptions,
    round_trip_cost_bps,
    sample_quality_banner,
    sample_quality_label,
)
from src.backtest.alpha_backtest import AlphaBacktestResult, write_alpha_backtest_outputs


def test_round_trip_cost_deducts_bps() -> None:
    assumptions = {
        "commission_bps": 15,
        "slippage_bps": 20,
        "securities_tx_tax_bps": 18,
    }
    assert round_trip_cost_bps(assumptions) == 53.0
    # 2.00% gross → 2.00 - 0.53 = 1.47
    assert apply_round_trip_cost(2.0, 63, assumptions) == 1.47
    assert abs(apply_round_trip_cost_fraction(0.02, 63, assumptions) - 0.0147) < 1e-9


def test_sample_quality_thresholds() -> None:
    assert sample_quality_label(16) == "insufficient"
    assert sample_quality_label(59) == "insufficient"
    assert sample_quality_label(60) == "preliminary"
    assert sample_quality_label(180) == "provisional"
    assert "예측력 판단 불가" in sample_quality_banner("insufficient")
    assert "예비 검증" in sample_quality_banner("preliminary")


def test_load_cost_assumptions_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "cost_assumptions.yaml"
    path.write_text(
        "commission_bps: 10\nslippage_bps: 5\nsecurities_tx_tax_bps: 20\nnote: test\n",
        encoding="utf-8",
    )
    a = load_cost_assumptions(path)
    assert a["commission_bps"] == 10
    assert a["slippage_bps"] == 5
    assert a["securities_tx_tax_bps"] == 20
    assert round_trip_cost_bps(a) == 35.0


def test_backtest_report_forces_insufficient_banner(tmp_path: Path) -> None:
    result = AlphaBacktestResult(
        dates=[f"2026-06-{i:02d}" for i in range(1, 17)],
        scored_dates=[f"2026-06-{i:02d}" for i in range(1, 17)],
        top_n=5,
        top_n_avg_return=0.1594,
        universe_avg_return=0.1394,
        top_n_excess=0.02,
        top_n_excess_net=0.0147,
        top_n_avg_return_net=0.1541,
        sample_quality="insufficient",
        round_trip_cost_bps=53.0,
        cost_assumptions={
            "commission_bps": 15,
            "slippage_bps": 20,
            "securities_tx_tax_bps": 18,
        },
        warnings=["예측력 판단 불가 — 참고용 (유효 표본 < 60일)"],
    )
    write_alpha_backtest_outputs(result, tmp_path)
    md = (tmp_path / "alpha_backtest_report.md").read_text(encoding="utf-8")
    assert "cost-adjusted" in md
    assert "예측력 판단 불가" in md
    assert "Gross Top-5 초과수익" in md
    assert "Net Top-5 초과수익" in md
    assert "insufficient" in md
    assert "scored_days_used" in md
    summary = (tmp_path / "alpha_backtest_summary.csv").read_text(encoding="utf-8")
    assert "top_n_excess_net" in summary
    assert "sample_quality" in summary
    assert "scored_days_used" in summary
    assert "price_history_days" in summary
