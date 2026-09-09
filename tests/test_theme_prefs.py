from __future__ import annotations

from pathlib import Path

from alpha_system.ui.theme_prefs import (
    DEFAULT_THEME,
    THEME_DARK,
    THEME_LIGHT,
    apply_color_tokens,
    css_variables,
    load_ui_theme,
    normalize_theme,
    save_ui_theme,
    watch_row_styles,
)


def test_default_theme_is_dark() -> None:
    assert DEFAULT_THEME == THEME_DARK
    assert normalize_theme("") == THEME_DARK
    assert normalize_theme("light") == THEME_LIGHT
    assert normalize_theme("일반") == THEME_LIGHT


def test_theme_persists_under_data_local(tmp_path: Path) -> None:
    assert load_ui_theme(tmp_path) == THEME_DARK
    path = save_ui_theme(tmp_path, THEME_LIGHT)
    assert path == tmp_path / "data" / "local" / "ui_prefs.json"
    assert load_ui_theme(tmp_path) == THEME_LIGHT
    save_ui_theme(tmp_path, "다크")
    assert load_ui_theme(tmp_path) == THEME_DARK


def test_color_tokens_leave_css_variables() -> None:
    raw = "background: #f3efe6; color: #1c1a16; border: 1px solid #dcd4c6;"
    out = apply_color_tokens(raw)
    assert "#f3efe6" not in out
    assert "var(--saa-bg)" in out
    assert "var(--saa-fg)" in out
    vars_css = css_variables(THEME_DARK)
    assert "color-scheme: dark" in vars_css
    assert "--saa-bg: #141210" in vars_css
    light = css_variables(THEME_LIGHT)
    assert "color-scheme: light" in light
    assert "--saa-bg: #f3efe6" in light


def test_watch_row_styles_follow_theme() -> None:
    dark = watch_row_styles(THEME_DARK)
    light = watch_row_styles(THEME_LIGHT)
    assert "제안" in dark and "적격" in dark and "관찰" in dark
    assert "제외" in dark
    assert dark["최종 제안"] == dark["제안"]
    assert dark["컷 통과"] == dark["적격"]
    assert dark["편입 제외"] == dark["제외"]
    assert "#d1fae5" in light["제안"]
    assert "#24352c" in dark["제안"]
    assert "color:" in dark["관찰"]


def test_selected_tab_text_contrasts_fill() -> None:
    from alpha_system.ui.styles import _WIDGET_OVERRIDES

    css = _WIDGET_OVERRIDES
    assert 'button[kind="segmented_controlActive"]' in css
    assert "color: var(--saa-on-accent) !important" in css
    assert "color: inherit !important" in css
    assert (
        'div[data-testid="stButton"] [data-testid="stMarkdownContainer"] p'
        in css
    )
