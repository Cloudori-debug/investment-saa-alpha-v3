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

# Light = warm cream; dark = warm charcoal. Contrast tuned so body/muted
# stay readable and tables never fall back to near-black slabs in light.
_PALETTES: dict[str, dict[str, str]] = {
    THEME_LIGHT: {
        "bg": "#f3efe6",
        "surface": "#faf7f1",
        "card": "#ffffff",
        "fg": "#1a1814",
        "muted": "#5c574e",
        "subtle": "#5b6573",
        "accent": "#2d4a3c",
        "on-accent": "#faf7f1",
        "border": "#d5cdc0",
        "border-strong": "#c4bdb0",
        "hairline": "#e6dfd4",
        "ink": "#1a1814",
        "ink-strong": "#12100e",
        "muted-bg": "#f0ebe3",
        "danger": "#dc2626",
        "danger-strong": "#b91c1c",
        "danger-bg": "#fef2f2",
        "danger-fg": "#9b1c1c",
        "danger-chip": "#fee2e2",
        "warn": "#c2410c",
        "warn-bg": "#fff7ed",
        "warn-chip": "#ffedd5",
        "warn-fg": "#9a3412",
        "warn-text": "#7c2d12",
        "warn-strong": "#c2410c",
        "warn-border": "#fdba74",
        "slate": "#788390",
        "slate-fg": "#3f4b59",
        "slate-ink": "#2c3643",
        "ok": "#2e7d32",
        "ok-fg": "#14532d",
        "ok-bg": "#e8f0ea",
        "ok-border": "#9bb5a6",
        "ok-chip": "#dcfce7",
        "chart": "#1e3a5f",
        "chart-bg": "#eef3f8",
        "chart-border": "#8fa0b3",
        "list-border": "#cfc6b8",
        "table-line": "#e0d8cc",
        "table-bg": "#ffffff",
        "table-head": "#f0ebe3",
        "input-bg": "#ffffff",
        "input-fg": "#1a1814",
        "popover-bg": "#ffffff",
        "popover-fg": "#1a1814",
        "popover-hover": "#f0ebe3",
        "read-bg": "#efe8d8",
        "read-fg": "#1a1814",
        "read-border": "#b7a88a",
        "read-hot-bg": "#f3ddb0",
        "read-hot-fg": "#4a3200",
        "read-hot-border": "#c9a227",
        "read-weak-bg": "#dce6f0",
        "read-weak-fg": "#1a334d",
        "read-weak-border": "#7b93ab",
        "read-ok-bg": "#dce8dc",
        "read-ok-fg": "#1c3324",
        "read-ok-border": "#6a8a72",
        "proposal-row": "#dcfce7",
        "eligible-row": "#ffedd5",
        "watch-row": "#ffffff",
    },
    THEME_DARK: {
        "bg": "#161410",
        "surface": "#1f1b16",
        "card": "#2a251e",
        "fg": "#f5f0e6",
        "muted": "#c9c0b3",
        "subtle": "#b0a89c",
        "accent": "#9bc4a6",
        "on-accent": "#121410",
        "border": "#453e34",
        "border-strong": "#5a5246",
        "hairline": "#342f28",
        "ink": "#f0ebe3",
        "ink-strong": "#faf6ee",
        "muted-bg": "#252018",
        "danger": "#f07171",
        "danger-strong": "#ef5350",
        "danger-bg": "#3a1c1c",
        "danger-fg": "#f7c4c4",
        "danger-chip": "#4a2222",
        "warn": "#e8a54b",
        "warn-bg": "#3a2e18",
        "warn-chip": "#4a3a1c",
        "warn-fg": "#f5d09a",
        "warn-text": "#f5d09a",
        "warn-strong": "#e8a54b",
        "warn-border": "#6b5428",
        "slate": "#9aa3b0",
        "slate-fg": "#d0d5dd",
        "slate-ink": "#e2e6ec",
        "ok": "#81c784",
        "ok-fg": "#b7e0bc",
        "ok-bg": "#24352c",
        "ok-border": "#4a6b58",
        "ok-chip": "#2a4034",
        "chart": "#7eb0d4",
        "chart-bg": "#1a2838",
        "chart-border": "#4a6a82",
        "list-border": "#453e34",
        "table-line": "#453e34",
        "table-bg": "#2a251e",
        "table-head": "#252018",
        "input-bg": "#1f1b16",
        "input-fg": "#f5f0e6",
        "popover-bg": "#2a251e",
        "popover-fg": "#f5f0e6",
        "popover-hover": "#353028",
        "read-bg": "#3a2e18",
        "read-fg": "#f5d09a",
        "read-border": "#6b5428",
        "read-hot-bg": "#4a3a1c",
        "read-hot-fg": "#f5d09a",
        "read-hot-border": "#8a6a30",
        "read-weak-bg": "#1a2838",
        "read-weak-fg": "#b8d4e8",
        "read-weak-border": "#4a6a82",
        "read-ok-bg": "#24352c",
        "read-ok-fg": "#b7e0bc",
        "read-ok-border": "#4a6b58",
        "proposal-row": "#24352c",
        "eligible-row": "#3a2e18",
        "watch-row": "#2a251e",
    },
}

# Longest hex first so #fff does not eat #ffffff / #fffbeb.
_HEX_TO_VAR: tuple[tuple[str, str], ...] = (
    ("rgba(255, 255, 255, 0.95)", "var(--saa-card)"),
    ("rgba(255,255,255,0.94)", "var(--saa-card)"),
    ("rgba(255,255,255,0.92)", "var(--saa-card)"),
    ("#ffffff", "var(--saa-card)"),
    ("#fff7ed", "var(--saa-warn-bg)"),
    ("#fffbeb", "var(--saa-warn-bg)"),
    ("#ffedd5", "var(--saa-warn-chip)"),
    ("#fef3c7", "var(--saa-warn-chip)"),
    ("#fef2f2", "var(--saa-danger-bg)"),
    ("#f8fafc", "var(--saa-muted-bg)"),
    ("#fafafa", "var(--saa-muted-bg)"),
    ("#f5efe6", "var(--saa-muted-bg)"),
    ("#f4f7f4", "var(--saa-ok-bg)"),
    ("#f0ebe3", "var(--saa-muted-bg)"),
    ("#f3efe6", "var(--saa-bg)"),
    ("#faf7f1", "var(--saa-surface)"),
    ("#efe8d8", "var(--saa-read-bg)"),
    ("#f3ddb0", "var(--saa-read-hot-bg)"),
    ("#dce6f0", "var(--saa-read-weak-bg)"),
    ("#dce8dc", "var(--saa-read-ok-bg)"),
    ("#dcfce7", "var(--saa-ok-chip)"),
    ("#dcd4c6", "var(--saa-border)"),
    ("#d5cdc0", "var(--saa-border)"),
    ("#d8dee6", "var(--saa-table-line)"),
    ("#d4c4a8", "var(--saa-read-border)"),
    ("#c5d4c8", "var(--saa-ok-border)"),
    ("#c4bdb0", "var(--saa-border-strong)"),
    ("#c4b5a0", "var(--saa-read-border)"),
    ("#b7a88a", "var(--saa-read-border)"),
    ("#1c1a16", "var(--saa-fg)"),
    ("#1a1814", "var(--saa-fg)"),
    ("#1a334d", "var(--saa-read-weak-fg)"),
    ("#1c3324", "var(--saa-read-ok-fg)"),
    ("#4a3200", "var(--saa-read-hot-fg)"),
    ("#6b4f2a", "var(--saa-warn-text)"),
    ("#6f6a60", "var(--saa-muted)"),
    ("#5c574e", "var(--saa-muted)"),
    ("#2d4a3c", "var(--saa-accent)"),
    ("#2e7d32", "var(--saa-ok)"),
    ("#14532d", "var(--saa-ok-fg)"),
    ("#64748b", "var(--saa-subtle)"),
    ("#5b6573", "var(--saa-subtle)"),
    ("#d1d5db", "var(--saa-border-strong)"),
    ("#1e293b", "var(--saa-ink)"),
    ("#0f172a", "var(--saa-ink-strong)"),
    ("#12100e", "var(--saa-ink-strong)"),
    ("#d97706", "var(--saa-warn)"),
    ("#c2410c", "var(--saa-warn)"),
    ("#ef6c00", "var(--saa-warn)"),
    ("#c9a227", "var(--saa-read-hot-border)"),
    ("#fdba74", "var(--saa-warn-border)"),
    ("#f0c36a", "var(--saa-warn-border)"),
    ("#f0a8a8", "var(--saa-danger)"),
    ("#94a3b8", "var(--saa-slate)"),
    ("#788390", "var(--saa-slate)"),
    ("#7b93ab", "var(--saa-read-weak-border)"),
    ("#6a8a72", "var(--saa-read-ok-border)"),
    ("#475569", "var(--saa-slate-fg)"),
    ("#3f4b59", "var(--saa-slate-fg)"),
    ("#ef4444", "var(--saa-danger)"),
    ("#c62828", "var(--saa-danger-strong)"),
    ("#991b1b", "var(--saa-danger-fg)"),
    ("#9b1c1c", "var(--saa-danger-fg)"),
    ("#7a4a00", "var(--saa-warn-fg)"),
    ("#7c2d12", "var(--saa-warn-text)"),
    ("#e2e8f0", "var(--saa-hairline)"),
    ("#e6dfd4", "var(--saa-hairline)"),
    ("#f0d9a8", "var(--saa-warn-border)"),
    ("#b45309", "var(--saa-warn-strong)"),
    ("#78350f", "var(--saa-warn-text)"),
    ("#dc2626", "var(--saa-danger-strong)"),
    ("#b91c1c", "var(--saa-danger-strong)"),
    ("#92400e", "var(--saa-warn-fg)"),
    ("#9a3412", "var(--saa-warn-fg)"),
    ("#fee2e2", "var(--saa-danger-chip)"),
    ("#e4ebe4", "var(--saa-ok-bg)"),
    ("#e8f0ea", "var(--saa-ok-bg)"),
    ("#cbd5e1", "var(--saa-list-border)"),
    ("#cfc6b8", "var(--saa-list-border)"),
    ("#8fa0b3", "var(--saa-chart-border)"),
    ("#eef3f8", "var(--saa-chart-bg)"),
    ("#1e3a5f", "var(--saa-chart)"),
    ("#e5e7eb", "var(--saa-table-line)"),
    ("#e0d8cc", "var(--saa-table-line)"),
    ("#9bb5a6", "var(--saa-ok-border)"),
    ("#86efac", "var(--saa-ok-border)"),
    ("#334155", "var(--saa-slate-ink)"),
    ("#2c3643", "var(--saa-slate-ink)"),
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
    """Row fills for ② 후보 Styler — always pair theme fg with theme row bg."""
    colors = palette(theme)
    fg = colors["fg"]
    # Explicit color so Streamlit does not keep the opposite theme ink.
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
