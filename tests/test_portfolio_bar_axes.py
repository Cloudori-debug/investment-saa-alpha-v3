"""Regression: price bar vs weight/cap bar stay on separate axes."""

from __future__ import annotations

from alpha_system.ui.services.portfolio_metrics import (
    classify_cap_tone,
    price_bar_view,
    weight_bar_view,
)
from alpha_system.ui.services.portfolio_widgets import render_price_bar_html, render_weight_bar_html
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
