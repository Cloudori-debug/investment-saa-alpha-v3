"""Ops badge + chart readout → one Review action."""

from __future__ import annotations

from alpha_system.proposal_chart import ChartRead
from alpha_system.ui.services.trade_cue_merge import unify_ops_and_chart


def test_hold_plus_no_buy_chart() -> None:
    chart = ChartRead(
        ticker="005930",
        name="삼성전자",
        ma_label="60일선 위",
        rsi_label="과열",
        bb_label="상단 밖",
        macd_label="시그널 위",
        macd_hist_label="히스토그램 확대",
    )
    cue = unify_ops_and_chart(ops_kind="hold", ops_label="유지", chart=chart)
    assert "추가금지" in cue.action or "금지" in cue.action
    assert cue.headline == "보유 · 더 사지 않음"
    assert "장부" in cue.why
    assert cue.evidence_ops == "유지"
    assert len(cue.chips) >= 3


def test_trim_beats_bullish_chart() -> None:
    chart = ChartRead(
        ticker="005930",
        name="삼성전자",
        ma_label="60일선 위",
        rsi_label="보통",
        bb_label="밴드 안",
        macd_label="골든크로스",
        macd_hist_label="히스토그램 확대",
    )
    cue = unify_ops_and_chart(ops_kind="trim", ops_label="줄이기", chart=chart)
    assert cue.action == "비중 줄이기"
    assert "줄이기" in cue.why or "축소" in cue.why
    assert cue.evidence_ops == "줄이기"


def test_exit_full_wins() -> None:
    cue = unify_ops_and_chart(
        ops_kind="exit_full",
        ops_label="교체",
        chart=ChartRead(
            ticker="000001",
            name="A",
            ma_label="60일선 위",
            rsi_label="보통",
            bb_label="밴드 안",
            macd_label="시그널 위",
            macd_hist_label="히스토그램 확대",
        ),
    )
    assert "교체" in cue.action
    assert cue.tone == "danger"


def test_no_chart_keeps_ops_label() -> None:
    cue = unify_ops_and_chart(ops_kind="hold", ops_label="유지", chart=None)
    assert cue.action == "유지"
    assert "일봉" in cue.why
    assert cue.headline == "보유 유지"
