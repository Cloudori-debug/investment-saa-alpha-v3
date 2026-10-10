"""HTML helpers for economy compass page (Review-only display)."""

from __future__ import annotations

from html import escape

from alpha_system.economy_compass.compass import CompassView


def _esc(value: object) -> str:
    return escape(str(value or ""), quote=True)


def sleeves_panel_html(view: CompassView) -> str:
    if not view.sleeves:
        return (
            '<div class="eco-compass-empty">'
            "국면이 없으면 슬리브 밴드를 만들지 않습니다. 다시 계산하세요."
            "</div>"
        )
    cells = []
    for s in view.sleeves:
        act = s.action
        tone = {"늘림": "up", "줄임": "down", "유지": "flat"}.get(act, "flat")
        cells.append(
            f'<div class="eco-sleeve eco-sleeve-{_esc(tone)}">'
            f'<div class="eco-sleeve-k">{_esc(s.label)}</div>'
            f'<div class="eco-sleeve-pct">{s.pct:.0f}%</div>'
            f'<div class="eco-sleeve-act">{_esc(act)}</div>'
            f'<div class="eco-sleeve-why">{_esc(s.why)}</div>'
            f"</div>"
        )
    warn = ""
    if view.regime_warning:
        warn = f'<div class="eco-compass-warn">{_esc(view.regime_warning)}</div>'
    alpha = f'<div class="eco-compass-alpha">{_esc(view.alpha_line)}</div>'
    return (
        f'<div class="eco-compass-block">'
        f"{alpha}{warn}"
        f'<div class="eco-sleeve-grid">{"".join(cells)}</div>'
        f"</div>"
    )


def history_panel_html(view: CompassView) -> str:
    freq = view.frequency
    if not freq.available:
        return (
            '<div class="eco-compass-empty">'
            "유사국면 빈도 표가 없습니다 (단계 미산출 또는 데이터 없음)."
            "</div>"
        )
    rows = []
    for c in freq.cells:
        wr = "—" if c.win_rate is None else f"{c.win_rate:.0f}%"
        mr = "—" if c.median_ret is None else f"{c.median_ret:+.1f}%"
        rows.append(
            "<tr>"
            f"<td>{_esc(c.label)}</td>"
            f"<td class=\"eco-num\">{_esc(wr)}</td>"
            f"<td class=\"eco-num\">{_esc(mr)}</td>"
            f"<td class=\"eco-num\">{c.n_months}</td>"
            "</tr>"
        )
    return (
        '<div class="eco-compass-block">'
        '<table class="eco-hist-table">'
        "<thead><tr>"
        "<th>슬리브</th><th>월 승률</th><th>중앙 수익률</th><th>표본(월)</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f'<div class="eco-hist-note">{_esc(freq.note)}</div>'
        "</div>"
    )


def metric_sleeve_lines_html(view: CompassView) -> str:
    if not view.metric_hints:
        return ""
    bits = []
    for h in view.metric_hints:
        bits.append(
            f'<div class="eco-m-sleeve">'
            f'<span class="eco-m-sleeve-k">{_esc(h.title)} · {_esc(h.stress_label)}</span>'
            f'<span class="eco-m-sleeve-v">{_esc(h.sleeve_implication)}</span>'
            f"</div>"
        )
    return f'<div class="eco-m-sleeve-list">{"".join(bits)}</div>'
