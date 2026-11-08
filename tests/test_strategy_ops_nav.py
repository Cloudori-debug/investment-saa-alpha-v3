"""전략별 탭 · 직접운영 라우팅 · 정적 묶음."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.nav import (
    NAV_STRATEGY_PAGES,
    PAGE_STRATEGY,
    PRIMARY_PAGES,
    STRATEGY_OP_PAGES,
)
from alpha_system.ui.services.strategy_ops_catalog import (
    LEGACY_STATIC_IDS,
    STRATEGY_OP_SPECS,
    strategy_id_from_page,
    strategy_page_key,
)


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_op_pages_bundled() -> None:
    ids = [s.strategy_id for s in STRATEGY_OP_SPECS]
    assert ids == [
        "mid_soft",
        "short_momentum",
        "static_book",
        "dual_momentum",
    ]
    assert len(STRATEGY_OP_PAGES) == 4
    assert strategy_page_key("static_book") in PRIMARY_PAGES
    assert strategy_page_key("mid_soft") in PRIMARY_PAGES
    assert strategy_page_key("sixty_forty") not in PRIMARY_PAGES
    assert PAGE_STRATEGY in PRIMARY_PAGES
    assert PAGE_STRATEGY in NAV_STRATEGY_PAGES
    assert strategy_id_from_page("전략·dual_momentum") == "dual_momentum"
    assert strategy_id_from_page("전략·sixty_forty") == "static_book"
    assert strategy_id_from_page("전략·golden_butterfly") == "static_book"
    assert set(LEGACY_STATIC_IDS) >= {
        "sixty_forty",
        "all_seasons",
        "permanent",
        "golden_butterfly",
        "k_all_weather",
    }
    assert strategy_id_from_page("전략비교") is None


def test_dashboard_wires_strategy_ops() -> None:
    dash = (ROOT / "alpha_dashboard.py").read_text(encoding="utf-8")
    assert "STRATEGY_OP_PAGES" in dash
    assert "strategy_ops" in dash
    page = (
        ROOT / "alpha_system" / "ui" / "pages" / "strategy_ops.py"
    ).read_text(encoding="utf-8")
    assert "render_strategy_ops" in page
    assert "static_book" in page
    assert "dual_momentum" in page or "듀얼" in page
    assert "Review-only" in page or "target" in page
    chrome = (
        ROOT / "alpha_system" / "ui" / "services" / "v2_chrome.py"
    ).read_text(encoding="utf-8")
    assert "전략 운용" in chrome
    assert "NAV_STRATEGY_PAGES" in chrome
