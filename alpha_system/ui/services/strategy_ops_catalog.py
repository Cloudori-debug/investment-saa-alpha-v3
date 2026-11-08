"""전략별 사이드바 탭 · 직접운영 메타 (Review-only · target 불변)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class StrategyOpSpec:
    strategy_id: str
    nav_label: str
    hint: str
    group: str  # individual | momentum | static


# 사이드바: Soft · 단기 · 정적(묶음) · 듀얼
STRATEGY_OP_SPECS: tuple[StrategyOpSpec, ...] = (
    StrategyOpSpec(
        "mid_soft",
        "중기 Soft",
        "알파 Soft · 포트 집행",
        "individual",
    ),
    StrategyOpSpec(
        "short_momentum",
        "단기 모멘텀",
        "알파 위성 · 비혼합",
        "momentum",
    ),
    StrategyOpSpec(
        "static_book",
        "정적 배분",
        "가계 본체(나침반적합) · 연리밸",
        "static",
    ),
    StrategyOpSpec(
        "dual_momentum",
        "듀얼모멘텀",
        "선택 위성 · 월 GEM·전량",
        "momentum",
    ),
)

# 예전 정적 개별 탭 → 정적 배분으로
LEGACY_STATIC_IDS: tuple[str, ...] = (
    "sixty_forty",
    "all_seasons",
    "permanent",
    "golden_butterfly",
    "k_all_weather",
)

PAGE_STRATEGY_PREFIX = "전략·"


def strategy_page_key(strategy_id: str) -> str:
    return f"{PAGE_STRATEGY_PREFIX}{strategy_id}"


def strategy_id_from_page(page: str) -> str | None:
    p = str(page or "")
    if not p.startswith(PAGE_STRATEGY_PREFIX):
        return None
    sid = p[len(PAGE_STRATEGY_PREFIX) :]
    if sid in LEGACY_STATIC_IDS:
        return "static_book"
    return sid


STRATEGY_OP_PAGES: tuple[str, ...] = tuple(
    strategy_page_key(s.strategy_id) for s in STRATEGY_OP_SPECS
)


def strategy_op_specs() -> Sequence[StrategyOpSpec]:
    return STRATEGY_OP_SPECS


def is_strategy_op_page(page: str) -> bool:
    return strategy_id_from_page(page) is not None


def legacy_static_page_redirects() -> dict[str, str]:
    dest = strategy_page_key("static_book")
    return {strategy_page_key(sid): dest for sid in LEGACY_STATIC_IDS}


__all__ = [
    "LEGACY_STATIC_IDS",
    "PAGE_STRATEGY_PREFIX",
    "STRATEGY_OP_PAGES",
    "STRATEGY_OP_SPECS",
    "StrategyOpSpec",
    "is_strategy_op_page",
    "legacy_static_page_redirects",
    "strategy_id_from_page",
    "strategy_op_specs",
    "strategy_page_key",
]
