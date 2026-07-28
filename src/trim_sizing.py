from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrimGuidance:
    overweight_ppt: float
    suggested_step_ppt: float
    full_ceiling_ppt: float


def trim_config_from_rules(rules: dict) -> tuple[float, float]:
    pt = rules.get("position_triggers", {})
    step_fraction = float(pt.get("trim_step_fraction", 1 / 3))
    max_step = float(pt.get("trim_max_single_step_ppt", 2.0))
    return step_fraction, max_step


def compute_trim_guidance(
    gap: float,
    *,
    current_weight: float,
    step_fraction: float = 1 / 3,
    max_step_ppt: float = 2.0,
) -> TrimGuidance | None:
    """gap < 0 이면 과체중. 1회 Trim은 gap의 step_fraction, 상한 max_step_ppt."""
    if gap >= -0.05:
        return None
    overweight = abs(gap)
    full_ceiling = min(overweight, current_weight)
    suggested = min(overweight * step_fraction, max_step_ppt, full_ceiling)
    if suggested < 0.05:
        return None
    return TrimGuidance(
        overweight_ppt=round(overweight, 2),
        suggested_step_ppt=round(suggested, 2),
        full_ceiling_ppt=round(full_ceiling, 2),
    )


def format_trim_reason(
    guidance: TrimGuidance,
    *,
    base: str = "과체중",
) -> str:
    return (
        f"{base} {guidance.overweight_ppt:.1f}%p — "
        f"1회 권장 Trim {guidance.suggested_step_ppt:.1f}%p "
        f"(전량 {guidance.full_ceiling_ppt:.1f}%p·한 번에 한 건만)"
    )


def format_trim_short(guidance: TrimGuidance) -> str:
    return f"권장 {guidance.suggested_step_ppt:.1f}%p / 과체중 {guidance.overweight_ppt:.1f}%p"


def trim_markdown_lines(
    actions: list,
    *,
    rules: dict | None = None,
) -> list[str]:
    """TradeAction 목록에서 Trim 부분 매도 가이드 블록."""
    trims = [a for a in actions if getattr(a, "action", None) == "Trim"]
    if not trims:
        return []
    step_frac, max_step = trim_config_from_rules(rules or {})
    lines = [
        "",
        f"### Trim 부분 매도 가이드 (gap × {step_frac:.0%}, 1회 최대 {max_step:.0f}%p)",
        "",
        "> **전량 Trim 금지.** `allowed_size_pct` = 1회 권장 매도 비중(%p). 한 번에 한 종목만.",
        "",
    ]
    for act in trims:
        step = abs(float(getattr(act, "allowed_size_pct", 0)))
        lines.append(
            f"- **{act.name}** ({act.ticker}): {act.reason}"
            + (f" → **{step:.1f}%p**" if step > 0 else "")
        )
    lines.append("")
    return lines
