"""Merge ops badge (유지/줄이기/…) with chart readout into one Review cue.

Does not write target_portfolio.csv or change QVM ranks.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpha_system.proposal_chart import ChartRead, _trade_verdict, summary_tone


@dataclass(frozen=True)
class UnifiedTradeCue:
    """Single operator-facing action from book badge + daily chart."""

    action: str
    headline: str
    why: str
    evidence_ops: str
    evidence_chart: str
    chart_reason: str
    chips: tuple[str, ...]
    detail: str
    tone: str  # accent | warn | danger | muted | hot | weak | ok
    ops_part: str
    chart_part: str


def _headline(action: str) -> str:
    """Scan-friendly signal label (one glance)."""
    mapping = {
        "유지 · 추가금지": "보유 · 더 사지 않음",
        "유지 · 추격금지": "보유 · 더 사지 않음",
        "유지 · 매수보류": "보유 · 관망",
        "유지 · 축소검토": "보유 · 축소 검토",
        "유지 · 소량만": "소량·사다리만",
        "비중 줄이기": "비중 줄이기",
        "교체·청산 검토": "교체·청산 검토",
        "유지": "보유 유지",
        "관망": "신호 · 관망",
    }
    return mapping.get(action, action)


def _indicator_chips(chart: ChartRead | None) -> tuple[str, ...]:
    if chart is None:
        return ()
    parts: list[str] = []
    if (chart.ma_label or "").strip():
        parts.append(f"이평 {chart.ma_label.strip()}")
    if (chart.rsi_label or "").strip():
        parts.append(f"RSI {chart.rsi_label.strip()}")
    if (chart.bb_label or "").strip():
        parts.append(f"BB {chart.bb_label.strip()}")
    if (chart.macd_label or "").strip():
        parts.append(f"MACD {chart.macd_label.strip()}")
    if (chart.macd_hist_label or "").strip():
        parts.append(chart.macd_hist_label.strip())
    if (chart.macd_div_label or "").strip():
        parts.append(chart.macd_div_label.strip())
    return tuple(parts)


def _finish(
    *,
    action: str,
    why: str,
    tone: str,
    ops_part: str,
    chart_part: str,
    chart_reason: str = "",
    chart: ChartRead | None = None,
) -> UnifiedTradeCue:
    hl = _headline(action)
    ev_ops = ops_part or "—"
    if chart_part and chart_part != "차트미읽음":
        ev_chart = chart_part
    elif (chart and (chart.note or "").strip()):
        ev_chart = chart.note.strip()
    else:
        ev_chart = "일봉 미읽음"
    detail = why
    return UnifiedTradeCue(
        action=action,
        headline=hl,
        why=why,
        evidence_ops=ev_ops,
        evidence_chart=ev_chart,
        chart_reason=(chart_reason or "").strip(),
        chips=_indicator_chips(chart),
        detail=detail,
        tone=tone,
        ops_part=ops_part,
        chart_part=chart_part,
    )


def _chart_verdict(item: ChartRead | None, *, ladder: str = "") -> tuple[str, str]:
    if item is None:
        return "", ""
    if (item.note or "").strip():
        return "차트 데이터 부족", item.note.strip()
    if not (item.ma_label or item.rsi_label or item.bb_label or item.macd_label):
        return "", ""
    rung = (ladder or "").replace("지금 ", "").replace("사다리 ", "").strip()
    return _trade_verdict(
        ma_label=item.ma_label,
        rsi_label=item.rsi_label,
        bb_label=item.bb_label,
        macd_label=item.macd_label,
        macd_hist_label=item.macd_hist_label,
        macd_div_label=item.macd_div_label,
        rung=rung,
    )


def unify_ops_and_chart(
    *,
    ops_kind: str = "",
    ops_label: str = "",
    chart: ChartRead | None = None,
    ladder: str = "",
) -> UnifiedTradeCue:
    """Priority: book exit/trim > chart no-buy > hold+chart keep."""
    kind = (ops_kind or "").strip()
    label = (ops_label or "").strip() or {
        "hold": "유지",
        "trim": "줄이기",
        "cash_half": "줄이기",
        "exit_full": "교체",
        "missing": "신호대기",
        "invalid": "데이터없음",
        "review": "검토",
    }.get(kind, "")

    chart_v, chart_why = _chart_verdict(chart, ladder=ladder)
    ops_part = label or "배지없음"
    chart_part = chart_v or "차트미읽음"

    if kind == "exit_full":
        action = "교체·청산 검토"
        if chart_v and ("금지" in chart_v or "보류" in chart_v):
            why = (
                "장부 교체·청산이 우선입니다. 차트도 매수 보류·금지라 "
                "신규 매수는 하지 마세요."
            )
        else:
            why = "장부 교체·청산 신호입니다. 포트폴리오에서 Review만 하세요."
        return _finish(
            action=action,
            why=why,
            tone="danger",
            ops_part=ops_part,
            chart_part=chart_part,
            chart_reason=chart_why,
            chart=chart,
        )

    if kind in {"trim", "cash_half"}:
        action = "비중 줄이기"
        if chart_v and ("매수" in chart_v and "검토" in chart_v and "금지" not in chart_v):
            why = (
                "장부 줄이기가 우선입니다. 차트가 매수 쪽이어도 추매하지 말고 "
                "축소만 Review하세요."
            )
        else:
            why = "장부 줄이기 신호입니다. 추가 매수 없이 비중만 줄이는 쪽을 Review하세요."
        return _finish(
            action=action,
            why=why,
            tone="warn",
            ops_part=ops_part,
            chart_part=chart_part,
            chart_reason=chart_why,
            chart=chart,
        )

    if chart_v:
        if "금지" in chart_v or ("보류" in chart_v and "축소" in chart_v):
            action = "유지 · 추가금지"
            why = (
                f"장부는 {ops_part or '유지'}인데, 차트는 지금 더 사지 말라는 구간입니다. "
                f"{chart_why}"
            ).strip()
            return _finish(
                action=action,
                why=why,
                tone="hot",
                ops_part=ops_part or "유지",
                chart_part=chart_part,
                chart_reason=chart_why,
                chart=chart,
            )
        if "보류" in chart_v:
            action = "유지 · 매수보류"
            why = (
                f"장부는 {ops_part or '유지'}입니다. 차트는 매수 타이밍을 보류하라고 합니다. "
                f"{chart_why}"
            ).strip()
            return _finish(
                action=action,
                why=why,
                tone="warn",
                ops_part=ops_part or "유지",
                chart_part=chart_part,
                chart_reason=chart_why,
                chart=chart,
            )
        if "축소" in chart_v:
            action = "유지 · 축소검토"
            why = (
                f"장부는 {ops_part or '유지'}이나 차트는 비중 축소를 검토하라고 합니다. "
                f"{chart_why}"
            ).strip()
            return _finish(
                action=action,
                why=why,
                tone="warn",
                ops_part=ops_part or "유지",
                chart_part=chart_part,
                chart_reason=chart_why,
                chart=chart,
            )
        if "분할" in chart_v or "첫 매수" in chart_v or "천천히" in chart_v:
            action = "유지 · 소량만"
            why = (
                f"장부 {ops_part or '유지'} + 차트는 소량·사다리만 검토하라고 합니다. "
                f"{chart_why}"
            ).strip()
            return _finish(
                action=action,
                why=why,
                tone="ok",
                ops_part=ops_part or "유지",
                chart_part=chart_part,
                chart_reason=chart_why,
                chart=chart,
            )
        if "유지" in chart_v:
            action = "유지 · 추격금지"
            why = (
                f"장부 {ops_part or '유지'} + 차트는 보유 유지, 추격 매수는 금지입니다. "
                f"{chart_why}"
            ).strip()
            return _finish(
                action=action,
                why=why,
                tone="ok",
                ops_part=ops_part or "유지",
                chart_part=chart_part,
                chart_reason=chart_why,
                chart=chart,
            )
        action = ops_part or "관망"
        why = f"차트: {chart_v}. {chart_why} 장부 배지는 {ops_part or '없음'}입니다."
        tone = summary_tone(chart) if chart else "muted"
        return _finish(
            action=action,
            why=why.strip(),
            tone=tone,
            ops_part=ops_part,
            chart_part=chart_part,
            chart_reason=chart_why,
            chart=chart,
        )

    if kind == "hold" or label == "유지":
        return _finish(
            action="유지",
            why="장부는 유지입니다. 「일봉 읽기」를 누르면 추가·추격 여부를 합쳐 표시합니다.",
            tone="accent",
            ops_part=ops_part,
            chart_part=chart_part,
            chart=chart,
        )
    if label:
        return _finish(
            action=label,
            why=f"장부 「{label}」 Review입니다. 일봉을 읽어 타이밍을 합치세요.",
            tone="warn" if kind in {"trim", "cash_half", "missing", "invalid"} else "muted",
            ops_part=ops_part,
            chart_part=chart_part,
            chart=chart,
        )
    return _finish(
        action="관망",
        why="배지·일봉을 확인한 뒤 Review하세요. 자동매매 없음.",
        tone="muted",
        ops_part=ops_part,
        chart_part=chart_part,
        chart=chart,
    )
