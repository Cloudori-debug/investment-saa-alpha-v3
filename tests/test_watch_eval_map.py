"""② 후보 표용 판정·심층·공시 접목."""

from __future__ import annotations

from alpha_system.review.screen_deep_verify import CheckItem, ScreenVerifyRow
from alpha_system.ui.services.dart_evidence import EvidenceEvent, TickerEvidence
from alpha_system.ui.services.opendart_evidence_board import (
    build_watch_eval_map,
    eval_cells_for_ticker,
)


def test_eval_cells_pass_and_pub() -> None:
    sv = ScreenVerifyRow(
        ticker="005930",
        name="삼성전자",
        book="제안",
        overall="ok",
        headline="ok",
        verdict="pass_review",
        verdict_note="자동 심층 통과",
        checks=[CheckItem("hakedaka", "하케다카", "PASS")],
    )
    ev = TickerEvidence(
        ticker="005930",
        data_status="ok",
        headline="배당 공시",
        events=[
            EvidenceEvent(
                kind="div",
                status="completed",
                date="2026-01-01",
                title="현금배당결정",
                rcept_no="20260101000000",
                source_url="https://opendart.fss.or.kr/",
                amount_krw=150,
                amount_note="1주당",
            )
        ],
    )
    cells = eval_cells_for_ticker(
        screen_verify=sv,
        evidence=ev,
        gate_labels=["경영참여"],
        gated=True,
    )
    assert cells["판정"] == "통과"
    assert "자동 심층" in cells["심층"]
    assert "배당" in cells["공시"] or "1주당" in cells["공시"]
    assert "제안제외" in cells["공시"] or "경영참여" in cells["공시"]


def test_build_watch_eval_map_keys() -> None:
    sv = ScreenVerifyRow(
        ticker="000660",
        name="SK하이닉스",
        book="관찰",
        overall="warn",
        headline="warn",
        verdict="hold",
        verdict_note="하케다카 보류",
    )
    out = build_watch_eval_map(
        ["000660", "005930"],
        screen_verify_rows=[sv],
        board=[],
        flags=[],
        gated=set(),
    )
    assert out["000660"]["판정"] == "보류"
    assert out["005930"]["판정"] == "관찰"
    assert out["005930"]["심층"] == "—"
