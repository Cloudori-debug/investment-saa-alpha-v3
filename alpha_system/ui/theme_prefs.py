"""Operator UI theme (dark default). Stored in data/local — not Git."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

THEME_DARK = "dark"
THEME_LIGHT = "light"
DEFAULT_THEME = THEME_DARK
THEMES = (THEME_DARK, THEME_LIGHT)
PREFS_REL = Path("data") / "local" / "ui_prefs.json"

THEME_LABELS = {
    THEME_DARK: "다크",
    THEME_LIGHT: "일반",
}

# Light values match the current cream shell. Dark is a warm charcoal pair.
_PALETTES: dict[str, dict[str, str]] = {
    THEME_LIGHT: {
        "bg": "#f3efe6",
        "surface": "#faf7f1",
        "card": "#ffffff",
        "fg": "#1c1a16",
        "muted": "#6f6a60",
        "subtle": "#64748b",
        "accent": "#2d4a3c",
        "on-accent": "#faf7f1",
        "border": "#dcd4c6",
        "border-strong": "#d1d5db",
        "hairline": "#e2e8f0",
        "ink": "#1e293b",
        "ink-strong": "#0f172a",
        "muted-bg": "#f8fafc",
        "danger": "#ef4444",
        "danger-strong": "#dc2626",
        "danger-bg": "#fef2f2",
        "danger-fg": "#991b1b",
        "danger-chip": "#fee2e2",
        "warn": "#d97706",
        "warn-bg": "#fffbeb",
        "warn-chip": "#fef3c7",
        "warn-fg": "#92400e",
        "warn-text": "#78350f",
        "warn-strong": "#b45309",
        "warn-border": "#f0d9a8",
        "slate": "#94a3b8",
        "slate-fg": "#475569",
        "slate-ink": "#334155",
        "ok-bg": "#e4ebe4",
        "ok-border": "#9bb5a6",
        "chart": "#1e3a5f",
        "chart-bg": "#eef3f8",
        "chart-border": "#8fa0b3",
        "list-border": "#cbd5e1",
        "table-line": "#e5e7eb",
        "input-bg": "#ffffff",
        "proposal-row": "#d1fae5",
        "eligible-row": "#fef3c7",
        "watch-row": "#ffffff",
    },
    THEME_DARK: {
        "bg": "#141210",
        "surface": "#1c1914",
        "card": "#241f19",
        "fg": "#f3efe6",
        "muted": "#b8b0a3",
        "subtle": "#9a9286",
        "accent": "#8fb89a",
        "on-accent": "#121410",
        "border": "#3a342c",
        "border-strong": "#4a4338",
        "hairline": "#2e2a24",
        "ink": "#ece8df",
        "ink-strong": "#f7f3ea",
        "muted-bg": "#1a1e24",
        "danger": "#f07171",
        "danger-strong": "#ef5350",
        "danger-bg": "#3a1c1c",
        "danger-fg": "#f5b5b5",
        "danger-chip": "#4a2222",
        "warn": "#e8a54b",
        "warn-bg": "#3a2e18",
        "warn-chip": "#43351c",
        "warn-fg": "#f0c98a",
        "warn-text": "#f0c98a",
        "warn-strong": "#e8a54b",
        "warn-border": "#6b5428",
        "slate": "#8b93a1",
        "slate-fg": "#c5cad3",
        "slate-ink": "#d5dae3",
        "ok-bg": "#24352c",
        "ok-border": "#4a6b58",
        "chart": "#7eb0d4",
        "chart-bg": "#1a2838",
        "chart-border": "#4a6a82",
        "list-border": "#3a342c",
        "table-line": "#2e2a24",
        "input-bg": "#1c1914",
        "proposal-row": "#24352c",
        "eligible-row": "#3a2e18",
        "watch-row": "#241f19",
    },
}

# Longest hex first so #fff does not eat #ffffff / #fffbeb.
_HEX_TO_VAR: tuple[tuple[str, str], ...] = (
    ("rgba(255, 255, 255, 0.95)", "var(--saa-card)"),
    ("rgba(255,255,255,0.94)", "var(--saa-card)"),
    ("rgba(255,255,255,0.92)", "var(--saa-card)"),
    ("#ffffff", "var(--saa-card)"),
    ("#fffbeb", "var(--saa-warn-bg)"),
    ("#fef3c7", "var(--saa-warn-chip)"),
    ("#fef2f2", "var(--saa-danger-bg)"),
    ("#f8fafc", "var(--saa-muted-bg)"),
    ("#f3efe6", "var(--saa-bg)"),
    ("#faf7f1", "var(--saa-surface)"),
    ("#dcd4c6", "var(--saa-border)"),
    ("#1c1a16", "var(--saa-fg)"),
    ("#6f6a60", "var(--saa-muted)"),
    ("#2d4a3c", "var(--saa-accent)"),
    ("#64748b", "var(--saa-subtle)"),
    ("#d1d5db", "var(--saa-border-strong)"),
    ("#1e293b", "var(--saa-ink)"),
    ("#0f172a", "var(--saa-ink-strong)"),
    ("#d97706", "var(--saa-warn)"),
    ("#94a3b8", "var(--saa-slate)"),
    ("#475569", "var(--saa-slate-fg)"),
    ("#ef4444", "var(--saa-danger)"),
    ("#991b1b", "var(--saa-danger-fg)"),
    ("#e2e8f0", "var(--saa-hairline)"),
    ("#f0d9a8", "var(--saa-warn-border)"),
    ("#b45309", "var(--saa-warn-strong)"),
    ("#78350f", "var(--saa-warn-text)"),
    ("#dc2626", "var(--saa-danger-strong)"),
    ("#92400e", "var(--saa-warn-fg)"),
    ("#fee2e2", "var(--saa-danger-chip)"),
    ("#e4ebe4", "var(--saa-ok-bg)"),
    ("#cbd5e1", "var(--saa-list-border)"),
    ("#8fa0b3", "var(--saa-chart-border)"),
    ("#eef3f8", "var(--saa-chart-bg)"),
    ("#1e3a5f", "var(--saa-chart)"),
    ("#e5e7eb", "var(--saa-table-line)"),
    ("#9bb5a6", "var(--saa-ok-border)"),
    ("#334155", "var(--saa-slate-ink)"),
    ("#fff", "var(--saa-card)"),
)


def normalize_theme(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"light", "일반", "라이트", "bright"}:
        return THEME_LIGHT
    if raw in THEMES:
        return raw
    return DEFAULT_THEME


def palette(theme: object) -> dict[str, str]:
    return dict(_PALETTES[normalize_theme(theme)])


def css_variables(theme: object) -> str:
    name = normalize_theme(theme)
    colors = _PALETTES[name]
    scheme = "dark" if name == THEME_DARK else "light"
    lines = [f"  --saa-{key}: {val};" for key, val in colors.items()]
    return (
        f":root {{\n  color-scheme: {scheme};\n" + "\n".join(lines) + "\n}\n"
        f"html, body, .stApp {{ color-scheme: {scheme}; }}\n"
    )


def apply_color_tokens(css: str) -> str:
    out = css
    for src, dest in _HEX_TO_VAR:
        out = out.replace(src, dest)
    return out


def prefs_path(root: Path) -> Path:
    return Path(root) / PREFS_REL


def load_ui_theme(root: Path | None) -> str:
    if root is None:
        return DEFAULT_THEME
    path = prefs_path(Path(root))
    if not path.is_file():
        return DEFAULT_THEME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_THEME
    if not isinstance(payload, dict):
        return DEFAULT_THEME
    return normalize_theme(payload.get("theme"))


def save_ui_theme(root: Path, theme: str) -> Path:
    path = prefs_path(Path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload["theme"] = normalize_theme(theme)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def theme_label(theme: object) -> str:
    return THEME_LABELS[normalize_theme(theme)]


def watch_row_styles(theme: object) -> Mapping[str, str]:
    colors = palette(theme)
    fg = colors["fg"]
    coded = {
        "제안": f"background-color: {colors['proposal-row']}; color: {fg}",
        "적격": f"background-color: {colors['eligible-row']}; color: {fg}",
        "제외": f"background-color: {colors['danger-chip']}; color: {fg}",
        "관찰": f"background-color: {colors['watch-row']}; color: {fg}",
    }
    from alpha_system.ui.services.rank_watchboard import TONE_DISPLAY

    out = dict(coded)
    for key, label in TONE_DISPLAY.items():
        if key in coded:
            out[label] = coded[key]
    return out
