"""Curated KR-listed Executable ETF picks per forest sleeve (Review-only).

Does not write target_portfolio.csv or place orders. Each sleeve lists 2–3
liquid ETFs with within-sleeve weights. Economic exposure prefers USD/global
proxies; KRW bonds/cash are a small buffer only — not the core duration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from alpha_system.economy_compass.sleeves import SleeveBand


@dataclass(frozen=True)
class ExecutableLeg:
    """One ETF inside a sleeve; sleeve_weight_pct sums to ~100 within sleeve."""

    ticker: str
    name: str
    sleeve_weight_pct: float
    why: str


@dataclass(frozen=True)
class ExecutablePick:
    sleeve_id: str
    sleeve_label: str
    pct: float
    action: str
    legs: tuple[ExecutableLeg, ...]
    compared: str

    @property
    def ticker(self) -> str:
        """Primary (largest-weight) leg — backward-compatible."""
        if not self.legs:
            return ""
        return max(self.legs, key=lambda x: x.sleeve_weight_pct).ticker

    @property
    def name(self) -> str:
        if not self.legs:
            return ""
        return max(self.legs, key=lambda x: x.sleeve_weight_pct).name

    @property
    def why(self) -> str:
        if not self.legs:
            return ""
        return max(self.legs, key=lambda x: x.sleeve_weight_pct).why


# sleeve_id → (legs, compared note)
# 경제노출=글로벌 · 상장=KRX · 국고/원화단기는 완충만
_PICKS: dict[str, tuple[tuple[ExecutableLeg, ...], str]] = {
    "equity": (
        (
            ExecutableLeg(
                "360750",
                "TIGER 미국S&P500",
                50.0,
                "미국 대형 베타 · 유동성·순자산 최상위.",
            ),
            ExecutableLeg(
                "195930",
                "TIGER 유로스탁스50",
                25.0,
                "유럽 대형 · EAFE 근사(미국 편중↓).",
            ),
            ExecutableLeg(
                "241180",
                "TIGER 일본니케이225",
                25.0,
                "일본 대형 · 지역·통화 분산.",
            ),
        ),
        "나스닥100·레버리지·섹터 제외 · 195980은 신흥국(유로 아님) · Soft 개별주와 합산 금지.",
    ),
    "bonds": (
        (
            ExecutableLeg(
                "305080",
                "TIGER 미국채10년선물",
                50.0,
                "미 중기채(IEF) · 본체·봉투 듀레이션 주력(고금리·2022형).",
            ),
            ExecutableLeg(
                "453850",
                "ACE 미국30년국채액티브(H)",
                30.0,
                "미 장기채(TLT) · 둔화·금리급락 틸트(본체 제외·봉투만).",
            ),
            ExecutableLeg(
                "365780",
                "ACE 국고채10년",
                20.0,
                "원화 국채 완충만 · 숲 듀레이션의 주력이 아님.",
            ),
        ),
        "하이일드·회사채·커버드콜·레버 제외 · 10y 주력+30y 틸트 · 국채↔현금 보완은 본체.",
    ),
    "cash": (
        (
            ExecutableLeg(
                "329750",
                "TIGER 미국달러단기채권액티브",
                60.0,
                "달러 초단기(BIL 근사) · 절대모멘텀·대기 축.",
            ),
            ExecutableLeg(
                "214980",
                "KODEX 단기채권PLUS",
                40.0,
                "원화 단기 완충 · 생활비·국내 결제용.",
            ),
        ),
        "중장기 채권은 bonds · CMA/예금도 동일 슬리브 가능.",
    ),
    "gold": (
        (
            ExecutableLeg(
                "411060",
                "ACE KRX금현물",
                70.0,
                "금 현물 · 롤오버 없음 · 헤지 핵심.",
            ),
            ExecutableLeg(
                "132030",
                "KODEX 골드선물(H)",
                30.0,
                "금 선물(환헤지) · 유동성 보조(롤 비용 인지).",
            ),
        ),
        "은·구리 등 원자재 테마는 숲 금 슬리브와 역할이 다름.",
    ),
}


def executable_lines(sleeves: Sequence[SleeveBand]) -> tuple[ExecutablePick, ...]:
    """Attach diversified ETF legs to each sleeve band; empty if no bands."""
    out: list[ExecutablePick] = []
    for band in sleeves:
        meta = _PICKS.get(band.sleeve_id)
        if meta is None:
            continue
        legs, compared = meta
        # Normalize sleeve weights to sum 100 (defensive).
        total_w = sum(max(0.0, float(x.sleeve_weight_pct)) for x in legs) or 1.0
        norm_legs = tuple(
            ExecutableLeg(
                ticker=x.ticker,
                name=x.name,
                sleeve_weight_pct=round(100.0 * float(x.sleeve_weight_pct) / total_w, 1),
                why=x.why,
            )
            for x in legs
        )
        out.append(
            ExecutablePick(
                sleeve_id=band.sleeve_id,
                sleeve_label=band.label,
                pct=float(band.pct),
                action=band.action,
                legs=norm_legs,
                compared=compared,
            )
        )
    return tuple(out)


def leg_book_pct(sleeve_pct: float, sleeve_weight_pct: float) -> float:
    """Absolute book % for one leg (sleeve band × within-sleeve weight)."""
    return round(float(sleeve_pct) * float(sleeve_weight_pct) / 100.0, 1)
