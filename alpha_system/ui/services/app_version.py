"""앱 표시용 버전 (사이드바 등). VERSION 파일 + 가능하면 git short hash."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def read_version() -> str:
    path = _REPO_ROOT / "VERSION"
    try:
        text = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        return text or "0.0.0"
    except OSError:
        return "0.0.0"


@lru_cache(maxsize=1)
def git_short_hash() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if out.returncode != 0:
            return None
        h = (out.stdout or "").strip()
        return h or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def sidebar_version_label() -> str:
    """예: v3.0.2 · fe030ec"""
    ver = read_version()
    label = f"v{ver}" if not ver.lower().startswith("v") else ver
    h = git_short_hash()
    if h:
        return f"{label} · {h}"
    return label
