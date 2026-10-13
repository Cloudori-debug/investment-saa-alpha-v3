"""Merge daily chart + investor-flow into one Review cue.

Review-only — never writes scores or target_portfolio.
Priority when conflict: chart no-buy/hold-back > flow distribution > flow accumulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Literal

from alpha_system.proposal_chart import ChartRead, _trade_verdict, summary_tone
from alpha_system.ui.services.flow_review_board import (
    _SIGNAL_KO,
    _fmt_mcap_pct,
    _pct,
)

Alignment = Literal["align", "conflict", "partial", "single"]
Stance = Literal["bull", "bear", "neutral", "unknown"]


@dataclass(frozen=True)
class ChartFlowCue:
    action: str
    why: str
    alignment: Alignment
    tone: str  # ok | warn | hot | muted
    chart_stance: Stance
    flow_stance: Stance
    chart_text: str
    flow_text: str
    flow_signal: str
    foreign_5d: str
    institution_5d: str


def _chart_verdict(chart: ChartRead | None) -> tuple[str, str]:
    if chart is None:
        return "", ""
    if (chart.note or "").strip():
        return "차트 데이터 부족", chart.note.strip()
    if not (chart.ma_label or chart.rsi_label or chart.bb_label or chart.macd_label):
        return "", ""
    return _trade_verdict(
        ma_label=chart.ma_label,
        rsi_label=chart.rsi_label,
        bb_label=chart.bb_label,
        macd_label=chart.macd_label,
        macd_hist_label=chart.macd_hist_label,
        macd_div_label=chart.macd_div_label,
        rung="",
    )


def _chart_stance(verdict: str, chart: ChartRead | None) -> Stance:
    if not verdict:
        return "unknown"
    # "보유 유지 · 추격 매수 금지" = trend OK, do not chase → bullish-leaning hold
    if "유지" in verdict and "추격" in verdict:
        return "bull"
    if "분할" in verdict or "첫 매수" in verdict or "천천히" in verdict:
        return "bull"
    if "추가 매수 금지" in verdict or "신규·추가" in verdict:
        return "bear"
    if "보류" in verdict or "축소" in verdict or "관망 우선" in verdict:
        return "bear"
    if "매수" in verdict and "금지" not in verdict:
        return "bull"
    if "유지" in verdict:
        return "neutral"
    if chart is not None:
        st = summary_tone(chart)
        if st == "hot":
            return "bear"
        if st == "weak":
            return "bear"
        if st == "ok":
            return "bull"
    return "neutral"


def _flow_stance(signal: str) -> Stance:
    if signal in {"ACCUMULATION", "MILD_ACCUMULATION"}:
        return "bull"
    if signal == "DISTRIBUTION":
        return "bear"
    if signal == "NEUTRAL":
        return "neutral"
    return "unknown"


def _alignment(cs: Stance, fs: Stance) -> Alignment:
    if cs == "unknown" and fs == "unknown":
        return "partial"
    if cs == "unknown" or fs == "unknown":
        return "single"
    if cs == "neutral" or fs == "neutral":
        return "partial"
    if cs == fs:
        return "align"
    return "conflict"


def unify_chart_and_flow(
    *,
    chart: ChartRead | None,
    flow_info: dict[str, Any] | None,
) -> ChartFlowCue | None:
    """Build one Review action from chart + flow. None if both empty."""
    info = flow_info or {}
    sig = str(info.get("flow_signal") or "STALE")
    source = str(info.get("source") or "")
    flow_missing = sig == "STALE" and source in {"missing", "template", ""}

    verdict, chart_why = _chart_verdict(chart)
    cs = _chart_stance(verdict, chart)
    fs = _flow_stance("STALE" if flow_missing else sig)
    align = _alignment(cs, fs)

    flow_ko = "데이터 없음" if flow_missing else _SIGNAL_KO.get(sig, sig)
    f5 = _fmt_mcap_pct(_pct(info.get("foreign_5d_mcap_pct")))
    i5 = _fmt_mcap_pct(_pct(info.get("institution_5d_mcap_pct")))
    chart_text = verdict or ("일봉 미읽음" if chart is None else "차트 신호 약함")
    flow_text = flow_ko if flow_missing else f"{flow_ko} · 외인 {f5} · 기관 {i5}"

    if cs == "unknown" and (fs == "unknown" or flow_missing):
        if flow_missing and chart is None:
            return None
        if flow_missing:
            return ChartFlowCue(
                action="관망",
                why="수급 데이터 없음. 차트만으로 Review하세요.",
                alignment="single",
                tone="muted",
                chart_stance=cs,
                flow_stance="unknown",
                chart_text=chart_text,
                flow_text="데이터 없음",
                flow_signal=sig,
                foreign_5d="—",
                institution_5d="—",
            )

    # --- conflict / soften matrix ---
    if cs == "bull" and fs == "bull":
        action, why, tone = "보유·소량만", "차트·수급이 같은 방향입니다. 추격 말고 소량·사다리만 Review.", "ok"
    elif cs == "bull" and fs == "bear":
        action, why, tone = (
            "추매금지",
            "차트는 강세이나 수급은 분산입니다. 가격만 보고 더 사지 마세요.",
            "hot",
        )
    elif cs == "bear" and fs == "bull":
        action, why, tone = (
            "관망",
            "수급은 매집이나 차트가 보류·약세입니다. 수급만으로 추격하지 마세요.",
            "warn",
        )
    elif cs == "bear" and fs == "bear":
        action, why, tone = (
            "축소·교체 검토",
            "차트·수급이 모두 약합니다. 줄이기·교체만 Review하세요.",
            "warn",
        )
    elif cs == "bull" and fs in {"neutral", "unknown"}:
        action, why, tone = "보유·관망", "차트는 우호적이나 수급 확인이 약합니다. 추격은 보류.", "ok"
    elif cs == "bear" and fs in {"neutral", "unknown"}:
        action, why, tone = "추가금지", "차트가 매수 보류·약세입니다. 수급과 무관하게 추매하지 마세요.", "hot"
    elif cs in {"neutral", "unknown"} and fs == "bull":
        action, why, tone = "관망", "수급 매집만으로는 매수 근거가 부족합니다. 차트 확인 후 Review.", "muted"
    elif cs in {"neutral", "unknown"} and fs == "bear":
        action, why, tone = "축소 검토", "수급 분산입니다. 차트와 맞춰 비중 축소를 Review하세요.", "warn"
    else:
        action, why, tone = "관망", "차트·수급을 함께 본 뒤 Review하세요. 자동매매 없음.", "muted"

    if chart_why and action in {"추매금지", "관망", "추가금지"}:
        why = f"{why} {chart_why}".strip()

    if align == "conflict":
        tone = "hot" if tone == "ok" else tone

    return ChartFlowCue(
        action=action,
        why=why,
        alignment=align,
        tone=tone,
        chart_stance=cs,
        flow_stance=fs,
        chart_text=chart_text,
        flow_text=flow_text,
        flow_signal=sig if not flow_missing else "STALE",
        foreign_5d=f5 if not flow_missing else "—",
        institution_5d=i5 if not flow_missing else "—",
    )


def chart_flow_strip_html(cue: ChartFlowCue) -> str:
    """Today condition card — same shell as 운영/모멘텀, quieter (rank 3)."""
    align_ko = {
        "align": "일치",
        "conflict": "충돌",
        "partial": "부분",
        "single": "한쪽",
    }.get(cue.alignment, "")
    align_html = (
        f'<span class="pf-review-chip">{escape(align_ko)}</span>' if align_ko else ""
    )
    return (
        f'<div class="pf-review-card pf-review-3 pf-cf-{escape(cue.tone)}" '
        f'title="3순위 · 오늘 컨디션(차트·수급) · 운영을 뒤집지 않음">'
        f'<div class="pf-review-top">'
        f'<span class="pf-review-kicker">3 · 지금</span>'
        f'<span class="pf-review-hint">오늘 컨디션</span>'
        f"{align_html}"
        f"</div>"
        f'<div class="pf-review-main">'
        f'<span class="pf-review-primary">{escape(cue.action)}</span>'
        f"</div>"
        f'<div class="pf-review-body">{escape(cue.why)}</div>'
        f'<div class="pf-review-ev">'
        f'<span><b>차트</b> {escape(cue.chart_text)}</span>'
        f'<span><b>수급</b> {escape(cue.flow_text)}</span>'
        f"</div></div>"
    )
