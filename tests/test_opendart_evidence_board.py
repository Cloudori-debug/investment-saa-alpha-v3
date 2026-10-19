"""OpenDART evidence board HTML — readability / structure."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.dart_evidence import EvidenceEvent, TickerEvidence
from alpha_system.ui.services.opendart_evidence_board import (
    _amount_cell,
    _fmt_amount,
    opendart_evidence_html,
    opendart_join_html,
    opendart_toolbar_html,
)


def test_fmt_amount_eok() -> None:
    assert _fmt_amount(5_000_000_000, "") == "50억"
    assert _fmt_amount(None, "") == "—"
    assert _fmt_amount(None, "미확인") == "미확인"


def test_amount_cell_div_not_미확인() -> None:
    from alpha_system.ui.services.opendart_evidence_board import _amount_display

    ev = EvidenceEvent(
        kind="div",
        status="resolved",
        date="2026-03-01",
        title="현금배당결정",
        rcept_no="1",
        source_url="",
        amount_krw=None,
        amount_note="",
    )
    assert _amount_cell(ev) == "—"
    assert "미확인" not in _amount_cell(ev)
    dps = EvidenceEvent(
        kind="div",
        status="resolved",
        date="2026-03-01",
        title="현금배당결정",
        rcept_no="2",
        source_url="",
        amount_krw=1446,
        amount_note="document.xml(1주당배당금)",
    )
    assert _amount_display(dps) == "1주당 1,446원"


def test_evidence_html_is_table() -> None:
    board = [
        TickerEvidence(
            ticker="005930",
            data_status="ok",
            headline="자사주 취득 결의",
            events=[
                EvidenceEvent(
                    kind="buyback",
                    status="resolved",
                    date="2026-05-15",
                    title="자기주식취득결정",
                    rcept_no="1",
                    source_url="https://opendart.fss.or.kr/#rcpNo=1",
                    amount_krw=1_000_000_000,
                    amount_note="tsstkAqDecsn",
                )
            ],
        )
    ]
    html = opendart_evidence_html(board, names={"005930": "삼성전자"})
    assert "pf-od-table" in html
    assert "<thead>" in html
    assert "<th>종목</th>" in html
    assert "자사주" in html or "취득" in html
    assert "pf-od-card" not in html
    assert "10억" in html


def test_join_html_merges_score_and_evidence() -> None:
    proposal = [
        SimpleNamespace(ticker="005930", name="삼성전자", total_score=72.5, score_sr=80.0)
    ]
    scoreboard = proposal
    board = [
        TickerEvidence(
            ticker="005930",
            data_status="ok",
            headline="자사주 취득 결의",
            events=[
                EvidenceEvent(
                    kind="buyback",
                    status="resolved",
                    date="2026-05-15",
                    title="자기주식취득결정",
                    rcept_no="1",
                    source_url="",
                    amount_krw=2_000_000_000,
                    amount_note="tsstkAqDecsn",
                )
            ],
        )
    ]
    html = opendart_join_html(
        proposal_rows=proposal,
        blocked_rows=[],
        scoreboard_rows=scoreboard,
        board=board,
        flags=[],
        gated=set(),
        names={"005930": "삼성전자"},
    )
    assert "한눈" in html
    assert "72.5" in html
    assert "제안" in html
    assert "자사주" in html
    assert "20억" in html


def test_join_html_includes_phcvs_columns() -> None:
    from alpha_system.ui.services.phcvs_watch_board import PhcvsWatchRow

    proposal = [
        SimpleNamespace(ticker="005930", name="삼성전자", total_score=70.0, score_sr=60.0)
    ]
    phcvs = [
        PhcvsWatchRow(
            ticker="092230",
            name="KPX홀딩스",
            phcvs_status="조건부 승격",
            screener_status="정량풀 밖",
            reason="시총",
            action="추적",
            in_proposal=False,
            in_holdings=False,
            track_only=True,
            price_gate="FAIL",
            liquidity_gate="FAIL",
            cash_gate="PASS",
            cash_stale=True,
        )
    ]
    html = opendart_join_html(
        proposal_rows=proposal,
        blocked_rows=[],
        scoreboard_rows=proposal,
        board=[],
        flags=[],
        gated=set(),
        names={"005930": "삼성전자"},
        phcvs_rows=phcvs,
    )
    assert "KPX" in html or "092230" in html
    assert "리포트추적" in html or "심층·사유" in html


def test_join_html_div_amount_label() -> None:
    proposal = [SimpleNamespace(ticker="000660", name="SK하이닉스")]
    board = [
        TickerEvidence(
            ticker="000660",
            data_status="ok",
            headline="현금배당",
            events=[
                EvidenceEvent(
                    kind="div",
                    status="resolved",
                    date="2026-02-01",
                    title="현금·현물배당결정",
                    rcept_no="2",
                    source_url="",
                    amount_krw=None,
                    amount_note="",
                )
            ],
        )
    ]
    html = opendart_join_html(
        proposal_rows=proposal,
        blocked_rows=[],
        scoreboard_rows=[],
        board=board,
        flags=[],
        gated=set(),
        names={"000660": "SK하이닉스"},
    )
    assert "배당·원문대기" in html
    assert "미확인" not in html
    assert "미연동" not in html


def test_toolbar_stale_banner() -> None:
    html = opendart_toolbar_html(
        quota_line="DART 호출 0/8000",
        stale=True,
        as_of="2026-10-18",
        gate_mode_on=False,
    )
    assert "pf-od-attn-warn" in html
    assert "증분 갱신" in html
