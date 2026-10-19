"""Lifecycle-aware unified trade cue (edition)."""

from __future__ import annotations

from alpha_system.proposal_chart import ChartRead
from alpha_system.ui.services.trade_cue_merge import UnifiedTradeCue, unify_ops_and_chart


def unify_with_lifecycle(
    *,
    ops_kind: str = "",
    ops_label: str = "",
    chart: ChartRead | None = None,
    ladder: str = "",
    lifecycle_state: str = "",
    lifecycle_label: str = "",
    lifecycle_why: str = "",
    lifecycle_weeks_out: int = 0,
    quality_line: str = "",
) -> UnifiedTradeCue:
    base = unify_ops_and_chart(
        ops_kind=ops_kind,
        ops_label=ops_label,
        chart=chart,
        ladder=ladder,
    )
    st = (lifecycle_state or "").strip()
    if not st:
        return base

    tone = base.tone
    action = base.action
    headline = base.headline
    why = base.why

    if st == "thesis_review":
        action = "가설·즉시 검토"
        headline = "가설·즉시 검토"
        why = lifecycle_why or base.why
        tone = "danger"
    elif st == "cap_trim":
        action = "비중 줄이기"
        headline = "비중 줄이기"
        why = lifecycle_why or base.why
        tone = "warn" if tone not in {"hot", "danger"} else tone
    elif st == "rotate_review":
        action = "교체 검토"
        headline = "월말 · 교체 검토"
        why = lifecycle_why or base.why
        tone = "warn"
    elif st == "just_dropped":
        action = "제안 이탈"
        headline = "제안 이탈 · 지금 확인"
        why = lifecycle_why or base.why
        tone = "hot"
    elif st == "watch":
        if "추가" not in headline and "금지" not in headline:
            headline = "보유 · 관찰"
        why = f"{lifecycle_why} {base.why}".strip()
        tone = "weak" if tone == "ok" else tone
    elif st == "buy_ok":
        pass

    ev_state = lifecycle_label or st
    if lifecycle_weeks_out > 0:
        ev_state = f"{ev_state} ({lifecycle_weeks_out}주 제안 밖)"

    chips = base.chips
    if quality_line:
        chips = chips + (quality_line[:80],)

    return UnifiedTradeCue(
        action=action,
        headline=headline,
        why=why,
        evidence_ops=base.evidence_ops,
        evidence_chart=base.evidence_chart,
        chart_reason=base.chart_reason,
        chips=chips,
        detail=why,
        tone=tone,
        ops_part=base.ops_part,
        chart_part=base.chart_part,
    )
