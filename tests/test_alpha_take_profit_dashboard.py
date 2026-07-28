"""Dashboard take-profit signal board exposure (display-only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ui.alpha_panel import prepare_take_profit_board_view, stair_band_label

PANEL = Path(__file__).resolve().parents[1] / "src" / "ui" / "alpha_panel.py"


def test_stair_band_labels() -> None:
    assert "목표 미설정" in stair_band_label(0, targets_missing=True)
    assert stair_band_label(65) == "70 미만 (—)"
    assert stair_band_label(75) == "70-80 (10%)"
    assert stair_band_label(85) == "80-90 (20%)"
    assert stair_band_label(95) == "90+ (30%)"


def test_prepare_view_marks_targets_missing() -> None:
    board = pd.DataFrame(
        [
            {
                "ticker": "030200",
                "name": "KT",
                "tp_signal_strength": 0,
                "exit_leg": "NONE",
                "trim_source_tag": "targets_missing",
                "targets_missing": True,
                "momentum_override_applied": False,
                "tp_rationale": "targets_missing",
                "tp_partial_frac": 0,
            }
        ]
    )
    view = prepare_take_profit_board_view(board)
    assert list(view.columns)[:3] == ["ticker", "name", "목표상태"]
    assert "근접도" in view.columns
    assert "targets_missing" not in view.columns
    assert "⚠️ 목표 미설정" in str(view.iloc[0]["목표상태"])
    assert view.iloc[0]["신호강도"] == "목표 미설정"
    assert "목표 미설정" in str(view.iloc[0]["계단구간"])
    assert view.iloc[0]["근접도"] == "—"


def test_prepare_view_shows_proximity_when_not_reached() -> None:
    board = pd.DataFrame(
        [
            {
                "ticker": "030200",
                "name": "KT",
                "tp_signal_strength": 0,
                "exit_leg": "NONE",
                "targets_missing": False,
                "fund_proximity_pct": "",
                "val_proximity_pct": 83.7,
                "momentum_override_applied": False,
                "tp_rationale": "TP-B 미달",
                "tp_partial_frac": 0,
                "trim_source_tag": "—",
            }
        ]
    )
    view = prepare_take_profit_board_view(board)
    assert view.iloc[0]["근접도"] == "VAL 83.7% 근접"
    assert view.iloc[0]["신호강도"] == "0.0"


def test_no_probability_wording_in_alpha_panel() -> None:
    src = PANEL.read_text(encoding="utf-8")
    for term in ("승률", "성공확률", "적중률", "도달확률", "예상확률"):
        assert term not in src
    # Legend may say 「예측·확률 아님」 (negation); ban predictive claims only.
    assert "확률로" not in src
    assert "신호강도" in src
    assert "근접도" in src


def test_take_profit_legend_terms_present() -> None:
    src = PANEL.read_text(encoding="utf-8")
    for term in (
        "FUND =",
        "VAL =",
        "근접도 =",
        "신호강도 =",
        "exit_leg =",
        "trim_source_tag",
        "FUND만 설정된 종목",
        "VAL만 설정된 종목",
        "둘 다 설정",
    ):
        assert term in src
    assert "예측·확률 아님" in src


def test_gap_legend_caption_present() -> None:
    portfolio = Path(__file__).resolve().parents[1] / "src" / "ui" / "portfolio_panel.py"
    src = portfolio.read_text(encoding="utf-8")
    assert "익절상태 = 목표 미설정 / 미도달(근접도%) / 도달(FUND·VAL·BOTH)" in src
    assert "알파 → 보유 리뷰 참고" in src
