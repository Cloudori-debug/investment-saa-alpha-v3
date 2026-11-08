"""Shadow attribution report + portfolio card HTML (Review-only)."""

from __future__ import annotations

from html import escape
from typing import Any

from alpha_system.shadow.mid_ledger import summarize_ledger
from src.backtest.cost_model import sample_quality_banner


def attribution_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = ("exit_full", "cash_half", "trim", "add_ready", "add_wait", "hold_drift")
    out = {k: 0.0 for k in keys}
    for r in rows:
        attr = r.get("attribution") or {}
        if not isinstance(attr, dict):
            continue
        for k in keys:
            try:
                out[k] += float(attr.get(k) or 0.0)
            except (TypeError, ValueError):
                pass
    return {k: round(v, 8) for k, v in out.items()}


def shadow_report_dict(
    rows: list[dict[str, Any]],
    *,
    rotation_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary = summarize_ledger(rows)
    summary["attribution"] = attribution_totals(rows)
    summary["banner"] = sample_quality_banner(str(summary.get("quality") or "insufficient"))
    summary["review_only"] = True
    summary["writes_target"] = False
    # Recent rebalance events (last 3 days with events)
    recent: list[dict[str, Any]] = []
    for r in reversed(rows):
        ev = r.get("events") or []
        if not ev:
            continue
        recent.append(
            {
                "as_of": r.get("as_of"),
                "n_events": len(ev),
                "net_ret": r.get("net_ret"),
                "kinds": sorted({str(e.get("kind")) for e in ev if isinstance(e, dict)}),
            }
        )
        if len(recent) >= 3:
            break
    summary["recent_rebals"] = list(reversed(recent))
    if rotation_events is not None:
        from alpha_system.shadow.rotation_coverage import summarize_rotation

        summary["rotation"] = summarize_rotation(rotation_events)
    return summary


def _pct(x: float) -> str:
    return f"{100.0 * float(x):+.2f}%"


def shadow_card_html(report: dict[str, Any] | None) -> str:
    if not report or int(report.get("n_days") or 0) <= 0:
        return (
            '<div class="pf-wact-board pf-wact-board-empty">'
            '<div class="pf-wact-head">'
            '<div class="pf-wact-title">Shadow</div>'
            '<div class="pf-wact-legend">기록 없음 · Review-only</div>'
            "</div></div>"
        )
    n = int(report.get("n_days") or 0)
    net = _pct(float(report.get("total_net_ret") or 0.0))
    vs_m = _pct(float(report.get("vs_market") or 0.0))
    vs_e = _pct(float(report.get("vs_ew") or 0.0))
    dd = _pct(float(report.get("max_drawdown") or 0.0))
    banner = escape(str(report.get("banner") or ""))
    quality = escape(str(report.get("quality") or ""))
    first = escape(str(report.get("as_of_first") or ""))
    last = escape(str(report.get("as_of_last") or ""))
    attr = report.get("attribution") or {}
    attr_bits = []
    for k, label in (
        ("hold_drift", "보유드리프트"),
        ("add_ready", "추가"),
        ("trim", "줄이기"),
        ("cash_half", "환금"),
        ("exit_full", "전량"),
        ("add_wait", "추가보류"),
    ):
        try:
            v = float(attr.get(k) or 0.0)
        except (TypeError, ValueError):
            v = 0.0
        if abs(v) < 1e-8 and k != "hold_drift":
            continue
        attr_bits.append(f"{label} {v:+.3f}")
    attr_s = escape(" · ".join(attr_bits) if attr_bits else "—")
    recent = report.get("recent_rebals") or []
    recent_s = ""
    if recent:
        parts = []
        for r in recent:
            kinds = ",".join(r.get("kinds") or []) or "—"
            parts.append(f"{escape(str(r.get('as_of') or ''))} ({escape(kinds)})")
        recent_s = " · ".join(parts)

    rot = report.get("rotation") or {}
    rot_s = ""
    n_sell = int(rot.get("n_sell_days") or 0) if isinstance(rot, dict) else 0
    if n_sell > 0:
        def _rp(x: object) -> str:
            if x is None:
                return "—"
            try:
                return f"{100.0 * float(x):.0f}%"
            except (TypeError, ValueError):
                return "—"

        rot_s = (
            f"순환 P1 {_rp(rot.get('p1_hat'))} · P2 {_rp(rot.get('p2_hat'))} "
            f"· 매도일 {n_sell}"
        )

    legend = f"{quality} · {first}→{last} · {n}일 · Review-only"
    if banner:
        legend = f"{banner} · {legend}"
    metrics = f"Net {escape(net)} · vs시장 {escape(vs_m)} · vsEW {escape(vs_e)} · MDD {escape(dd)}"
    foot_bits = []
    if attr_s and attr_s != "—":
        foot_bits.append(f"기여 {attr_s}")
    if recent_s:
        foot_bits.append(f"리밸 {recent_s}")
    if rot_s:
        foot_bits.append(rot_s)
    foot = escape(" · ".join(foot_bits)) if foot_bits else ""

    return (
        '<div class="pf-wact-board">'
        '<div class="pf-wact-head">'
        '<div class="pf-wact-title">Shadow</div>'
        f'<div class="pf-wact-legend">{escape(legend)}</div>'
        "</div>"
        f'<div class="pf-wact-board-body" style="font-weight:700;color:var(--saa-fg)">{metrics}</div>'
        + (f'<div class="pf-wact-board-hint" style="margin-top:0.2rem">{foot}</div>' if foot else "")
        + "</div>"
    )
