"""Three-layer Review UI — QV / momentum / chart·flow (no Core score_m mix)."""

from __future__ import annotations

from pathlib import Path

from alpha_system.proposal_chart import ChartRead
from alpha_system.ui.services.chart_flow_merge import chart_flow_strip_html, unify_chart_and_flow
from alpha_system.ui.services.context import PortfolioRow, _review_display_mom_extra
from alpha_system.ui.services.portfolio_widgets import (
    _chart_flow_synth_html,
    _earn_mom_chip_html,
    _momentum_layer_html,
)
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


def _row(ticker: str = "000000", **extra_kw) -> PortfolioRow:
    extra = {"book": "proposal", **extra_kw}
    return PortfolioRow(
        ticker=ticker,
        name=f"N{ticker}",
        weight_pct=5.0,
        initial_weight_pct=None,
        avg_price=100.0,
        current_price=100.0,
        target_price=200.0,
        target_progress=50.0,
        remaining_upside_pct=None,
        has_target=True,
        target_detail="test",
        cap_pct=15.0,
        cap_headroom_pct=5.0,
        cap_near=False,
        extra=extra,
    )


def test_ui_copy_three_layers_and_buffer() -> None:
    load_ui_copy.cache_clear()
    mid = copy_get("portfolio", "screen_book_caption", default="")
    short = copy_get("portfolio", "screen_book_caption_short", default="")
    hold = copy_get("portfolio", "holdings_caption", default="")
    assert "중기=메인" in mid
    assert "운영" in mid or "보유" in mid
    assert "모멘텀" in mid or "언제" in mid
    assert "단기=테스트" in short or "단기=테스트" in hold
    assert "운영" in hold or "보유" in hold


def test_chart_flow_strip_has_now_kicker() -> None:
    cue = unify_chart_and_flow(
        chart=ChartRead(
            ticker="005930",
            name="삼성",
            ma_label="정배열",
            rsi_label="보통",
            bb_label="밴드 안",
            macd_label="골든크로스",
            macd_hist_label="",
            macd_div_label="",
            note="",
        ),
        flow_info={
            "flow_signal": "ACCUMULATION",
            "source": "test",
            "foreign_5d_mcap_pct": 0.1,
            "institution_5d_mcap_pct": 0.05,
        },
    )
    assert cue is not None
    html = chart_flow_strip_html(cue)
    assert "3 · 지금" in html
    assert "오늘 컨디션" in html
    assert "pf-review-3" in html
    assert "차트" in html and "수급" in html


def test_momentum_layer_prefix_and_missing() -> None:
    html = _momentum_layer_html(_row("000000"))
    assert "2 · 모멘텀" in html
    assert "중기 타이밍" in html
    assert "데이터 부족" in html
    assert "pf-review-2" in html

    rich = _row(
        "030000",
        score_m=55.0,
        return_6m=0.08,
        return_12m_ex_1m=0.12,
        net_income=120.0,
        net_income_y1=100.0,
    )
    html2 = _momentum_layer_html(rich)
    assert "2 · 모멘텀" in html2
    assert "흐름" in html2
    assert "score_m" not in html2
    assert "12-1" not in html2
    assert "최근 반년" in html2 or "최근 1년" in html2
    assert "실적 ·" in html2
    assert "상향" in html2


def test_earn_chip_omitted_without_fields() -> None:
    assert _earn_mom_chip_html({}) == ""
    assert "하향" in _earn_mom_chip_html({"net_income": 80.0, "net_income_y1": 100.0})


def test_synth_order_mom_then_now() -> None:
    row = _row("005930", score_m=40.0, return_6m=-0.05)
    html = _chart_flow_synth_html(row, chart=None, flow_data_dir=None)
    assert "2 · 모멘텀" in html
    assert "pf-review-stack" in html
    assert html.index("2 · 모멘텀") >= 0


def test_review_display_mom_extra_does_not_invent_core_weight() -> None:
    class _Sc:
        score_m = 42.0

    out = _review_display_mom_extra(
        {"book": "proposal"},
        sc=_Sc(),  # type: ignore[arg-type]
        price_row={"return_6m": 0.1, "return_12m_ex_1m": 0.2},
        fund_row={"net_income": 1, "net_income_y1": 2},
    )
    assert out["score_m"] == 42.0
    assert out["return_6m"] == 0.1
    assert out["return_12m_ex_1m"] == 0.2
    # Must not introduce a blended QVM+M total
    assert "qv_momentum_total" not in out
    assert "factor_score_total" not in out


def test_ui_copy_file_has_layer_phrases() -> None:
    text = Path("docs/UI_COPY.md").read_text(encoding="utf-8")
    assert "중기=메인" in text
    assert "운영" in text and ("보유" in text or "추가" in text)
    assert "단기=테스트" in text
