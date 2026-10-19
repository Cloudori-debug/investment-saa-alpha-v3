"""제안·보유 요약 표 행 HTML."""

from __future__ import annotations

from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.portfolio_widgets import (
    _book_reason_plain,
    _portfolio_book_head_html,
    _portfolio_book_row_html,
)
from alpha_system.ui.services.ui_copy import load_ui_copy


def _row(
    ticker: str,
    *,
    book: str = "proposal",
    eligible: bool = True,
    score: float | None = 72.5,
    weight: float = 8.0,
    has_target: bool = True,
) -> PortfolioRow:
    return PortfolioRow(
        ticker=ticker,
        name=f"N{ticker}",
        weight_pct=weight,
        initial_weight_pct=None,
        avg_price=100.0,
        current_price=120_000.0,
        target_price=150_000.0 if has_target else None,
        target_progress=50.0 if has_target else None,
        remaining_upside_pct=25.0 if has_target else None,
        has_target=has_target,
        target_detail="test",
        cap_pct=15.0,
        cap_headroom_pct=5.0,
        cap_near=False,
        total_score=score,
        ops_signal="hold",
        ops_signal_label="유지",
        ops_signal_detail="목표가까지 +25%",
        extra={"book": book, "proposal_eligible": eligible},
    )


def test_book_head_has_summary_columns() -> None:
    html = _portfolio_book_head_html()
    assert "배지" in html
    assert "종목" in html
    assert "점수" in html
    assert "비중" in html
    assert "사유" in html


def test_book_row_cue_front_and_numbers() -> None:
    load_ui_copy.cache_clear()
    html = _portfolio_book_row_html(
        _row("005930"),
        held={"005930"},
        proposed={"005930"},
        blocked=set(),
        open_row=True,
    )
    assert "pf-book-tr-open" in html
    assert "pf-book-c-cue" in html
    assert "pf-book-cue" in html
    assert "유지" in html
    assert "72.50" in html
    assert "8.0%" in html
    assert "120,000" in html
    assert "150,000" in html
    assert "보유중" in html
    assert "pf-chart-hint" in html
    # Badge is not duplicated inside the name cell.
    name_chunk = html.split('pf-book-c-name')[1].split("pf-book-c-score")[0]
    assert "pf-book-cue" not in name_chunk


def test_blocked_row_quiet_dashes() -> None:
    load_ui_copy.cache_clear()
    row = _row("000660", eligible=False, has_target=False)
    row.extra["ineligible_reason"] = "노른자 대기"
    html = _portfolio_book_row_html(row, held=set(), proposed=set(), blocked={"000660"})
    assert "pf-book-tr-blocked" in html
    assert "부적격" in html
    assert "노른자 대기" in _book_reason_plain(row) or "부적격" in html
    assert html.count("—") >= 2
