from __future__ import annotations

import inspect
from pathlib import Path

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
    assert "st.data_editor" in watch
    assert "_style_watch_df(frame)" in watch
    assert '"보유"' in watch
    assert "CheckboxColumn" in watch
    assert '"판정"' in watch
    assert '"심층"' in watch
    assert '"공시"' in watch
    assert "_watch_eval_enrichment" in watch
    assert "pf-watch-scroll" in watch
    assert "column_order" in watch
    assert "watch_tone_label" in watch
    page = inspect.getsource(portfolio.render_portfolio)
    assert "_render_today_book(mid_ctx, short_ctx)" in page
    assert "_render_book_editor(mid_ctx)" in page
    today = inspect.getsource(portfolio._render_today_book)
    assert "_render_today_book_copy(rows)" in today
    prop = inspect.getsource(portfolio._render_proposal_book)
    assert "screen_book_caption" in prop


def test_today_book_copy_tsv_and_csv() -> None:
    rows = [
        {
            "우선": 1,
            "할 일": "사기",
            "구분": "중기 Soft",
            "종목": "가",
            "코드": "000001",
            "보유": "",
            "제안": "Y",
            "비중": 12.5,
            "현재가": None,
            "신호": "신규",
            "사람": "사기 1순위",
        }
    ]
    tsv = portfolio._desk_rows_tsv(rows)
    assert tsv.startswith("우선\t할 일\t구분\t종목\t코드")
    assert "사기\t중기 Soft\t가\t000001" in tsv
    assert "사기 1순위" in tsv
    raw = portfolio._desk_rows_csv_bytes(rows)
    text = raw.decode("utf-8-sig")
    assert "우선,할 일,구분,종목,코드" in text
    assert "000001" in text


def test_hold_editor_uses_the_scored_candidates() -> None:
    class Row:
        def __init__(self, ticker: str, name: str, total_score: float) -> None:
            self.ticker = ticker
            self.name = name
            self.total_score = total_score

    class Ctx:
        scoreboard_rows = [
            Row("000002", "비", 10.0),
            Row("000001", "가", 90.0),
        ]
        data_dir = Path("missing-positions")

    rows = portfolio._candidate_edit_order(Ctx())
    assert [tk for tk, _name, _score in rows] == ["000001", "000002"]
    Ctx.root = Path("missing-positions")
    Ctx.portfolio_rows = []
    recs = portfolio._candidate_edit_records(Ctx(), {})
    assert recs[0]["종목"] == "가"
    assert "품질" in recs[0] and "PER" in recs[0] and "여유%" in recs[0]
    assert recs[0]["일봉"] is None
    assert "fchart.naver" in str(recs[0]["차트"])
    sparked = portfolio._candidate_edit_records(
        Ctx(),
        {},
        {"000001": [("2026-01-01", 10.0), ("2026-01-02", 12.0), ("2026-01-03", 11.0)]},
    )
    assert sparked[0]["일봉"] == [10.0, 12.0, 11.0]
    assert sparked[1]["일봉"] is None
    extended = portfolio._extend_closes_with_snapshot(
        {"000001": [("2026-11-04", 62700.0)]},
        {"000001": "2026-11-13"},
        {"000001": 59000.0, "000009": 1000.0},
    )
    assert extended["000001"][-1] == ("2026-11-13", 59000.0)
    assert "000009" not in extended
    assert len(rows) > 1


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
    assert "pf-metric-grid" in html
    assert "혼합목표" in html or "혼합 목표" in html
    assert "하케다카" in html
    assert "10.0%" in html
    deduped = _proposal_expand_html(row, summary_in_table=True)
    assert "비중" not in deduped
    assert "10.0%" not in deduped
    assert "하케다카" in deduped
    assert "여유" in deduped
    prop = inspect.getsource(portfolio._render_proposal_book)
    assert "always_open=True" in prop
    from alpha_system.ui.services import portfolio_widgets as pw

    bullets = inspect.getsource(pw.render_portfolio_bullets)
    assert "always_open" in bullets
    assert "show_header=False" in bullets
    assert "summary_in_table=True" in bullets
    assert "pf-book-detail-open" in bullets
    lean = pw._row_main_html(row, detail=True, show_header=False)
    assert "pf-bullet-top" not in lean
    assert "제안 10.0%" not in lean
