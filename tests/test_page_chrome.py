"""Shared page chrome — same head / section titles on every menu."""

from __future__ import annotations

import inspect
from pathlib import Path

from alpha_system.ui.pages import (
    approval,
    economy,
    journal,
    portfolio,
    settings,
)
from alpha_system.ui.services.approval_chrome import page_head, page_tabs
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


def test_every_menu_uses_page_head() -> None:
    for mod in (approval, portfolio, economy, journal, settings):
        src = inspect.getsource(mod)
        assert "page_head" in src, mod.__name__
        assert "st.subheader" not in src, mod.__name__
    assert "_render_alpha_ratio_bar" in inspect.getsource(portfolio)
    assert "render_screen_market_nav" in inspect.getsource(approval)
    assert "render_screen_market_nav" in inspect.getsource(portfolio)


def test_tabbed_menus_use_page_tabs() -> None:
    assert "page_tabs" in inspect.getsource(approval)
    assert "page_tabs" in inspect.getsource(settings)
    assert "_TAB_TOOLS" in inspect.getsource(settings)
    assert "st.segmented_control" not in inspect.getsource(approval)
    assert "st.segmented_control" not in inspect.getsource(settings)


def test_page_head_copy_keys() -> None:
    load_ui_copy.cache_clear()
    assert copy_get("approval", "page_kicker") == "확인"
    assert "숫자" in copy_get("approval", "page_title")
    assert copy_get("portfolio", "sec_watch").startswith("②")
    assert copy_get("portfolio", "rebal_note")
    assert copy_get("journal", "page_kicker") == "저널"
    assert copy_get("economy", "page_kicker") == "경제 시그널"
    assert "개별주" in copy_get("economy", "page_title")


def test_compact_layout_has_no_sidebar_toggle() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parents[1].joinpath("alpha_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "compact_mode" not in src
    assert "컴팩트 모드" not in src
    scores = Path(__file__).resolve().parents[1].joinpath(
        "alpha_system", "ui", "pages", "scores.py"
    ).read_text(encoding="utf-8")
    assert "is_mobile_browser" in scores
    dash = Path(__file__).resolve().parents[1].joinpath("alpha_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "home.render_home" not in dash
    assert "from alpha_system.ui.pages import home" not in dash


def test_product_display_name() -> None:
    from alpha_system.product import PRODUCT_NAME
    from alpha_system.ui.services.v2_chrome import render_primary_nav

    assert PRODUCT_NAME == "알파 스크리너"
    src = inspect.getsource(render_primary_nav)
    assert "PRODUCT_NAME" in src
    dash = Path(__file__).resolve().parents[1].joinpath("alpha_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "sync_market_from_ui" in dash
    assert "safe_page" in dash


def test_page_head_and_tabs_helpers_exist() -> None:
    assert callable(page_head)
    assert callable(page_tabs)


def test_desk_portal_is_launcher_only() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "desk" / "책상.html").read_text(encoding="utf-8")
    bat = (root / "desk" / "책상.bat").read_text(encoding="utf-8")
    spec = (root / "docs" / "DESK_PORTAL.md").read_text(encoding="utf-8")
    assert "127.0.0.1:8501" in html
    assert "127.0.0.1:8000" in html
    assert "run_ui_direct.bat" in bat
    assert "investment-fund-screener" in bat
    assert "pension.db" not in bat
    assert "import pension" not in bat.lower()
    assert "시스템은 섞지 않음" in spec
