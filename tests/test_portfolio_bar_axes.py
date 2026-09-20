"""Regression: price bar vs weight/cap bar stay on separate axes."""

from __future__ import annotations

from alpha_system.ui.services.portfolio_metrics import (
    classify_cap_tone,
    price_bar_view,
    weight_bar_view,
)
from alpha_system.ui.services.portfolio_widgets import (
    _rung_now_idx,
    render_price_bar_html,
    render_weight_bar_html,
)
from alpha_system.ui.services.context import PortfolioRow


def _row(
    *,
    weight: float,
    progress: float | None,
    cap: float = 35.0,
    has_target: bool = True,
) -> PortfolioRow:
    tone = classify_cap_tone(weight, cap)
    return PortfolioRow(
        ticker="000000",
        name="TEST",
        weight_pct=weight,
        initial_weight_pct=None,
        avg_price=100.0,
        current_price=100.0,
        target_price=200.0,
        target_progress=progress,
        remaining_upside_pct=None,
        has_target=has_target,
        target_detail="test",
        cap_pct=cap,
        cap_headroom_pct=round(cap - weight, 2),
        cap_near=tone == "warn",
        cap_over=tone == "danger",
        price_progress_pct=progress,
    )


def test_progress_80_weight_20_cap_ok():
    """진행률 80% · 비중 20% → cap 정상 (가격 축과 무관)."""
    pv = price_bar_view(80.0)
    wv = weight_bar_view(20.0, 35.0)
    assert pv.fill_pct == 80.0
    assert pv.loss_pct is None
    assert wv.tone == "ok"
    assert wv.reduce_signal is False
    assert abs(wv.fill_pct - (20 / 35 * 100)) < 0.01

    row = _row(weight=20.0, progress=80.0)
    price_html = render_price_bar_html(row)
    weight_html = render_weight_bar_html(row)
    assert 'class="pf-bar-cap"' not in price_html  # 가격 바에 cap 마커 없음
    assert "80.0%" in price_html or "80%" in price_html
    assert "pf-fill-ok" in weight_html
    assert "감축" not in weight_html


def test_progress_10_weight_36_cap_over():
    """진행률 10% · 비중 36% → cap 초과 + 감축 신호 (가격 낮아도)."""
    pv = price_bar_view(10.0)
    wv = weight_bar_view(36.0, 35.0)
    assert pv.fill_pct == 10.0
    assert wv.tone == "danger"
    assert wv.reduce_signal is True
    assert wv.fill_pct == 100.0  # visual clamp at bar end

    row = _row(weight=36.0, progress=10.0)
    price_html = render_price_bar_html(row)
    weight_html = render_weight_bar_html(row)
    assert 'class="pf-bar-cap"' not in price_html
    assert "pf-fill-danger" in weight_html
    assert "감축" in weight_html
    # 가격 진행이 낮아도 비중 바가 danger
    assert "10.0%" in price_html or "10%" in price_html


def test_weight_30_is_warn_not_danger():
    assert classify_cap_tone(30.0, 35.0) == "warn"
    assert classify_cap_tone(29.9, 35.0) == "ok"
    assert classify_cap_tone(35.0, 35.0) == "danger"


def test_price_loss_clamps_fill_and_shows_negative_text():
    view = price_bar_view(-12.5)
    assert view.fill_pct == 0.0
    assert view.loss_pct == -12.5
    assert "-12.5%" in view.label

    row = _row(weight=10.0, progress=-12.5)
    html = render_price_bar_html(row)
    assert "손실" in html
    assert "-12.5%" in html


def test_quant_caption_on_screen_pending() -> None:
    row = _row(weight=10.0, progress=None, has_target=False)
    row.target_gap_kind = "screen_pending"
    row.extra = {
        "quant_ok": True,
        "quant_pbr_draft": 1.70,
        "quant_price_mid": 45000,
    }
    html = render_price_bar_html(row)
    assert "정량초안" in html
    assert "1.70" in html
    assert "45,000원" in html


def test_ladder_gauge_shows_floor_ceiling_rungs_and_fill() -> None:
    row = _row(weight=10.0, progress=50.0, has_target=True)
    row.current_price = 150.0
    row.target_price = 200.0
    row.extra = {
        "ladder_ok": True,
        "ladder_low": 100.0,
        "ladder_high": 200.0,
        "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
        "ladder_labels": ["매수1", "매수2", "줄이기", "절반", "전량"],
        "ladder_fill_pct": 50.0,
        "ladder_high_source": "approved",
    }
    html = render_price_bar_html(row)
    assert "하한" in html and "100원" in html
    assert "상한" in html and "200원" in html
    assert "현재" in html and "150원" in html
    assert "매수1" in html and "전량" in html
    assert "125원" in html
    assert "width:50.0%" in html
    assert "pf-bar-ladder" in html
    assert "pf-rung-now" in html
    assert 'class="pf-bar-cap"' not in html
    assert _rung_now_idx(150.0, [100.0, 125.0, 150.0, 175.0, 200.0]) == 2


def test_screen_pending_ladder_uses_quant_ceiling() -> None:
    row = _row(weight=10.0, progress=None, has_target=False)
    row.target_gap_kind = "screen_pending"
    row.current_price = 30000.0
    row.extra = {
        "ladder_ok": True,
        "ladder_low": 20000.0,
        "ladder_high": 45000.0,
        "ladder_rungs": [20000.0, 26250.0, 32500.0, 38750.0, 45000.0],
        "ladder_labels": ["매수1", "매수2", "줄이기", "절반", "전량"],
        "ladder_fill_pct": 40.0,
        "ladder_high_source": "quant_draft",
        "quant_ok": True,
        "quant_pbr_draft": 1.70,
        "quant_price_mid": 45000,
    }
    html = render_price_bar_html(row)
    assert "스크린" in html
    assert "상한(초안)" in html
    assert "45,000원" in html
    assert "하한" in html
    assert "20,000원" in html
    assert "width:40.0%" in html
    assert "pf-rung-now" in html
