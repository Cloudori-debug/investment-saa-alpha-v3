"""OpenDART evidence + gate board — table layout (Review-only).

No score blend, no target writes.
"""

from __future__ import annotations

from html import escape
from typing import Any, Mapping, Sequence

from alpha_system.sizing.qual_overlay import GATE_REASON_KO
from alpha_system.ui.services.dart_evidence import (
    DATA_STATUS_LABEL,
    KIND_LABEL,
    STATUS_LABEL,
    EvidenceEvent,
    TickerEvidence,
)
from alpha_system.ui.services.rank_watchboard import naver_name_chart_html


def _esc(value: object) -> str:
    return escape(str(value or ""), quote=True)


def _fmt_amount(amount_krw: int | None, note: str) -> str:
    if amount_krw is None:
        return note or "—"
    try:
        n = int(amount_krw)
    except (TypeError, ValueError):
        return note or "—"
    if n >= 100_000_000:
        eok = n / 100_000_000
        if abs(eok - round(eok)) < 1e-9:
            return f"{int(round(eok)):,}억"
        return f"{eok:,.1f}억"
    if n >= 10_000:
        return f"{n / 10_000:,.0f}만"
    return f"{n:,}원"


def _amount_display(ev: EvidenceEvent) -> str:
    """Format amount; DPS notes read as 1주당 N원."""
    if ev.amount_krw is None:
        return "—"
    note = ev.amount_note or ""
    if "1주당" in note:
        return f"1주당 {int(ev.amount_krw):,}원"
    return _fmt_amount(ev.amount_krw, note)


def _amount_cell(ev: EvidenceEvent) -> str:
    """Honest empty labels — do not pretend '미확인' when API was never called."""
    if ev.amount_krw is not None:
        return _amount_display(ev)
    if ev.kind == "div":
        return "—"  # document.xml 미수신 · 증분 갱신
    if ev.kind == "buyback":
        return "—"  # tsstkAqDecsn 미수신 · 증분 갱신 필요
    if ev.kind == "asset_sale":
        return "—"  # tgastTrfDecsn 미수신
    if ev.kind == "cancel":
        return "—"
    return "—"


def _amount_summary(item: TickerEvidence) -> str:
    """One-cell summary for join table."""
    if item.data_status != "ok" or not item.events:
        return "—"
    for ev in item.events:
        if ev.amount_krw is not None:
            kind = KIND_LABEL.get(ev.kind, ev.kind)
            return f"{kind} {_amount_display(ev)}"
    kinds = {e.kind for e in item.events}
    if kinds <= {"div"}:
        return "배당·원문대기"
    if "buyback" in kinds:
        return "자사주·증분갱신"
    return "—"


_VERDICT_KO = {
    "pass_review": "통과",
    "hold": "보류",
    "exclude_review": "제외검토",
    "watch": "관찰",
    "parked": "대기",
}


def _clip_cell(text: object, *, max_len: int = 56) -> str:
    s = str(text or "").strip() or "—"
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def eval_cells_for_ticker(
    *,
    screen_verify: Any | None = None,
    phcvs_row: Any | None = None,
    evidence: TickerEvidence | None = None,
    gate_labels: Sequence[str] | None = None,
    gated: bool = False,
) -> dict[str, str]:
    """Plain-text 판정·심층·공시 for one ticker (watch table / join share)."""
    gates = list(gate_labels or [])
    if gated and "제안제외" not in gates and "제안 제외" not in gates:
        gates.append("제안제외")
    gate_cell = ", ".join(gates) if gates else "—"

    if screen_verify is not None:
        warn_list = list(getattr(screen_verify, "warn_tags", None) or [])
        note = str(getattr(screen_verify, "verdict_note", "") or "")
        deep_cell = note or (", ".join(warn_list) if warn_list else "—")
        v_key = str(getattr(screen_verify, "verdict", "") or "watch")
    elif phcvs_row is not None:
        from alpha_system.ui.services.phcvs_watch_board import phcvs_warn_tags

        warn_list = phcvs_warn_tags(phcvs_row)
        deep_cell = str(getattr(phcvs_row, "phcvs_status", "") or "—")
        if warn_list:
            deep_cell = f"{deep_cell} · " + ", ".join(warn_list)
        v_key = "watch"
    else:
        deep_cell = "—"
        v_key = "watch"

    headline = (
        evidence.headline
        if evidence is not None and evidence.data_status == "ok"
        else "—"
    )
    amt = _amount_summary(evidence) if evidence is not None else "—"
    pub_bits: list[str] = []
    if headline and headline != "—":
        pub_bits.append(headline)
    if amt and amt != "—":
        pub_bits.append(amt)
    if gate_cell and gate_cell != "—":
        pub_bits.append(gate_cell)
    pub_cell = " · ".join(pub_bits) if pub_bits else "—"

    return {
        "판정": _VERDICT_KO.get(v_key, "관찰"),
        "심층": _clip_cell(deep_cell),
        "공시": _clip_cell(pub_cell),
        "verdict_key": v_key,
    }


def build_watch_eval_map(
    tickers: Sequence[str],
    *,
    screen_verify_rows: Sequence[Any] | None = None,
    board: Sequence[TickerEvidence] | None = None,
    flags: Sequence[Any] | None = None,
    gated: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    """Cache-only enrichment for ② 후보 rows: 판정 / 심층 / 공시."""
    gated_set = {
        (str(t).zfill(6) if str(t).isdigit() else str(t)) for t in (gated or set())
    }
    sv_map: dict[str, Any] = {}
    for pr in screen_verify_rows or ():
        tk = str(getattr(pr, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        if tk:
            sv_map[tk] = pr
    ev_by = {b.ticker: b for b in (board or ()) if getattr(b, "ticker", None)}
    flag_by: dict[str, list[str]] = {}
    for item in flags or ():
        tk = str(getattr(item, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        kind = str(getattr(item, "kind", "") or "")
        label = GATE_REASON_KO.get(kind, kind)
        flag_by.setdefault(tk, []).append(label)

    out: dict[str, dict[str, str]] = {}
    for raw in tickers:
        tk = str(raw).zfill(6) if str(raw).isdigit() else str(raw)
        cells = eval_cells_for_ticker(
            screen_verify=sv_map.get(tk),
            evidence=ev_by.get(tk),
            gate_labels=flag_by.get(tk),
            gated=tk in gated_set,
        )
        out[tk] = {
            "판정": cells["판정"],
            "심층": cells["심층"],
            "공시": cells["공시"],
        }
    return out


def _status_chip(status: str) -> str:
    tone = {
        "withdrawn": "hot",
        "completed": "ok",
        "in_progress": "warn",
        "resolved": "ok",
        "review": "muted",
        "unknown": "muted",
    }.get(status, "muted")
    label = STATUS_LABEL.get(status, status)
    return f'<span class="pf-od-chip pf-od-chip-{tone}">{_esc(label)}</span>'


def _kind_chip(kind: str) -> str:
    label = KIND_LABEL.get(kind, kind)
    return f'<span class="pf-od-chip pf-od-chip-kind">{_esc(label)}</span>'


def _data_chip(data_status: str) -> str:
    tone = {
        "ok": "ok",
        "no_events": "muted",
        "fetch_error": "hot",
        "missing_key": "hot",
        "no_corp": "warn",
        "stale": "warn",
    }.get(data_status, "muted")
    label = DATA_STATUS_LABEL.get(data_status, data_status)
    return f'<span class="pf-od-chip pf-od-chip-{tone}">{_esc(label)}</span>'


def parse_evidence_board(raw: Sequence[Mapping[str, Any]] | None) -> list[TickerEvidence]:
    board: list[TickerEvidence] = []
    for item in raw or ():
        if not isinstance(item, dict):
            continue
        events: list[EvidenceEvent] = []
        for ev in item.get("events") or []:
            if not isinstance(ev, dict):
                continue
            try:
                raw_amt = ev.get("amount_krw")
                amt = int(raw_amt) if raw_amt is not None else None
            except (TypeError, ValueError):
                amt = None
            try:
                events.append(
                    EvidenceEvent(
                        kind=str(ev.get("kind") or ""),
                        status=str(ev.get("status") or ""),
                        date=str(ev.get("date") or ""),
                        title=str(ev.get("title") or ""),
                        rcept_no=str(ev.get("rcept_no") or ""),
                        source_url=str(ev.get("source_url") or ""),
                        amount_krw=amt,
                        amount_note=str(ev.get("amount_note") or "미확인"),
                        is_correction=bool(ev.get("is_correction")),
                        chain_id=str(ev.get("chain_id") or ""),
                        chain_role=str(ev.get("chain_role") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
        board.append(
            TickerEvidence(
                ticker=str(item.get("ticker") or ""),
                data_status=str(item.get("data_status") or ""),
                data_note=str(item.get("data_note") or ""),
                events=events,
                headline=str(item.get("headline") or ""),
            )
        )
    return board


def opendart_join_html(
    *,
    proposal_rows: Sequence[Any],
    blocked_rows: Sequence[Any],
    scoreboard_rows: Sequence[Any],
    board: Sequence[TickerEvidence],
    flags: Sequence[Any],
    gated: set[str],
    names: Mapping[str, str],
    phcvs_rows: Sequence[Any] | None = None,
    screen_verify_rows: Sequence[Any] | None = None,
) -> str:
    """One glance: QVM ∩ screen deep-verify ∩ OpenDART (Review-only)."""
    from alpha_system.ui.services.phcvs_watch_board import phcvs_warn_tags

    ev_by = {b.ticker: b for b in board if b.ticker}
    sv_map: dict[str, Any] = {}
    for pr in screen_verify_rows or ():
        tk = str(getattr(pr, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        if tk:
            sv_map[tk] = pr
    phcvs_map: dict[str, Any] = {}
    for pr in phcvs_rows or ():
        tk = str(getattr(pr, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        if tk:
            phcvs_map[tk] = pr

    flag_by: dict[str, list[str]] = {}
    for item in flags:
        tk = str(getattr(item, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        kind = str(getattr(item, "kind", "") or "")
        label = GATE_REASON_KO.get(kind, kind)
        flag_by.setdefault(tk, []).append(label)

    score_by: dict[str, tuple[float | None, float | None]] = {}
    for row in scoreboard_rows or ():
        tk = str(getattr(row, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        if not tk:
            continue
        ts = getattr(row, "total_score", None)
        sr = getattr(row, "score_sr", None)
        try:
            ts_f = float(ts) if ts is not None else None
        except (TypeError, ValueError):
            ts_f = None
        try:
            sr_f = float(sr) if sr is not None else None
        except (TypeError, ValueError):
            sr_f = None
        score_by[tk] = (ts_f, sr_f)

    held_phcvs = {
        tk
        for tk, pr in phcvs_map.items()
        if bool(getattr(pr, "in_holdings", False))
    }

    def _book_label(tk: str) -> str:
        for r in proposal_rows or ():
            t = str(getattr(r, "ticker", "") or "")
            if t.isdigit():
                t = t.zfill(6)
            if t == tk:
                return "제안"
        for r in blocked_rows or ():
            t = str(getattr(r, "ticker", "") or "")
            if t.isdigit():
                t = t.zfill(6)
            if t == tk:
                return "대기"
        if tk in held_phcvs:
            return "보유"
        if tk in sv_map:
            return str(getattr(sv_map[tk], "book", None) or "관찰")
        if tk in phcvs_map:
            return "리포트추적"
        return "관찰"

    # Prefer proposal → blocked → screen verify → evidence → report PH-CVS
    seen: set[str] = set()
    ordered: list[str] = []
    for group in (proposal_rows, blocked_rows):
        for r in group or ():
            tk = str(getattr(r, "ticker", "") or "")
            if tk.isdigit():
                tk = tk.zfill(6)
            if tk and tk not in seen:
                seen.add(tk)
                ordered.append(tk)
    for tk in sv_map:
        if tk not in seen:
            seen.add(tk)
            ordered.append(tk)
    for b in board:
        if b.ticker and b.ticker not in seen and (
            b.data_status == "ok" and b.events
        ):
            seen.add(b.ticker)
            ordered.append(b.ticker)
    for tk, pr in phcvs_map.items():
        if tk in seen:
            continue
        warns = phcvs_warn_tags(pr) if hasattr(pr, "phcvs_status") else []
        if warns or getattr(pr, "in_holdings", False) or getattr(pr, "in_proposal", False):
            seen.add(tk)
            ordered.append(tk)

    _verdict_ko = {
        "pass_review": ("통과", "ok"),
        "hold": ("보류", "warn"),
        "exclude_review": ("제외검토", "hot"),
        "watch": ("관찰", "muted"),
        "parked": ("대기", "warn"),
    }
    _v_pri = {
        "exclude_review": 0,
        "hold": 1,
        "pass_review": 2,
        "parked": 3,
        "watch": 4,
    }

    def _sort_key(tk: str) -> tuple:
        book = _book_label(tk)
        pri = {
            "제안": 0,
            "대기": 1,
            "보유": 2,
            "관찰": 3,
            "리포트추적": 4,
        }.get(book, 5)
        sv = sv_map.get(tk)
        vp = _v_pri.get(str(getattr(sv, "verdict", "") or ""), 9)
        sc = score_by.get(tk, (None, None))[0]
        return (pri, vp, sc is None, -(sc or 0), tk)

    ordered.sort(key=_sort_key)

    rows_html: list[str] = []
    for tk in ordered:
        name = names.get(tk, tk)
        sv = sv_map.get(tk)
        ph = phcvs_map.get(tk)
        if sv is not None and getattr(sv, "name", None):
            name = str(sv.name) or name
        elif ph is not None and getattr(ph, "name", None):
            name = str(ph.name) or name
        ts, sr = score_by.get(tk, (None, None))
        book = _book_label(tk)
        ev = ev_by.get(tk)
        headline = ev.headline if ev and ev.data_status == "ok" else "—"
        amt = _amount_summary(ev) if ev else "—"
        gates = list(flag_by.get(tk) or [])
        if tk in gated and "제안 제외" not in gates:
            gates.append("제안제외")
        gate_cell = ", ".join(gates) if gates else "—"
        if sv is not None:
            warn_list = list(getattr(sv, "warn_tags", None) or [])
            note = str(getattr(sv, "verdict_note", "") or "")
            deep_cell = note or (", ".join(warn_list) if warn_list else "—")
            v_key = str(getattr(sv, "verdict", "") or "watch")
        elif ph is not None:
            warn_list = phcvs_warn_tags(ph)
            deep_cell = str(getattr(ph, "phcvs_status", "") or "—")
            if warn_list:
                deep_cell = f"{deep_cell} · " + ", ".join(warn_list)
            v_key = "watch"
        else:
            warn_list = []
            deep_cell = "—"
            v_key = "watch"
        # Merge 공시 + 금액 + 게이트 into one cell
        pub_bits = []
        if headline and headline != "—":
            pub_bits.append(headline)
        if amt and amt != "—":
            pub_bits.append(amt)
        if gate_cell and gate_cell != "—":
            pub_bits.append(gate_cell)
        pub_cell = " · ".join(pub_bits) if pub_bits else "—"
        v_lab, v_tone = _verdict_ko.get(v_key, ("관찰", "muted"))
        book_chip = {
            "제안": "ok",
            "대기": "warn",
            "보유": "ok",
            "관찰": "muted",
            "리포트추적": "warn",
        }.get(book, "muted")
        row_cls = (
            "pf-od-row-hot"
            if v_key == "exclude_review"
            else ("pf-od-row-warn" if v_key == "hold" or warn_list else "")
        )
        ts_s = f"{ts:.1f}" if ts is not None else "—"
        sr_s = f"{sr:.0f}" if sr is not None else "—"
        rows_html.append(
            f'<tr class="{row_cls}">'
            f"<td>{naver_name_chart_html(tk, name)}</td>"
            f'<td class="pf-od-num">{_esc(ts_s)}</td>'
            f'<td class="pf-od-num">{_esc(sr_s)}</td>'
            f"<td><span class=\"pf-od-chip pf-od-chip-{book_chip}\">{_esc(book)}</span></td>"
            f"<td><span class=\"pf-od-chip pf-od-chip-{v_tone}\">{_esc(v_lab)}</span></td>"
            f'<td class="pf-od-note">{_esc(deep_cell)}</td>'
            f'<td class="pf-od-note">{_esc(pub_cell)}</td>'
            "</tr>"
        )

    if not rows_html:
        return (
            '<div class="pf-od-empty">'
            "접목할 제안·심층검증·증거가 없습니다. 정량 갱신 후 「증분 갱신」·"
            "「심층 다시 그리기」를 누르세요."
            "</div>"
        )

    return (
        f'<div class="pf-od-section">'
        f'<div class="pf-od-section-title">한눈 · 점수 × 판정 × 심층·공시</div>'
        f'<div class="pf-od-table-wrap">'
        f'<table class="pf-od-table">'
        "<thead><tr>"
        "<th>종목</th><th>점수</th><th>SR</th><th>장부</th><th>판정</th>"
        "<th>심층·사유</th><th>공시·게이트</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        f"</table></div>"
        f'<div class="pf-od-foot">'
        "점수=정량 · 판정·심층=자동검증 · 공시=watch · 자동편입·target 없음"
        f"</div>"
        f"</div>"
    )


def opendart_toolbar_html(
    *,
    quota_line: str,
    stale: bool,
    as_of: str = "",
    fetched_at: str = "",
    gate_mode_on: bool = False,
) -> str:
    meta_bits = []
    if as_of:
        meta_bits.append(f"기준 {_esc(as_of)}")
    if fetched_at:
        meta_bits.append(f"갱신 {_esc(fetched_at[:16])}")
    meta_bits.append("게이트 ON" if gate_mode_on else "게이트 OFF·표시만")
    stale_html = (
        '<div class="pf-od-attn pf-od-attn-warn">'
        '<div class="pf-od-attn-title">캐시 만료 · 자동 재호출 없음</div>'
        '<div class="pf-od-attn-body">일일 한도 보호 · 「증분 갱신」만 네트워크를 칩니다.</div>'
        "</div>"
        if stale
        else ""
    )
    return (
        f'<div class="pf-od-block">'
        f'<div class="pf-od-kicker">OpenDART 증거 · Review-only</div>'
        f'<div class="pf-od-meta">{" · ".join(meta_bits)}</div>'
        f'<div class="pf-od-quota">{_esc(quota_line)}</div>'
        f"{stale_html}"
        f"</div>"
    )


def opendart_gates_html(
    flags: Sequence[Any],
    *,
    names: Mapping[str, str],
    gated: set[str],
) -> str:
    if not flags:
        return ""
    rows = []
    for item in flags:
        tk = str(getattr(item, "ticker", "") or "").zfill(6)
        kind = str(getattr(item, "kind", "") or "")
        note = str(getattr(item, "note", "") or "")
        url = str(getattr(item, "source_url", "") or "")
        name = names.get(tk, tk)
        label = GATE_REASON_KO.get(kind, kind)
        excluded = tk in gated
        mark = "제안 제외" if excluded else "탐색"
        row_cls = "pf-od-row-hot" if (kind == "control_purpose" or excluded) else ""
        link = (
            f'<a class="pf-od-link" href="{_esc(url)}" target="_blank" '
            f'rel="noopener">공시</a>'
            if url
            else "—"
        )
        rows.append(
            f'<tr class="{row_cls}">'
            f"<td>{naver_name_chart_html(tk, name)}</td>"
            f"<td>{_esc(label)}</td>"
            f"<td>{_esc(mark)}</td>"
            f'<td class="pf-od-note">{_esc(note)}</td>'
            f"<td>{link}</td>"
            f"</tr>"
        )
    return (
        f'<div class="pf-od-section">'
        f'<div class="pf-od-section-title">게이트 메모 · {len(flags)}건</div>'
        f'<div class="pf-od-hint">경영참여·연기금 → 제안 제외 · 점수·target 불변</div>'
        f'<div class="pf-od-table-wrap">'
        f'<table class="pf-od-table">'
        "<thead><tr>"
        "<th>종목</th><th>사유</th><th>처리</th><th>메모</th><th>공시</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table></div></div>"
    )


def opendart_evidence_html(
    board: Sequence[TickerEvidence],
    *,
    names: Mapping[str, str],
    withdrawn_tickers: Sequence[str] | None = None,
    ab: Mapping[str, Any] | None = None,
    gate_mode_on: bool = False,
    show_attn: bool = True,
) -> str:
    withdrawn = {
        str(t).zfill(6) if str(t).isdigit() else str(t)
        for t in (withdrawn_tickers or ())
    }
    with_ev = [b for b in board if b.data_status == "ok" and b.events]
    problems = [
        b
        for b in board
        if b.data_status in {"fetch_error", "missing_key", "no_corp"}
    ]
    if not with_ev and not problems:
        return (
            '<div class="pf-od-empty">'
            "가치실현 증거가 없습니다. 「증분 갱신」으로 관찰 풀 공시를 모으세요. "
            "QVM 점수는 바꾸지 않습니다."
            "</div>"
        )

    attn = ""
    if show_attn and withdrawn:
        names_line = ", ".join(
            f"{_esc(names.get(tk, tk))}({_esc(tk)})" for tk in sorted(withdrawn)
        )
        attn = (
            f'<div class="pf-od-attn pf-od-attn-hot">'
            f'<div class="pf-od-attn-title">지금 볼 것 · 철회 {len(withdrawn)}종</div>'
            f'<div class="pf-od-attn-body">{names_line}</div>'
            f'<div class="pf-od-attn-note">'
            f'게이트 {"ON·제외 적용" if gate_mode_on else "OFF·표시만"} · 점수 불변'
            f"</div></div>"
        )

    rows: list[str] = []
    # One row per event; withdrawn tickers first
    ordered = sorted(
        with_ev,
        key=lambda b: (0 if b.ticker in withdrawn else 1, b.ticker),
    )
    for item in ordered:
        name = names.get(item.ticker, item.ticker)
        name_cell = naver_name_chart_html(item.ticker, name)
        hot = item.ticker in withdrawn
        for i, ev in enumerate(item.events[:6]):
            row_cls = "pf-od-row-hot" if hot else ""
            amt = _amount_cell(ev)
            link = (
                f'<a class="pf-od-link" href="{_esc(ev.source_url)}" '
                f'target="_blank" rel="noopener">공시</a>'
                if ev.source_url
                else "—"
            )
            # Show name only on first event row of ticker
            name_td = name_cell if i == 0 else '<span class="pf-od-cont">↳</span>'
            chain_td = _esc(item.headline) if i == 0 else ""
            flag = ""
            if hot and i == 0:
                flag = '<span class="pf-od-chip pf-od-chip-hot">철회</span> '
            rows.append(
                f'<tr class="{row_cls}">'
                f"<td>{name_td}</td>"
                f"<td>{flag}{chain_td}</td>"
                f'<td class="pf-od-num">{_esc(ev.date)}</td>'
                f"<td>{_kind_chip(ev.kind)}</td>"
                f"<td>{_status_chip(ev.status)}</td>"
                f'<td class="pf-od-num">{_esc(amt)}</td>'
                f'<td class="pf-od-note">{_esc(ev.title)}</td>'
                f"<td>{link}</td>"
                f"</tr>"
            )
        if len(item.events) > 6:
            rows.append(
                f"<tr><td></td><td colspan=\"7\" class=\"pf-od-more\">"
                f"외 {len(item.events) - 6}건</td></tr>"
            )

    for item in problems:
        name = names.get(item.ticker, item.ticker)
        rows.append(
            f'<tr class="pf-od-row-warn">'
            f"<td>{naver_name_chart_html(item.ticker, name)}</td>"
            f"<td colspan=\"2\">{_data_chip(item.data_status)}</td>"
            f'<td colspan="5" class="pf-od-note">'
            f"{_esc(item.data_note or item.headline)}</td>"
            f"</tr>"
        )

    ab_html = ""
    if ab and int(ab.get("n_removed") or 0) > 0:
        ab_html = (
            f'<div class="pf-od-ab">'
            f'<span class="pf-od-ab-lbl">Shadow A/B</span> '
            f"A {_esc(ab.get('n_a'))} → B {_esc(ab.get('n_b'))} "
            f"(철회제외 {_esc(ab.get('n_removed'))}) · "
            f"Δ점수 {_esc(ab.get('mean_score_delta_b_minus_a'))} · DART 0회"
            f"</div>"
        )

    return (
        f'<div class="pf-od-section">'
        f'<div class="pf-od-section-title">'
        f"가치실현 증거 · {len(with_ev)}종"
        f"{f' · 이상 {len(problems)}' if problems else ''}"
        f"</div>"
        f"{attn}"
        f'<div class="pf-od-table-wrap">'
        f'<table class="pf-od-table">'
        "<thead><tr>"
        "<th>종목</th><th>체인</th><th>일자</th><th>종류</th>"
        "<th>상태</th><th>금액</th><th>제목</th><th>공시</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table></div>"
        f"{ab_html}"
        f'<div class="pf-od-foot">Review-only · 자동 편입 없음</div>'
        f"</div>"
    )
