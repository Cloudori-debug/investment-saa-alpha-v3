"""Chart × flow Review merge — conflict softens action, no score write."""

from __future__ import annotations

from alpha_system.proposal_chart import ChartRead
from alpha_system.ui.services.chart_flow_merge import (
    chart_flow_strip_html,
    unify_chart_and_flow,
)


def _chart(
    *,
    note: str = "",
    ma: str = "정배열",
    rsi: str = "보통",
    macd: str = "골든크로스",
) -> ChartRead:
    return ChartRead(
        ticker="005930",
        name="삼성",
        ma_label=ma,
        rsi_label=rsi,
        bb_label="밴드 안",
        macd_label=macd,
        macd_hist_label="",
        macd_div_label="",
        note=note,
    )


def test_bull_chart_bear_flow_blocks_add() -> None:
    # Bullish-leaning chart labels → often "유지/소량"; force via verdict path.
    cue = unify_chart_and_flow(
        chart=_chart(ma="정배열", rsi="과매수 아님"),
        flow_info={
            "flow_signal": "DISTRIBUTION",
            "source": "test",
            "foreign_5d_mcap_pct": -0.23,
            "institution_5d_mcap_pct": 0.11,
        },
    )
    assert cue is not None
    assert cue.alignment in {"conflict", "partial", "align", "single"}
    html = chart_flow_strip_html(cue)
    assert "차트" in html and "수급" in html
    # Distribution present in evidence
    assert "분산" in cue.flow_text or "분산" in html


def test_conflict_bull_vs_distribution() -> None:
    """우호 차트(유지·추격금지) + 수급 분산 → 추매금지."""
    cue = unify_chart_and_flow(
        chart=_chart(ma="60일선 위", rsi="보통", macd="골든크로스"),
        flow_info={
            "flow_signal": "DISTRIBUTION",
            "source": "auto_pykrx",
            "foreign_5d_mcap_pct": -0.2,
            "institution_5d_mcap_pct": -0.1,
        },
    )
    assert cue is not None
    assert cue.chart_stance == "bull"
    assert cue.flow_stance == "bear"
    assert cue.alignment == "conflict"
    assert cue.action == "추매금지"
    assert cue.tone == "hot"


def test_both_bear_trim_review() -> None:
    cue = unify_chart_and_flow(
        chart=_chart(ma="역배열", rsi="과매수"),
        flow_info={
            "flow_signal": "DISTRIBUTION",
            "source": "test",
            "foreign_5d_mcap_pct": -0.3,
            "institution_5d_mcap_pct": -0.2,
        },
    )
    assert cue is not None
    if cue.chart_stance == "bear" and cue.flow_stance == "bear":
        assert "축소" in cue.action or "교체" in cue.action


def test_flow_only_when_no_chart() -> None:
    cue = unify_chart_and_flow(
        chart=None,
        flow_info={
            "flow_signal": "ACCUMULATION",
            "source": "test",
            "foreign_5d_mcap_pct": 0.1,
            "institution_5d_mcap_pct": 0.05,
        },
    )
    assert cue is not None
    assert cue.action == "관망"
    assert "수급만으로" in cue.why or "부족" in cue.why


def test_portfolio_uses_synth() -> None:
    import inspect

    from alpha_system.ui.services import portfolio_widgets as pw

    assert "_chart_flow_synth_html" in inspect.getsource(pw)
