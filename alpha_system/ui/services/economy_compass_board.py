"""HTML helpers for economy compass page (Review-only display)."""

from __future__ import annotations

from dataclasses import replace
from html import escape
from typing import Optional, Sequence

from alpha_system.economy_compass.compass import CompassView
from alpha_system.economy_compass.executable import executable_lines, leg_book_pct
from alpha_system.economy_compass.sleeves import (
    SleeveBand,
    alpha_envelope_line,
    sleeve_bands_for_stage,
)
from alpha_system.economy_compass.fear_greed_soft import FearGreedSoftBoard
from alpha_system.economy_compass.marks_continuum import (
    MarksContinuumBoard,
    marks_continuum_rail_html,
)
from alpha_system.economy_compass.mean_reversion_review import MeanReversionBoard
from alpha_system.economy_compass.stress_overlay import BubbleStressBoard
from alpha_system.economy_signal import EconomySignal, envelope_policy

# Forest risk horizon — operator framing only (not Core / target / YouTube feed).
_RISK_POINTS: tuple[tuple[str, str], ...] = (
    (
        "시총 ≠ 현금",
        "시가총액은 청산가가 아닙니다. 테마·레버리지 추격을 줄이고 유동성 있는 노른자만.",
    ),
    (
        "주식·국채 동시약세",
        "둘 다 빠질 수 있습니다. 국채 한 종목 헤지 과신 금지 · 짧은 듀레이션·현금·금 분산.",
    ),
    (
        "취약 구간 가설",
        "중간선거 후~대선 전은 정치·세금·부채가 겹칠 수 있는 구간. 달력으로 자동매매하지 않음.",
    ),
    (
        "금리 · 연준",
        "금리 경로·신뢰는 나침반 입력으로만 봅니다. 시황 한마디로 비중을 바꾸지 않습니다.",
    ),
)


def _esc(value: object) -> str:
    return escape(str(value or ""), quote=True)


def _sleeve_tone(action: str) -> str:
    return {"늘림": "up", "줄임": "down", "유지": "flat"}.get(action, "flat")


def asset_move_board_html(
    *,
    signal: EconomySignal | None,
    compass: CompassView,
    playbook_title: str,
    playbook_tone: str,
    action_lines: Sequence[tuple[str, str]],
    posture_stage: int | None = None,
    stage_for_posture: int | None = None,
    scoreline: str = "",
    fetched_at: str = "",
) -> str:
    """결론: 자산이 어떻게 움직이는지 (알파 봉투 + 숲 슬리브 방향)."""
    from alpha_system.ui.services.economy_display import format_fetched_at, hero_copy

    if signal is None:
        return (
            '<div class="eco-verdict eco-verdict-off">'
            '<div class="eco-verdict-kicker">결론 · 자산 움직임</div>'
            '<div class="eco-verdict-title">아직 국면 없음</div>'
            '<div class="eco-verdict-scope">'
            "다시 계산 후 알파 장부·숲 슬리브 방향이 나옵니다 · "
            "가계 전체 SAA 비중은 이 화면이 아닙니다"
            "</div>"
            "</div>"
        )

    hero = hero_copy(signal)
    when = fetched_at or format_fetched_at(getattr(signal, "fetched_at", None) or "")
    moves = "".join(
        f'<div class="eco-move eco-move-{_esc(_sleeve_tone(s.action))}">'
        f'<span class="eco-move-lab">{_esc(s.label)}</span>'
        f'<span class="eco-move-pct">{s.pct:.0f}%</span>'
        f'<span class="eco-move-act">{_esc(s.action)}</span>'
        f"</div>"
        for s in (compass.sleeves or ())
    )
    if not moves:
        moves = '<div class="eco-move-empty">숲 슬리브 미산출</div>'
    actions = "".join(
        f'<div class="eco-verdict-act">'
        f'<span class="eco-verdict-act-lab">{_esc(lab)}</span>'
        f'<span class="eco-verdict-act-body">{_esc(body)}</span>'
        f"</div>"
        for lab, body in action_lines[:3]
    )
    posture = ""
    if posture_stage is not None:
        stage_s = "—" if stage_for_posture is None else str(stage_for_posture)
        posture = (
            f'<div class="eco-posture-chip">'
            f'<span class="eco-posture-k">자세권고</span>'
            f'<span class="eco-posture-v">{int(posture_stage)}단계</span>'
            f'<span class="eco-posture-sub">국면 {_esc(stage_s)}</span>'
            f"</div>"
        )
    meta_bits = [b for b in (scoreline, f"계산 {when}" if when else "") if b]
    meta = (
        f'<p class="eco-when">{_esc(" · ".join(meta_bits))}</p>' if meta_bits else ""
    )
    tone = playbook_tone or "wait"
    warn = ""
    if compass.regime_warning:
        warn = f'<div class="eco-compass-warn">{_esc(compass.regime_warning)}</div>'
    return (
        f'<div class="eco-verdict eco-verdict-{_esc(tone)}">'
        '<div class="eco-verdict-kicker">결론 · 자산 움직임</div>'
        f'<div class="eco-verdict-title">{_esc(hero.get("kicker") or "")} · '
        f'{_esc(hero.get("title") or playbook_title)}</div>'
        '<div class="eco-verdict-scope">'
        "알파 장부(개별주/단기채) + 숲 슬리브 방향 · "
        "가계 전체 SAA·자동주문 아님 · 한국 개별주는 포트폴리오"
        "</div>"
        f"{posture}"
        '<div class="eco-move-block">'
        '<div class="eco-move-h">알파 장부</div>'
        '<div class="eco-split eco-split-tight">'
        f'<div><span class="eco-pct">{_esc(hero.get("equity") or "")}</span>'
        '<span class="eco-pct-label">개별주</span></div>'
        f'<div><span class="eco-pct">{_esc(hero.get("cash") or "")}</span>'
        '<span class="eco-pct-label">단기채</span></div>'
        "</div>"
        f'<div class="eco-move-h">숲 슬리브</div>'
        f'<div class="eco-move-grid">{moves}</div>'
        "</div>"
        f'<div class="eco-verdict-do">'
        f'<div class="eco-verdict-do-h">{_esc(playbook_title)}</div>'
        f"{actions}"
        "</div>"
        f"{warn}{meta}"
        "</div>"
    )


def why_drivers_html(
    *,
    stress: BubbleStressBoard | None,
    mean_rev: MeanReversionBoard | None,
    scoreline: str = "",
    marks: MarksContinuumBoard | None = None,
) -> str:
    """결론 아래: 왜 그렇게 됐는지 — 중복 없이 핵심 지표만."""
    rows: list[str] = []
    marks_block = ""
    if marks is not None:
        marks_block = (
            '<div class="eco-why-marks">'
            f"{marks_continuum_rail_html(marks, compact=True)}"
            "</div>"
        )
    if scoreline:
        rows.append(
            f'<div class="eco-why-row eco-why-span">'
            f'<span class="eco-why-k">국면</span>'
            f'<span class="eco-why-v">{_esc(scoreline)}</span>'
            f"</div>"
        )
    if stress is not None:
        # Material first: hot → watch → skip plain ok/missing fluff unless all ok
        material = [i for i in stress.items if i.status in {"hot", "watch"}]
        if not material:
            material = [i for i in stress.items if i.status == "ok"][:2]
        for item in material:
            rows.append(
                f'<div class="eco-why-row eco-why-{_esc(item.status)}">'
                f'<span class="eco-why-k">{_esc(item.label)}</span>'
                f'<span class="eco-why-chip">{_esc(item.status_ko)}</span>'
                f'<span class="eco-why-v">{_esc(item.detail)}</span>'
                f"</div>"
            )
        if stress.elevated and stress.posture_stage is not None:
            rows.append(
                f'<div class="eco-why-row eco-why-span eco-why-hot">'
                f'<span class="eco-why-k">자세</span>'
                f'<span class="eco-why-v">위험 칸 {int(stress.hot_count)} · '
                f"자세권고 {int(stress.posture_stage)}단계</span>"
                f"</div>"
            )
        elif stress.hot_count:
            rows.append(
                f'<div class="eco-why-row eco-why-span">'
                f'<span class="eco-why-k">자세</span>'
                f'<span class="eco-why-v">위험 칸 {int(stress.hot_count)} · 국면 유지</span>'
                f"</div>"
            )
    if mean_rev is not None:
        for key in ("real_rate", "kr_value", "vix_soft", "kospi_dd", "contrarian_rebal"):
            item = next((i for i in mean_rev.items if i.key == key), None)
            if item is None:
                continue
            # Soft fear rows: only when watch/hot (avoid clutter in calm)
            if key in {"vix_soft", "kospi_dd", "contrarian_rebal"} and item.status not in {
                "watch",
                "hot",
            }:
                continue
            rows.append(
                f'<div class="eco-why-row eco-why-{_esc(item.status)}">'
                f'<span class="eco-why-k">{_esc(item.label)}</span>'
                f'<span class="eco-why-chip">{_esc(item.status_ko)}</span>'
                f'<span class="eco-why-v">{_esc(item.detail)}</span>'
                f"</div>"
            )
        if mean_rev.sleeve_note:
            rows.append(
                f'<div class="eco-why-row eco-why-span">'
                f'<span class="eco-why-k">함의</span>'
                f'<span class="eco-why-v">{_esc(mean_rev.sleeve_note)}</span>'
                f"</div>"
            )
    if not rows:
        rows.append(
            '<div class="eco-why-row eco-why-span">'
            '<span class="eco-why-k">대기</span>'
            '<span class="eco-why-v">지표를 채운 뒤 근거가 붙습니다.</span>'
            "</div>"
        )
    return (
        '<div class="eco-why-board">'
        '<div class="eco-why-board-h">왜 이렇게 · 근거 지표</div>'
        f"{marks_block}"
        f'<div class="eco-why-list">{"".join(rows)}</div>'
        '<div class="eco-why-board-f">'
        "국면(FRED) 산출식 불변 · 순위·target·자동매수 없음"
        "</div>"
        "</div>"
    )


def executable_compact_html(view: CompassView) -> str:
    """ETF 후보를 포트폴리오형 표로 — 결론/근거와 섞지 않음."""
    if not view.sleeves:
        return ""
    picks = {p.sleeve_id: p for p in executable_lines(view.sleeves)}
    rows: list[str] = []
    for s in view.sleeves:
        pick = picks.get(s.sleeve_id)
        if pick is None or not pick.legs:
            continue
        tone = _sleeve_tone(s.action)
        n_legs = len(pick.legs)
        for i, leg in enumerate(pick.legs):
            book = leg_book_pct(s.pct, leg.sleeve_weight_pct)
            sleeve_cells = ""
            if i == 0:
                sleeve_cells = (
                    f'<td class="eco-exec-sleeve" rowspan="{n_legs}">'
                    f'<div class="eco-exec-sleeve-lab">{_esc(s.label)}</div>'
                    f'<div class="eco-exec-sleeve-act eco-move-{_esc(tone)}">'
                    f'{_esc(s.action)} · {s.pct:.0f}%</div>'
                    f"</td>"
                )
            rows.append(
                f'<tr class="eco-exec-row eco-exec-{_esc(tone)}">'
                f"{sleeve_cells}"
                f'<td class="eco-exec-tk eco-num">{_esc(leg.ticker)}</td>'
                f'<td class="eco-exec-name">{_esc(leg.name)}</td>'
                f'<td class="eco-num">{leg.sleeve_weight_pct:.0f}%</td>'
                f'<td class="eco-num">{book:.1f}%</td>'
                f'<td class="eco-exec-note">{_esc(leg.why)}</td>'
                f"</tr>"
            )
    if not rows:
        return ""
    notes = []
    for s in view.sleeves:
        pick = picks.get(s.sleeve_id)
        if pick is not None and pick.compared:
            notes.append(f"{s.label}: {pick.compared}")
    note_html = ""
    if notes:
        note_html = (
            '<div class="eco-exec-table-notes">'
            + "".join(f'<div>{_esc(n)}</div>' for n in notes)
            + "</div>"
        )
    return (
        '<div class="eco-exec-table-wrap">'
        '<table class="eco-exec-table">'
        "<thead><tr>"
        "<th>슬리브</th>"
        "<th>코드</th>"
        "<th>상품</th>"
        "<th>슬리브내</th>"
        "<th>장부≈</th>"
        "<th>메모</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        f"{note_html}"
        '<div class="eco-exec-table-f">'
        "사람만 매매 · 한국 개별주는 포트폴리오 ③ · target 자동기입 없음"
        "</div>"
        "</div>"
    )


def verdict_panel_html(
    *,
    signal: EconomySignal | None,
    playbook_title: str,
    playbook_tone: str,
    action_lines: Sequence[tuple[str, str]],
    regime_warning: str = "",
    posture_stage: int | None = None,
    stage_for_posture: int | None = None,
    scoreline: str = "",
    fetched_at: str = "",
    compass: CompassView | None = None,
) -> str:
    """Back-compat → asset_move_board_html."""
    from alpha_system.economy_compass.compass import build_compass

    view = compass if compass is not None else build_compass(signal)
    if regime_warning and view.regime_warning != regime_warning:
        view = replace(view, regime_warning=regime_warning)
    return asset_move_board_html(
        signal=signal,
        compass=view,
        playbook_title=playbook_title,
        playbook_tone=playbook_tone,
        action_lines=action_lines,
        posture_stage=posture_stage,
        stage_for_posture=stage_for_posture,
        scoreline=scoreline,
        fetched_at=fetched_at,
    )


def stress_board_html(board: BubbleStressBoard) -> str:
    """Live FRED-proxy checklist — Review-only, no stage cache writes."""
    cells: list[str] = []
    for item in board.items:
        cells.append(
            f'<div class="eco-stress-item eco-stress-{_esc(item.status)}">'
            f'<div class="eco-stress-top">'
            f'<span class="eco-stress-label">{_esc(item.label)}</span>'
            f'<span class="eco-stress-chip">{_esc(item.status_ko)}</span>'
            f"</div>"
            f'<div class="eco-stress-detail">{_esc(item.detail)}</div>'
            f"</div>"
        )
    posture_bits: list[str] = []
    for card in board.posture_cards:
        posture_bits.append(
            f'<div class="eco-stress-posture-card">'
            f'<span class="eco-stress-posture-k">{_esc(card.label)}</span>'
            f'<span class="eco-stress-posture-b">{_esc(card.body)}</span>'
            f"</div>"
        )
    posture_html = (
        f'<div class="eco-stress-posture">{"".join(posture_bits)}</div>'
        if posture_bits
        else ""
    )
    elev = ""
    if board.show_posture_chip and board.posture_stage is not None:
        stage_s = "—" if board.stage is None else str(board.stage)
        elev = (
            f'<div class="eco-stress-elev">'
            f"국면 {_esc(stage_s)} · "
            f"<strong>자세권고 {int(board.posture_stage)}</strong>"
            f" · 자동매도·target 없음"
            f"</div>"
        )
    return (
        '<div class="eco-stress">'
        '<div class="eco-stress-head">'
        '<div class="eco-stress-kicker">거품·신용 점검 · Review</div>'
        '<div class="eco-stress-title">지표 상태 · 자세 권고</div>'
        '<div class="eco-stress-sub">'
        f"{_esc(board.source_note)}"
        "</div>"
        "</div>"
        f"{elev}"
        f'<div class="eco-stress-grid">{"".join(cells)}</div>'
        f"{posture_html}"
        '<div class="eco-stress-foot">'
        "국면(FRED)은 그대로 · 위험 칸이 많으면 자세만 상향 표시 · "
        "순위·target·Core 불변"
        "</div>"
        "</div>"
    )


def kospi_valuation_band_html(band) -> str:
    """KOSPI PBR/PER band Review card — stage formula untouched."""
    if band is None:
        return ""
    tone = getattr(band, "tone", "missing") or "missing"
    label = getattr(band, "label_ko", "") or ""
    detail = getattr(band, "detail", "") or ""
    as_of = getattr(band, "as_of", "") or ""
    src = getattr(band, "source", "") or ""
    pbr = getattr(band, "pbr", None)
    pctl = getattr(band, "pbr_pctl", None)
    head_bits = []
    if pbr is not None:
        head_bits.append(f"PBR {float(pbr):.2f}")
    if pctl is not None:
        head_bits.append(f"장기%ile {float(pctl):.0f}")
    head = " · ".join(head_bits) if head_bits else "지표 대기"
    return (
        f'<div class="eco-kval eco-kval-{_esc(tone)}">'
        '<div class="eco-kval-kicker">코스피 밸류 밴드 · Review-only</div>'
        f'<div class="eco-kval-row">'
        f'<span class="eco-kval-head">{_esc(head)}</span>'
        f'<span class="eco-kval-chip">{_esc(label)}</span>'
        f"</div>"
        f'<div class="eco-kval-detail">{_esc(detail)}</div>'
        f'<div class="eco-kval-foot">'
        f"출처: {_esc(src)}"
        + (f" · as_of {_esc(as_of)}" if as_of else "")
        + " · 국면 산출 불변 · 자동매수 없음"
        "</div>"
        "</div>"
    )


def fear_greed_soft_panel_html(board: FearGreedSoftBoard) -> str:
    """CNN Fear&Greed Soft checklist — local proxies only, Review-only."""
    score_txt = "—" if board.soft_score is None else f"{board.soft_score:.0f}"
    cells: list[str] = []
    for leg in board.legs:
        chip = leg.chip or (
            "미수집"
            if leg.status == "missing"
            else (f"{leg.soft_score:.0f}" if leg.soft_score is not None else leg.status)
        )
        cells.append(
            f'<div class="eco-fg-item eco-fg-{_esc(leg.status)}">'
            f'<div class="eco-fg-top">'
            f'<span class="eco-fg-label">{_esc(leg.label)}</span>'
            f'<span class="eco-fg-chip">{_esc(chip)}</span>'
            f"</div>"
            f'<div class="eco-fg-cnn">{_esc(leg.cnn_name)}</div>'
            f'<div class="eco-fg-detail">{_esc(leg.detail)}</div>'
            f"</div>"
        )
    as_of = f" · as_of {_esc(board.as_of)}" if board.as_of else ""
    return (
        f'<div class="eco-fg eco-fg-tone-{_esc(board.tone)}">'
        '<div class="eco-fg-head">'
        '<div class="eco-fg-kicker">Fear &amp; Greed · Soft</div>'
        f'<div class="eco-fg-title">{_esc(board.title)}</div>'
        f'<div class="eco-fg-sub">{_esc(board.source_note)}</div>'
        "</div>"
        f'<div class="eco-fg-scoreline">'
        f'<span class="eco-fg-score">{_esc(score_txt)}</span>'
        f'<span class="eco-fg-zone">{_esc(board.zone_ko)}</span>'
        f'<span class="eco-fg-avail">가용 {int(board.available_n)}/7</span>'
        f"</div>"
        f'<div class="eco-fg-hint">{_esc(board.hint)}</div>'
        f'<div class="eco-fg-grid">{"".join(cells)}</div>'
        f'<div class="eco-fg-foot">'
        f"원본 참고: {_esc(board.cnn_url)}{as_of} · "
        "합산 Soft≠CNN · 국면식·target·자세 불변"
        "</div>"
        "</div>"
    )


def mean_reversion_panel_html(board: MeanReversionBoard) -> str:
    """Hong-style mean-reversion Review — real rates + KR value caution."""
    cells: list[str] = []
    for item in board.items:
        cells.append(
            f'<div class="eco-mrev-item eco-mrev-{_esc(item.status)}">'
            f'<div class="eco-mrev-top">'
            f'<span class="eco-mrev-label">{_esc(item.label)}</span>'
            f'<span class="eco-mrev-chip">{_esc(item.status_ko)}</span>'
            f"</div>"
            f'<div class="eco-mrev-detail">{_esc(item.detail)}</div>'
            f"</div>"
        )
    card_bits: list[str] = []
    for i, card in enumerate(board.cards, start=1):
        card_bits.append(
            f'<div class="eco-mrev-card">'
            f'<span class="eco-mrev-n">{i:02d}</span>'
            f'<div class="eco-mrev-card-lab">{_esc(card.label)}</div>'
            f'<div class="eco-mrev-card-body">{_esc(card.body)}</div>'
            f"</div>"
        )
    note = ""
    if board.sleeve_note:
        note = (
            f'<div class="eco-mrev-sleeve">{_esc(board.sleeve_note)}</div>'
        )
    band_html = kospi_valuation_band_html(getattr(board, "kospi_band", None))
    return (
        f'<div class="eco-mrev eco-mrev-tone-{_esc(board.tone)}">'
        '<div class="eco-mrev-head">'
        '<div class="eco-mrev-kicker">평균회귀·역발상 · Review</div>'
        f'<div class="eco-mrev-title">{_esc(board.title)}</div>'
        f'<div class="eco-mrev-sub">{_esc(board.source_note)}</div>'
        "</div>"
        f"{note}"
        f'<div class="eco-mrev-grid">{"".join(cells)}</div>'
        f"{band_html}"
        f'<div class="eco-mrev-cards">{"".join(card_bits)}</div>'
        '<div class="eco-mrev-foot">'
        "QVM·월 리밸·L3 재진입과 같은 축 · VIX Soft≠자세 가산 · "
        "바닥 타이밍·target 자동기입 없음"
        "</div>"
        "</div>"
    )


def apply_mean_reversion_sleeve_notes(
    compass: CompassView,
    board: MeanReversionBoard,
) -> CompassView:
    """Append mean-reversion note to bond/cash (and equity when rates hot)."""
    note = (board.sleeve_note or "").strip()
    if not note or not compass.sleeves:
        return compass
    out: list[SleeveBand] = []
    for b in compass.sleeves:
        why = b.why
        if b.sleeve_id in {"bonds", "cash"}:
            why = f"{why} · {note}"
        elif b.sleeve_id == "equity" and board.real_score is not None and board.real_score >= 2:
            why = f"{why} · 실질금리↑ · 추격↓ · 밸류·QVM"
        out.append(
            SleeveBand(
                sleeve_id=b.sleeve_id,
                label=b.label,
                pct=b.pct,
                action=b.action,
                why=why,
            )
        )
    return replace(compass, sleeves=tuple(out))


def risk_horizon_panel_html() -> str:
    """Readable forest-risk framing under sleeves — Review-only, no orders."""
    cards: list[str] = []
    for i, (label, body) in enumerate(_RISK_POINTS, start=1):
        cards.append(
            f'<div class="eco-risk-card">'
            f'<span class="eco-risk-n">{i:02d}</span>'
            f'<div class="eco-risk-label">{_esc(label)}</div>'
            f'<div class="eco-risk-body">{_esc(body)}</div>'
            f"</div>"
        )
    return (
        '<div class="eco-risk">'
        '<div class="eco-risk-head">'
        '<div class="eco-risk-kicker">숲 리스크 · 배경 해설</div>'
        '<div class="eco-risk-title">주식·국채가 같이 약해질 수 있음</div>'
        '<div class="eco-risk-sub">'
        "시총 버블 청산 · 상관 붕괴 · 부채·정치 구간 — 배경 해설만 · 자동매도 없음"
        "</div>"
        "</div>"
        f'<div class="eco-risk-grid">{"".join(cards)}</div>'
        '<div class="eco-risk-foot">'
        "시황 채널 아님 · 위 점검판·평균회귀가 자세·슬리브 힌트 · "
        "순위·target·Core 점수 불변 · Executable은 사람만"
        "</div>"
        "</div>"
    )


def compass_with_posture(
    compass: CompassView,
    signal: EconomySignal | None,
    posture_stage: Optional[int],
    *,
    elevated: bool = False,
) -> CompassView:
    """Rebuild sleeve bands for posture_stage; FRED stage cache untouched."""
    if posture_stage is None:
        return compass
    try:
        ps = int(posture_stage)
    except (TypeError, ValueError):
        return compass
    if compass.stage is not None and int(compass.stage) == ps and not elevated:
        return compass
    bands = sleeve_bands_for_stage(ps)
    if elevated:
        bands = [
            SleeveBand(
                sleeve_id=b.sleeve_id,
                label=b.label,
                pct=b.pct,
                action=b.action,
                why=f"{b.why} · 거품·신용 오버레이",
            )
            for b in bands
        ]
    pol = envelope_policy(ps)
    eq = float(pol.equity_share)
    cash = float(pol.cash_share)
    if signal is not None and not elevated:
        eq = float(signal.equity_share)
        cash = float(signal.cash_share)
    line = alpha_envelope_line(ps, eq, cash)
    if elevated:
        line = f"{line} · 자세권고 {ps}"
    warn = compass.regime_warning or ""
    if elevated:
        prefix = "자세 권고 상향 · 거품·신용 오버레이 · "
        warn = prefix + (warn or "자동매도 없음.")
    return replace(
        compass,
        stage=ps,
        stage_label=f"자세권고 {ps}" if elevated else compass.stage_label,
        sleeves=tuple(bands),
        alpha_line=line,
        regime_warning=warn,
    )


def _legs_html(pick) -> str:
    rows: list[str] = []
    for leg in pick.legs:
        book = leg_book_pct(pick.pct, leg.sleeve_weight_pct)
        rows.append(
            f'<div class="eco-exec-leg">'
            f'<div class="eco-exec-leg-top">'
            f'<span class="eco-exec-tk">{_esc(leg.ticker)}</span>'
            f'<span class="eco-exec-leg-name">{_esc(leg.name)}</span>'
            f'<span class="eco-exec-leg-w">{leg.sleeve_weight_pct:.0f}%'
            f'<span class="eco-exec-leg-abs"> · 장부≈{book:.1f}%</span></span>'
            f"</div>"
            f'<div class="eco-exec-why">{_esc(leg.why)}</div>'
            f"</div>"
        )
    return (
        f'<div class="eco-exec-legs">{"".join(rows)}</div>'
        f'<div class="eco-exec-cmp">{_esc(pick.compared)}</div>'
    )


def sleeves_panel_html(view: CompassView) -> str:
    """One card per sleeve: band + diversified Executable ETF legs."""
    if not view.sleeves:
        return (
            '<div class="eco-compass-empty">'
            "국면이 없으면 슬리브 밴드를 만들지 않습니다. 다시 계산하세요."
            "</div>"
        )
    picks = {p.sleeve_id: p for p in executable_lines(view.sleeves)}
    cells = []
    for s in view.sleeves:
        act = s.action
        tone = {"늘림": "up", "줄임": "down", "유지": "flat"}.get(act, "flat")
        pick = picks.get(s.sleeve_id)
        product = _legs_html(pick) if pick is not None else ""
        cells.append(
            f'<div class="eco-sleeve eco-sleeve-{_esc(tone)} eco-exec-card">'
            f'<div class="eco-sleeve-k">{_esc(s.label)}</div>'
            f'<div class="eco-sleeve-pct">{s.pct:.0f}%</div>'
            f'<div class="eco-sleeve-act">{_esc(act)}</div>'
            f'<div class="eco-sleeve-why">{_esc(s.why)}</div>'
            f"{product}"
            f"</div>"
        )
    alpha = f'<div class="eco-compass-alpha">{_esc(view.alpha_line)}</div>'
    foot = (
        '<div class="eco-compass-alpha">'
        "Review-only · 슬리브 안 ETF 2~3종 분산 · 자동매매·target 기입 없음 · "
        "한국 개별주는 포트폴리오 ③"
        "</div>"
    )
    return (
        f'<div class="eco-compass-block">'
        f"{alpha}{foot}"
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
        '<div class="eco-hist-banner">예시 · 비검증 · 백테스트 아님</div>'
        '<table class="eco-hist-table">'
        "<thead><tr>"
        "<th>슬리브</th><th>월 승률*</th><th>중앙 수익률*</th><th>표본(월)*</th>"
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


def alpha_ops_bridge_html(
    *,
    playbook_title: str,
    playbook_tone: str,
    action_lines: Sequence[tuple[str, str]],
) -> str:
    """나침반 → 포트: 거시 태도만 여기서, 종목 매매는 포트폴리오."""
    tone = playbook_tone or "wait"
    acts = "".join(
        f'<div class="eco-bridge-act">'
        f'<span class="eco-bridge-lab">{_esc(lab)}</span>'
        f'<span class="eco-bridge-body">{_esc(body)}</span>'
        f"</div>"
        for lab, body in action_lines[:3]
    ) or (
        '<div class="eco-bridge-act">'
        '<span class="eco-bridge-lab">다음</span>'
        '<span class="eco-bridge-body">포트폴리오에서 팔기→유지→사기 순으로 Review</span>'
        "</div>"
    )
    return (
        f'<div class="eco-bridge eco-bridge-{_esc(tone)}" role="note">'
        '<div class="eco-bridge-kicker">알파 위성으로 넘기기</div>'
        f'<div class="eco-bridge-title">{_esc(playbook_title)} → 포트폴리오</div>'
        '<div class="eco-bridge-scope">'
        "여기=국면·수급·슬리브 참고 · 종목 편입·매도·회차 금액은 "
        "<b>포트폴리오</b> · 자동주문·target 불변"
        "</div>"
        f'<div class="eco-bridge-acts">{acts}</div>'
        '<div class="eco-bridge-steps">'
        '<span class="eco-bridge-step">① 포트에서 팔기(보유만·배지)</span>'
        '<span class="eco-bridge-step">② 둘 다 유지</span>'
        '<span class="eco-bridge-step">③ 제안만 사기(≤33%)</span>'
        "</div>"
        "</div>"
    )
