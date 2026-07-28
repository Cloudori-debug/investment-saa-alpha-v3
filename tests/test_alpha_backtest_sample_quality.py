"""Alpha lite backtest — scored_days_used vs price_history_days labeling."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.alpha_backtest import (
    AlphaBacktestResult,
    run_alpha_lite_backtest,
    write_alpha_backtest_outputs,
)


def _fake_scored_frame(seed: int = 0) -> pd.DataFrame:
    """Enough rows with distinct scores for pd.qcut(5)."""
    rows = []
    for i in range(10):
        rows.append(
            {
                "ticker": f"{i + 1:06d}",
                "total_score": float(40 + i * 5 + seed),
                "return_3m": float(0.01 * (i + 1)),
            }
        )
    return pd.DataFrame(rows)


def test_scored_days_used_not_price_history_days(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """가격 30일 · usable만 마지막 5일에 걸리는 합성 fixture → scored=5, price=30."""
    data = tmp_path / "data"
    data.mkdir()
    start = date(2026, 6, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(30)]
    usable_from = dates[-5]  # 마지막 5일에만 게이트 통과로 시뮬

    price_rows = []
    for d in dates:
        for t in range(1, 11):
            price_rows.append(
                {
                    "date": d,
                    "ticker": f"{t:06d}",
                    "close": "1000",
                    "market_cap": "600000000000",
                    "trading_value_20d": "2000000000",
                    "trading_value_60d": "2000000000",
                    "return_1m": "0.01",
                    "return_3m": "0.02",
                    "return_6m": "0.03",
                    "return_12m": "0.04",
                    "return_12m_ex_1m": "0.03",
                    "high_52w": "1100",
                    "distance_from_52w_high": "-0.09",
                    "volatility_60d": "0.2",
                }
            )
    pd.DataFrame(price_rows).to_csv(data / "prices_history.csv", index=False)

    (data / "cost_assumptions.yaml").write_text(
        "commission_bps: 15\nslippage_bps: 20\nsecurities_tx_tax_bps: 18\n",
        encoding="utf-8",
    )
    (data / "alpha_scoring.yaml").write_text(
        "score_weights: {quality: 0.3, valuation: 0.25, momentum: 0.2, shareholder_return: 0.15}\n",
        encoding="utf-8",
    )
    # fundamentals: usable_from_date 종류 1개 (경고 문구용)
    fund_rows = [
        {
            "ticker": f"{t:06d}",
            "usable_from_date": usable_from,
            "report_date": usable_from,
            "roe": "10",
        }
        for t in range(1, 11)
    ]
    pd.DataFrame(fund_rows).to_csv(data / "fundamentals.csv", index=False)

    def _fake_score(data_dir: Path, as_of: str, prices_by_ticker: dict, scoring_cfg: dict) -> pd.DataFrame:
        # usable_from_date 이전 날짜는 게이트와 동일하게 빈 DF
        if as_of < usable_from:
            return pd.DataFrame()
        return _fake_scored_frame(seed=int(as_of[-2:]))

    monkeypatch.setattr("src.backtest.alpha_backtest._score_on_date", _fake_score)
    monkeypatch.setattr(
        "src.backtest.alpha_backtest.load_alpha_scoring_config",
        lambda path: {"score_weights": {}},
    )

    result = run_alpha_lite_backtest(data)
    assert len(result.dates) == 30
    assert len(result.scored_dates) == 5
    assert result.scored_dates == dates[-5:]
    assert result.sample_quality == "insufficient"  # 5 < 60
    assert result.usable_from_date_kinds == 1

    out = tmp_path / "outputs"
    write_alpha_backtest_outputs(result, out)
    summary = (out / "alpha_backtest_summary.csv").read_text(encoding="utf-8")
    assert "scored_days_used" in summary
    assert "price_history_days" in summary
    assert ",5," in summary or summary.count("5") >= 1
    md = (out / "alpha_backtest_report.md").read_text(encoding="utf-8")
    assert "scored_days_used" in md
    assert "price_history_days" in md
    assert "전략 판단 근거로 사용하지 말 것" in md
    assert any("유효 표본" in w or "전략 판단" in w for w in result.warnings)


def test_report_shows_scored_not_price_days(tmp_path: Path) -> None:
    result = AlphaBacktestResult(
        dates=[f"2026-06-{i:02d}" for i in range(1, 31)],
        scored_dates=[f"2026-06-{i:02d}" for i in range(26, 31)],
        top_n=5,
        top_n_avg_return=0.10,
        universe_avg_return=0.08,
        top_n_excess=0.02,
        top_n_excess_net=0.0147,
        sample_quality="insufficient",
        usable_from_date_kinds=2,
        round_trip_cost_bps=53.0,
        cost_assumptions={
            "commission_bps": 15,
            "slippage_bps": 20,
            "securities_tx_tax_bps": 18,
        },
        warnings=[
            "예측력 판단 불가 — 참고용 (유효 표본 < 60일)",
            "PIT 재무 데이터가 단일 스냅샷(usable_from_date 종류 2개)이라 "
            "유효 표본이 가격 데이터 범위 대비 크게 작음 — 결과를 전략 판단 근거로 사용하지 말 것",
        ],
    )
    write_alpha_backtest_outputs(result, tmp_path)
    md = (tmp_path / "alpha_backtest_report.md").read_text(encoding="utf-8")
    assert "유효 기여 일수" in md
    assert "**5일**" in md
    assert "가격 이력 커버리지" in md
    assert "30일" in md
    assert "전략 판단 근거로 사용하지 말 것" in md
    summary = pd.read_csv(tmp_path / "alpha_backtest_summary.csv")
    assert int(summary.iloc[0]["scored_days_used"]) == 5
    assert int(summary.iloc[0]["price_history_days"]) == 30
    assert int(summary.iloc[0]["dates_used"]) == 5
