"""③↔④ overlap chips on shared portfolio row header."""

from __future__ import annotations

from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.portfolio_widgets import (
    _cross_book_chips_html,
    _row_main_html,
)
from alpha_system.ui.services.ui_copy import load_ui_copy


def _row(ticker: str, *, book: str, eligible: bool = True) -> PortfolioRow:
    return PortfolioRow(
        ticker=ticker,
        name=f"N{ticker}",
        weight_pct=10.0,
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
        extra={"book": book, "proposal_eligible": eligible},
    )


def test_proposal_row_shows_held_chip() -> None:
    load_ui_copy.cache_clear()
    html = _cross_book_chips_html(
        _row("005930", book="proposal"),
        held={"005930"},
        proposed={"005930"},
        blocked=set(),
    )
    assert "pf-xchip-hold" in html
    assert "보유중" in html


def test_ops_row_shows_proposal_or_wait_chip() -> None:
    load_ui_copy.cache_clear()
    prop = _cross_book_chips_html(
        _row("005930", book="ops"),
        held={"005930"},
        proposed={"005930"},
        blocked=set(),
    )
    assert "pf-xchip-prop" in prop
    assert "제안중" in prop
    wait = _cross_book_chips_html(
        _row("000660", book="ops"),
        held={"000660"},
        proposed=set(),
        blocked={"000660"},
    )
    assert "대기중" in wait


def test_row_main_wires_cross_and_chart() -> None:
    load_ui_copy.cache_clear()
    html = _row_main_html(
        _row("005930", book="proposal"),
        held={"005930"},
        proposed={"005930"},
        blocked=set(),
    )
    assert "보유중" in html
    assert "pf-chart-hint" in html


def test_proposal_row_shows_phcvs_chip() -> None:
    load_ui_copy.cache_clear()
    html = _cross_book_chips_html(
        _row("092230", book="proposal"),
        held=set(),
        proposed={"092230"},
        blocked=set(),
        phcvs={"092230"},
    )
    assert "pf-xchip-phcvs" in html
    assert "PH추적" in html
