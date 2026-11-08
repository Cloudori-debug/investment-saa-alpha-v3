"""전략 비교 보드 · 내비 등록."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.nav import (
    PAGE_STRATEGY,
    NAV_STRATEGY_PAGES,
    PRIMARY_PAGES,
)
from alpha_system.ui.services.strategy_compare_board import (
    build_strategy_compare_board,
    card_detail_html,
    compare_overview_html,
    compare_table_rows,
    radio_options,
    strategy_gallery_html,
)


ROOT = Path(__file__).resolve().parents[1]


def test_nav_has_strategy_page() -> None:
    assert PAGE_STRATEGY == "전략비교"
    assert PAGE_STRATEGY in PRIMARY_PAGES
    assert PAGE_STRATEGY in NAV_STRATEGY_PAGES


def test_board_has_soft_and_static() -> None:
    board = build_strategy_compare_board(ROOT)
    ids = {c.id for c in board.cards}
    assert "mid_soft" in ids
    assert "short_momentum" in ids
    assert "sixty_forty" in ids
    assert "dual_momentum" in ids
    assert board.writes_target is False
    opts = radio_options(board)
    assert any("개별 퀀트" in lab for _, lab in opts)
    assert any("정적 배분" in lab for _, lab in opts)
    soft = next(c for c in board.cards if c.id == "mid_soft")
    assert soft.comparable is False
    assert soft.cagr is None
    html = card_detail_html(soft)
    assert "비교금지" in html
    assert "무엇인가" in html
    assert "하지 않음" in html
    rows = compare_table_rows(board)
    assert len(rows) == len(board.cards)
    soft_row = next(r for r in rows if "Soft" in r["전략"])
    assert "비교금지" in soft_row["성과"] or soft_row["KPI"] == "참고·비교금지"
    assert "CAGR" not in soft_row.get("성과", "")
    etf = next(r for r in rows if r["전략"] == "60/40")
    assert "성과" in etf
    # ETF comparable rows keep CAGR-style pair when lab ran
    sixty = next(c for c in board.cards if c.id == "sixty_forty")
    assert sixty.comparable is True


def test_dashboard_wires_strategy_page() -> None:
    dash = (ROOT / "alpha_dashboard.py").read_text(encoding="utf-8")
    assert "PAGE_STRATEGY" in dash
    assert "strategy_compare" in dash
    page = (
        ROOT / "alpha_system" / "ui" / "pages" / "strategy_compare.py"
    ).read_text(encoding="utf-8")
    assert "render_strategy_compare" in page
    assert "strategy_gallery_html" in page
    assert "compare_overview_html" in page
    assert "st.radio" not in page
    assert "st.tabs" not in page


def test_gallery_shows_all_cards_without_mode_switch() -> None:
    board = build_strategy_compare_board(ROOT)
    overview = compare_overview_html(board)
    assert "한눈 비교표" in overview
    assert "비교금지" in overview or "pf-sc-row-ref" in overview
    gallery = strategy_gallery_html(board)
    assert "개별 퀀트" in gallery
    assert "모멘텀 퀀트" in gallery
    assert "정적 배분" in gallery
    assert "mid_soft" in gallery
    assert "sixty_forty" in gallery or "60/40" in gallery
    assert "하지 않음" in gallery
    assert "radio" not in gallery.lower()
