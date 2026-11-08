"""Economy playbook — stance cards; ratio lives on hero."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.economy_signal import envelope_policy, policy_target_line
from alpha_system.ui.services.economy_playbook import (
    holdings_proposal_gap,
    stage_playbook,
)


def test_envelope_policy_stage3() -> None:
    pol = envelope_policy(3)
    assert pol.stage == 3
    assert pol.equity_share == 0.60
    assert pol.cash_share == 0.40
    assert "36–56%" in pol.ratio_band
    line = policy_target_line(3)
    assert "정책 목표" in line
    assert "60%" in line
    assert "40%" in line


def test_stage_playbook_stance_only_no_ratio_card() -> None:
    book = stage_playbook(3)
    assert book.tone == "wait"
    assert book.equity_pct == 60.0
    assert book.cash_pct == 40.0
    assert book.cards
    labels = [c.label for c in book.cards]
    assert "정책 목표" not in labels
    assert "중기" in labels
    blob = " ".join(book.bullets)
    # Stance text, not a second copy of 60/40 policy paragraph
    assert "개별주 60%" not in blob
    assert "맞출지" not in blob


def test_stage_playbook_defensive() -> None:
    assert stage_playbook(4).tone == "bad"
    assert stage_playbook(4).equity_pct == 40.0
    assert stage_playbook(4).cards[0].label == "중기"
    assert stage_playbook(5).tone == "bad"
    assert stage_playbook(None).tone == "off"
    assert "다시 계산" in [c.label for c in stage_playbook(None).cards]


def test_holdings_proposal_gap_lists() -> None:
    held = [
        SimpleNamespace(ticker="030200", name="KT"),
        SimpleNamespace(ticker="000660", name="SK하이닉스"),
    ]
    prop = [
        SimpleNamespace(ticker="000660", name="SK하이닉스"),
        SimpleNamespace(ticker="005930", name="삼성전자"),
    ]
    gap = holdings_proposal_gap(held, prop)
    assert [x.ticker for x in gap.held_not_proposed] == ["030200"]
    assert [x.ticker for x in gap.proposed_not_held] == ["005930"]
    assert [x.ticker for x in gap.overlap] == ["000660"]
    assert gap.has_gaps
    assert not gap.no_books


def test_holdings_proposal_gap_empty_books() -> None:
    gap = holdings_proposal_gap([], [])
    assert gap.no_books
    assert not gap.has_gaps


def test_economy_page_wires_playbook_and_gap() -> None:
    from pathlib import Path

    page = Path(__file__).resolve().parents[1].joinpath(
        "alpha_system", "ui", "pages", "economy.py"
    ).read_text(encoding="utf-8")
    # playbook·gap은 함수명 헬퍼 없이 탭 본문에 직접 배선
    assert "stage_playbook" in page
    assert "holdings_proposal_gap" in page
    assert "asset_move_board_html" in page or "alpha_ops_bridge_html" in page
    assert "total_score" not in page
