from __future__ import annotations

import inspect

from alpha_system.ui.pages import portfolio
from alpha_system.ui.services.portfolio_widgets import _proposal_expand_html
from alpha_system.ui.services.context import PortfolioRow, ScoreboardRow
from alpha_system.ui.services.rank_watchboard import (
    TONE_BLOCKED,
    TONE_PROPOSAL,
    build_rank_watchboard,
    build_watch_table_rows,
)


def _board(*rows: tuple[str, str, float, bool]) -> list[ScoreboardRow]:
    out: list[ScoreboardRow] = []
    for ticker, name, score, eligible in rows:
        out.append(
            ScoreboardRow(
                ticker=ticker,
                name=name,
                total_score=score,
                score_q=score,
                score_v=score,
                score_sr=score,
                score_r=score,
                cecs=score,
                eligibility=eligible,
                sector_peer_fallback=False,
                is_held=False,
                status="final",
            )
        )
    return out


def test_proposal_page_keeps_final_and_blocked_apart() -> None:
    src = inspect.getsource(portfolio._render_proposal_book)
    assert "display_rows" not in src
    assert "pf_blocked" in src
    assert "proposal_final_heading" in src
    assert "proposal_blocked_heading" in src
    watch = inspect.getsource(portfolio._render_watch_pool)
    assert "proposal_tickers |=" not in watch
    assert "blocked_tickers=blocked_tickers" in watch


def test_watch_table_blocked_is_not_proposal_tone() -> None:
    board = build_rank_watchboard(
        _board(("000001", "A", 90.0, True), ("000002", "B", 88.0, False)),
        proposal_tickers={"000001"},
        max_rows=30,
    )
    table = build_watch_table_rows(
        board,
        cutoff=70.0,
        target_n=6,
        blocked_tickers={"000002"},
    )
    by_tk = {row.ticker: row.tone for row in table}
    assert by_tk["000001"] == TONE_PROPOSAL
    assert by_tk["000002"] == TONE_BLOCKED
    watch = inspect.getsource(portfolio._render_watch_pool)
    assert "_style_watch_df(frame)" in watch
    assert "watch_tone_label" in watch


def test_proposal_expand_skips_cecs_dump() -> None:
    row = PortfolioRow(
        ticker="000001",
        name="A",
        weight_pct=10.0,
        initial_weight_pct=10.0,
        avg_price=None,
        current_price=10000,
        target_price=12000,
        target_progress=None,
        remaining_upside_pct=20.0,
        has_target=True,
        target_detail="",
        target_gap_kind="none",
        cap_pct=35.0,
        cap_headroom_pct=25.0,
        cap_near=False,
        cap_over=False,
        price_progress_pct=80.0,
        total_score=90.0,
        extra={
            "book": "proposal",
            "proposal_eligible": True,
            "quant_ok": True,
            "quant_pbr_draft": 1.2,
            "quant_price_mid": 12000,
            "hakedaka_detail": "하케다카 2/2",
        },
    )
    html = _proposal_expand_html(row)
    assert "정성 채점" not in html
    assert "execution" not in html
    assert "혼합 목표가" in html
    assert "하케다카" in html
