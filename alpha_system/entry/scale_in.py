"""Name-level scale-in schedule (SCALE_IN_OPS_RULE) — not T1–T4 portfolio tranches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence


DEFAULT_LEGS = 3
MIN_LEGS = 2
MIN_GAP_CALENDAR_DAYS = 5  # approximates ≥3 trading days across weekends


@dataclass(frozen=True)
class ScaleInLeg:
    leg_index: int  # 1-based
    fraction: float
    earliest_as_of: date


@dataclass(frozen=True)
class ScaleInPlan:
    as_of: date
    n_legs: int
    legs: tuple[ScaleInLeg, ...]
    rule_ref: str = "docs/SCALE_IN_OPS_RULE.md"

    @property
    def max_single_day_fraction(self) -> float:
        return 1.0 / float(self.n_legs)


def build_scale_in_plan(
    as_of: date,
    *,
    n_legs: int = DEFAULT_LEGS,
    gap_calendar_days: int = MIN_GAP_CALENDAR_DAYS,
) -> ScaleInPlan:
    """Equal-weight legs with calendar spacing (proxy for ≥3 trading days)."""
    if n_legs < MIN_LEGS:
        raise ValueError(f"n_legs must be >= {MIN_LEGS}, got {n_legs}")
    if n_legs > 6:
        raise ValueError(f"n_legs must be <= 6, got {n_legs}")
    frac = 1.0 / float(n_legs)
    legs: list[ScaleInLeg] = []
    for i in range(n_legs):
        legs.append(
            ScaleInLeg(
                leg_index=i + 1,
                fraction=frac,
                earliest_as_of=as_of + timedelta(days=i * gap_calendar_days),
            )
        )
    return ScaleInPlan(as_of=as_of, n_legs=n_legs, legs=tuple(legs))


def apply_leg_to_krw(full_krw: float | None, leg: ScaleInLeg) -> float | None:
    if full_krw is None:
        return None
    return float(full_krw) * float(leg.fraction)


def reject_full_dump(
    *,
    requested_fraction_of_name_budget: float,
    n_legs: int = DEFAULT_LEGS,
    tolerance: float = 1e-6,
) -> str | None:
    """
    Return block reason if a single fill tries to spend more than one leg.
    Does not touch T1–T4 tranche weights (those stay 0.25 each).
    """
    if requested_fraction_of_name_budget < 0:
        return "scale_in: negative fraction"
    max_frac = 1.0 / float(max(n_legs, MIN_LEGS))
    if requested_fraction_of_name_budget > max_frac + tolerance:
        return (
            f"scale_in: single-day fill {requested_fraction_of_name_budget:.0%} "
            f"exceeds one leg max {max_frac:.0%} ({n_legs}-way equal). "
            "See docs/SCALE_IN_OPS_RULE.md"
        )
    return None


def render_plan_markdown(
    plan: ScaleInPlan,
    *,
    rows: Sequence[tuple[str, str, float]] | None = None,
) -> str:
    """
    rows: optional (ticker, name, full_dry_weight_pct) for preview lines.
    """
    lines = [
        "## 종목 분할매수 스케줄 (SCALE_IN · 승인 규칙)",
        "",
        f"- rule: `{plan.rule_ref}`",
        f"- legs: **{plan.n_legs}** × equal ({plan.max_single_day_fraction:.0%} each)",
        f"- gap: calendar **{MIN_GAP_CALENDAR_DAYS}d** between legs (≥3 trading days proxy)",
        "- note: T1–T4 portfolio tranche weights unchanged; this is name-level execution only",
        "",
        "| leg | earliest | fraction |",
        "|-----|----------|----------|",
    ]
    for leg in plan.legs:
        lines.append(
            f"| {leg.leg_index} | {leg.earliest_as_of.isoformat()} | "
            f"{leg.fraction:.0%} |"
        )
    if rows:
        lines.extend(["", "### 1회차 미리보기 (전체 dry 비중의 1/leg)", ""])
        for ticker, name, full_pct in rows:
            leg1 = full_pct * plan.max_single_day_fraction
            lines.append(
                f"- `{ticker}` {name} — full dry {full_pct:.2f}% → "
                f"leg1 ≈ **{leg1:.2f}%**"
            )
    lines.append("")
    return "\n".join(lines)
