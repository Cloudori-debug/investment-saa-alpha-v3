"""Home status / freshness one-liners — no Streamlit."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional, Sequence

from alpha_system.ui.services.data_freshness import SourceStatus

# Home one-liner keys (dashboard.yaml) — prices / regime proxy / T3
_HOME_SOURCE_KEYS: tuple[tuple[str, str], ...] = (
    ("prices", "종가"),
    ("benchmark", "레짐"),
    ("kospi_pbr_history", "T3"),
)


def age_ko(as_of: Optional[date], today: date) -> str:
    if as_of is None:
        return "없음"
    days = (today - as_of).days
    if days <= 0:
        return "오늘"
    if days == 1:
        return "어제"
    return f"{days}일 전"


def status_line(
    *,
    pre_launch: bool,
    held_n: int,
    next_title: Optional[str],
) -> str:
    live = "가동 전" if pre_launch else "가동 중"
    held = "실보유 없음" if int(held_n or 0) <= 0 else f"실보유 {int(held_n)}종"
    todo = next_title.strip() if next_title else "오늘 할 일 없음"
    return f"{live} · {held} · {todo}"


def freshness_line(
    sources: Sequence[SourceStatus] | Iterable[SourceStatus],
    today: date,
) -> tuple[str, bool]:
    """Return ('종가 어제 · 레짐 35일 전 · T3 59일 전', any_attention)."""
    by_key = {s.key: s for s in sources}
    bits: list[str] = []
    attention = False
    for key, label in _HOME_SOURCE_KEYS:
        src = by_key.get(key)
        if src is None:
            bits.append(f"{label} 없음")
            attention = True
            continue
        if not src.exists:
            bits.append(f"{label} 없음")
            attention = True
            continue
        bits.append(f"{label} {age_ko(src.as_of, today)}")
        if src.stale:
            attention = True
    return " · ".join(bits), attention
