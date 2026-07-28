"""Pure portfolio bar metrics — price axis vs weight/cap axis (no Streamlit)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

CapTone = Literal["ok", "warn", "danger"]

# market_value_cap 기본 35% 기준: 여유 5%p 미만(≥30%) → warn, ≥35% → danger
CAP_WARN_HEADROOM_PP = 5.0


@dataclass(frozen=True)
class PriceBarView:
    """Price-axis only. Never mixes weight/cap."""

    fill_pct: float
    """0~100 clamped fill for the bar."""
    raw_progress_pct: Optional[float]
    loss_pct: Optional[float]
    """Negative progress when current < entry; shown as text alongside clamp."""
    label: str


@dataclass(frozen=True)
class WeightBarView:
    """Weight-axis: 0 → market_value_cap scale."""

    fill_pct: float
    """0~100+ mapped as weight/cap*100, capped visually at 100 for overflow."""
    weight_pct: float
    cap_pct: float
    headroom_pp: float
    tone: CapTone
    reduce_signal: bool
    label: str


def classify_cap_tone(weight_pct: float, cap_pct: float = 35.0) -> CapTone:
    if cap_pct <= 0:
        return "ok"
    if weight_pct >= cap_pct:
        return "danger"
    if weight_pct >= (cap_pct - CAP_WARN_HEADROOM_PP):
        return "warn"
    return "ok"


def price_bar_view(price_progress_pct: Optional[float]) -> PriceBarView:
    """
    Entry→target progress. Loss (current < entry) → fill 0% + loss text.
    """
    if price_progress_pct is None:
        return PriceBarView(fill_pct=0.0, raw_progress_pct=None, loss_pct=None, label="—")
    raw = float(price_progress_pct)
    if raw < 0:
        return PriceBarView(
            fill_pct=0.0,
            raw_progress_pct=raw,
            loss_pct=raw,
            label=f"{raw:.1f}%",
        )
    fill = min(100.0, raw)
    return PriceBarView(
        fill_pct=fill,
        raw_progress_pct=raw,
        loss_pct=None,
        label=f"{raw:.1f}%",
    )


def weight_bar_view(weight_pct: float, cap_pct: float = 35.0) -> WeightBarView:
    tone = classify_cap_tone(weight_pct, cap_pct)
    headroom = round(cap_pct - weight_pct, 2)
    fill = 0.0 if cap_pct <= 0 else min(100.0, max(0.0, (weight_pct / cap_pct) * 100.0))
    reduce = tone == "danger"
    if tone == "danger":
        label = f"비중 {weight_pct:.1f}% · cap 초과 → 감축"
    elif tone == "warn":
        label = f"비중 {weight_pct:.1f}% · cap 임박 (여유 {headroom:.1f}%p)"
    else:
        label = f"비중 {weight_pct:.1f}% / cap {cap_pct:.0f}% (여유 {headroom:.1f}%p)"
    return WeightBarView(
        fill_pct=fill,
        weight_pct=weight_pct,
        cap_pct=cap_pct,
        headroom_pp=headroom,
        tone=tone,
        reduce_signal=reduce,
        label=label,
    )
