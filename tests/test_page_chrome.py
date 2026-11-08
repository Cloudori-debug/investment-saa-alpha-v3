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
    src_pf = inspect.getsource(portfolio)
    # 단기채 Review UI는 경제 나침반 playbook에만 (④ 장부방어 카드 없음)
    assert "_render_alpha_ratio_bar" not in src_pf
    assert "_cash_defense_row_html" not in src_pf
    assert "pf-cash-defense" not in src_pf
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
    assert "정량" in copy_get("approval", "page_title")
    assert "후보" in copy_get("portfolio", "sec_watch")
    assert copy_get("portfolio", "sec_phcvs") == "정밀 Review"
    assert "Soft" in copy_get("portfolio", "phcvs_caption")
    assert copy_get("portfolio", "rebal_note")
    assert copy_get("journal", "page_kicker") == "저널"
    assert copy_get("economy", "page_kicker") == "경제 나침반"
    assert "태도" in copy_get("economy", "page_title")
    assert "자세" in copy_get("economy", "sec_playbook")
    # page_title may be EN branding; Soft/today trade still in copy surface
    pf_title = copy_get("portfolio", "page_title")
    assert pf_title
    assert (
        "오늘 매매" in pf_title
        or "Trade today" in pf_title
        or "Soft" in pf_title
        or "satellite" in pf_title.lower()
    )
    assert copy_get("portfolio", "theme_fusion_caption")
    assert copy_get("portfolio", "sec_alpha_sources")
    tab_u = copy_get("portfolio", "tab_universe")
    assert "유니버스" in tab_u or "Universe" in tab_u
    assert copy_get("portfolio", "household_satellite_caption")
    assert "모멘텀" in copy_get("portfolio", "sleeve_short_fold")
    pf_lead = copy_get("portfolio", "page_lead")
    assert (
        "본체" in pf_lead
        or "위성" in pf_lead
        or "Soft" in pf_lead
        or "Core" in pf_lead
    )
    assert copy_get("portfolio", "alpha_sources_lead")
    assert copy_get("portfolio", "gieop_btn_pipe")
    assert copy_get("portfolio", "gieop_btn_open")
    assert "오늘 해부" in copy_get("portfolio", "sec_gieop")
    assert copy_get("portfolio", "causal_exec")
    assert copy_get("portfolio", "diag_fold")


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


def test_nav_button_keys_unique_for_primary_pages() -> None:
    from alpha_system.ui.services.nav import PRIMARY_PAGES
    from alpha_system.ui.services.v2_chrome import render_primary_nav

    src = inspect.getsource(render_primary_nav)
    assert "저평가독점" not in src
    assert "방어배당" not in src
    assert 'f"p_{abs(hash(page))' in src or "hash(page)" in src
    # mapped pages must not collide on fallback "page"
    assert '"page"' not in src or "_btn_ids.get(page) or" in src
    assert len(PRIMARY_PAGES) == len(set(PRIMARY_PAGES))
    dash = Path(__file__).resolve().parents[1].joinpath("alpha_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "monopoly_value" not in dash
    assert "defense_dividend" not in dash


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
