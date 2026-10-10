"""Stage → global sleeve recommendation bands (Review-only).

Does not write target_portfolio.csv or change QVM ranks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


SLEEVE_IDS = ("equity", "bonds", "cash", "gold")


@dataclass(frozen=True)
class SleeveBand:
    sleeve_id: str
    label: str
    pct: float
    action: str  # 늘림 | 유지 | 줄임
    why: str


# Balanced reference for action labels (approx. mid-cycle).
_REF = {"equity": 40.0, "bonds": 25.0, "cash": 20.0, "gold": 15.0}

# Forest weights by economy stage (sum 100).
_BANDS: dict[int, dict[str, float]] = {
    1: {"equity": 55.0, "bonds": 20.0, "cash": 15.0, "gold": 10.0},
    2: {"equity": 45.0, "bonds": 22.0, "cash": 20.0, "gold": 13.0},
    3: {"equity": 35.0, "bonds": 25.0, "cash": 25.0, "gold": 15.0},
    4: {"equity": 25.0, "bonds": 25.0, "cash": 35.0, "gold": 15.0},
    5: {"equity": 15.0, "bonds": 20.0, "cash": 50.0, "gold": 15.0},
}

_LABELS = {
    "equity": "주식(글로벌)",
    "bonds": "국채",
    "cash": "현금·단기채",
    "gold": "금",
}

_WHY: dict[int, dict[str, str]] = {
    1: {
        "equity": "긴축 압력 낮음 · 성장 자산 여유.",
        "bonds": "기본 분산 · 듀레이션 무리 확대 X.",
        "cash": "최소 탄약·버퍼.",
        "gold": "소량 꼬리 헤지.",
    },
    2: {
        "equity": "조금 줄임 · 품질·노른자 위주.",
        "bonds": "분산 유지.",
        "cash": "탄약 소폭↑.",
        "gold": "헤지 소폭↑.",
    },
    3: {
        "equity": "중립 · 테마 추격↓ · 노른자만.",
        "bonds": "금리·둔화 신호 시 역할↑.",
        "cash": "버퍼를 두껍게.",
        "gold": "인플레·환율 불안 시 소량.",
    },
    4: {
        "equity": "방어 · 신규 중단 기본 · AI·레버리지 주의.",
        "bonds": "고품질 국채 Review.",
        "cash": "생존·기회 탄약 우선.",
        "gold": "꼬리 헤지 유지.",
    },
    5: {
        "equity": "현금 우대 · 추격 금지 · 기술≠주가.",
        "bonds": "금리 피크·둔화 후 듀레이션 Review.",
        "cash": "유동성·생활비 최우선.",
        "gold": "극단 스트레스 헤지.",
    },
}


def _action(sleeve_id: str, pct: float) -> str:
    ref = _REF.get(sleeve_id, 25.0)
    if pct >= ref + 5.0:
        return "늘림"
    if pct <= ref - 5.0:
        return "줄임"
    return "유지"


def sleeve_bands_for_stage(stage: int | None) -> list[SleeveBand]:
    """Return four sleeve bands; empty list if stage unknown (fail-open)."""
    if stage is None:
        return []
    try:
        s = int(stage)
    except (TypeError, ValueError):
        return []
    weights = _BANDS.get(s)
    if not weights:
        return []
    why_map = _WHY.get(s, {})
    out: list[SleeveBand] = []
    for sid in SLEEVE_IDS:
        pct = float(weights[sid])
        out.append(
            SleeveBand(
                sleeve_id=sid,
                label=_LABELS[sid],
                pct=pct,
                action=_action(sid, pct),
                why=str(why_map.get(sid) or ""),
            )
        )
    return out


def alpha_envelope_line(stage: Optional[int], equity_share: float, cash_share: float) -> str:
    """KR alpha book equity/cash hint (existing ladder)."""
    if stage is None:
        return "—"
    return f"알파 봉투 개별주 {equity_share:.0%} / 단기채 {cash_share:.0%}"
