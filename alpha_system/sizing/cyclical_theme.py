"""경기민감(조선·방산·기계장비) 테마 — 점수 불변, 편입 상한만."""

from __future__ import annotations

from alpha_system.sizing.sector_map import concentration_bucket

# KRX sector_group that is already the mechanical-equipment theme.
_SECTOR_GROUPS = frozenset({"industrials"})

# 대한조선·한화오션 등은 sector_group=auto 라서 이름/내부업종으로 묶는다.
_KEYWORDS = (
    "조선",
    "오션",
    "중공업",
    "에어로스페이스",
    "방산",
    "방위",
    "선박",
    "shipbuild",
    "defense",
)


def is_cyclical_heavy(
    *,
    sector: str = "",
    name: str = "",
    internal_sector: str = "",
) -> bool:
    """True if the name sits in the shipbuilding / defense / machinery theme."""
    if concentration_bucket(sector) in _SECTOR_GROUPS:
        return True
    blob = f"{name} {sector} {internal_sector}".strip()
    if not blob:
        return False
    lower = blob.lower()
    return any(key in blob or key in lower for key in _KEYWORDS)
