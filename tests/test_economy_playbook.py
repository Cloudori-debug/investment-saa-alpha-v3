"""Economy playbook + holdings↔proposal gap — Review-only."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.economy_playbook import (
    holdings_proposal_gap,
    stage_playbook,
)


def test_stage_playbook_neutral_mentions_short_bond() -> None:
    book = stage_playbook(3)
    assert book.tone == "wait"
    assert book.equity_pct == 60.0
    assert book.cash_pct == 40.0
    assert "40%" in book.equity_cash
    assert book.cards
    assert book.cards[0].label
    blob = " ".join(book.bullets)
    assert "단기채" in blob
    assert "target" in blob.lower() or "target" in blob


def test_stage_playbook_defensive() -> None:
    assert stage_playbook(4).tone == "bad"
    assert "60%" in stage_playbook(4).equity_cash
    assert stage_playbook(5).tone == "bad"
    assert stage_playbook(None).tone == "off"


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
    assert "_render_playbook" in page
    assert "_render_forest_checklist" in page
    assert "_render_holdings_gap" in page
    assert "stage_playbook" in page
    assert "stage_forest_checklist" in page
    assert "holdings_proposal_gap" in page
    assert "점수" not in page