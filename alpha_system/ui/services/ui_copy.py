"""Load user-facing copy from docs/UI_COPY.md (YAML fence) — no hardcoded UI strings."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PATH = _ROOT / "docs" / "UI_COPY.md"


@lru_cache(maxsize=2)
def load_ui_copy(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    match = re.search(r"```yaml\s*\n(.*?)```", text, flags=re.DOTALL)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else {}


def copy_get(*keys: str, default: str = "", **fmt: Any) -> str:
    node: Any = load_ui_copy()
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default.format(**fmt) if fmt and default else default
        node = node[key]
    if not isinstance(node, str):
        return default
    try:
        return node.format(**fmt) if fmt else node
    except (KeyError, ValueError):
        return node


def tranche_display(tranche_id: str) -> tuple[str, str]:
    """Return (display_name, short_desc)."""
    data = load_ui_copy().get("tranches") or {}
    row = data.get(tranche_id) or {}
    name = str(row.get("display_name") or tranche_id)
    desc = str(row.get("short_desc") or "")
    return name, desc


def format_tranche_label(tranche_id: str) -> str:
    name, _ = tranche_display(tranche_id)
    return f"{name} ({tranche_id})"
