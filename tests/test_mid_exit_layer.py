"""Mid-book unified ops cue: 보유 | 추가 (one strip)."""

from __future__ import annotations

from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.portfolio_widgets import (
    _chart_flow_synth_html,
    _mid_book_cue_html,
    _mid_buy_layer_html,
    _momentum_layer_html,
)
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


def _mid(**kw) -> PortfolioRow:
    extra = {"book": "ops", **kw.pop("extra", {})}
    return PortfolioRow(
        ticker=kw.get("ticker", "005930"),
        name=kw.get("name", "삼성"),
        weight_pct=10.0,
        initial_weight_pct=None,
        avg_price=100.0,
        current_price=kw.get("current_price", 100.0),
        target_price=kw.get("target_price", 200.0),
        target_progress=50.0,
        remaining_upside_pct=None,
        has_target=kw.get("has_target", True),
        target_detail="test",
        cap_pct=15.0,
        cap_headroom_pct=5.0,
        cap_near=False,
        ops_signal=kw.get("ops_signal", "hold"),
        ops_signal_label=kw.get("ops_signal_label", "유지"),
        ops_signal_detail=kw.get("ops_signal_detail", ""),
        ops_trim_pct=kw.get("ops_trim_pct"),
        extra=extra,
    )


def _short(**kw) -> PortfolioRow:
    row = _mid(**kw)
    row.extra = {**(row.extra or {}), "ops_book": "short", "book": "ops"}
    return row


def test_ui_copy_unified_ops() -> None:
    load_ui_copy.cache_clear()
    ops = copy_get("portfolio", "ops_cue_caption", default="")
    hold = copy_get("portfolio", "holdings_caption", default="")
    assert "보유" in ops and "추가" in ops
    assert "한 줄" in ops or "한 줄" in hold


def test_unified_hold_plus_buy1() -> None:
    row = _mid(
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
            "ladder_labels": ["매수1", "매수2", "줄이기", "절반", "전량"],
            "score_m": 50.0,
            "return_6m": 0.02,
        },
    )
    html = _mid_book_cue_html(row)
    assert "1 · 운영" in html
    assert "유지" in html
    assert "추가만 매수1" in html
    assert "|" in html
    assert html.count("1 · 운영") == 1
    assert "pf-review-card" in html and "pf-review-1" in html
    synth = _chart_flow_synth_html(row, chart=None, flow_data_dir=None)
    assert "pf-review-stack" in synth
    assert synth.index("1 · 운영") < synth.index("2 · 모멘텀")
    assert "익절 ·" not in synth
    assert "매수 ·" not in synth or "추가만" in synth


def test_unified_cash_half_holdoff_add() -> None:
    row = _mid(
        ops_signal="cash_half",
        ops_signal_label="환금",
        ops_signal_detail="목표가 도달 · 수량 절반",
        ops_trim_pct=50,
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
            "score_m": 40.0,
        },
    )
    html = _mid_book_cue_html(row)
    assert "환금" in html
    assert "추가 매수 보류" in html
    assert "pf-book-hot" in html


def test_unified_missing_target() -> None:
    row = _mid(
        has_target=False,
        ops_signal="missing",
        ops_signal_label="목표없음",
        target_price=None,
    )
    html = _mid_book_cue_html(row)
    assert "목표없음" in html or "익절 불가" in html
    assert "추가 매수 대기" in html
    assert "pf-book-danger" in html


def test_buy_layer_empty_no_double() -> None:
    assert _mid_buy_layer_html(_mid()) == ""


def test_short_skips_book_cue() -> None:
    row = _short(
        ops_signal="trim",
        ops_signal_label="축소",
        extra={"score_m": 45.0, "return_6m": -0.1, "trend_sign": "DOWN"},
    )
    assert _mid_book_cue_html(row) == ""
    html = _chart_flow_synth_html(row, chart=None, flow_data_dir=None)
    assert "1 · 운영" not in html
    assert "2 · 모멘텀" in html
    mom = _momentum_layer_html(row)
    assert "축소" in mom or "흐름" in mom


def test_hold_no_add_when_high() -> None:
    row = _mid(
        current_price=180.0,
        ops_signal="hold",
        ops_signal_label="유지",
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
            "ladder_labels": ["매수1", "매수2", "줄이기", "절반", "전량"],
        },
    )
    html = _mid_book_cue_html(row)
    assert "유지" in html
    assert "추가 매수 없음" in html
