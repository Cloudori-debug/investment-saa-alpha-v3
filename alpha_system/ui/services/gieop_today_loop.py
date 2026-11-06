"""오늘 해부 2~3종 루프 — 알파→박홍기 사용법 SoT (Review-only).

알파는 후보·초안만 · 해부는 박홍기 HTML · Soft/target 불변.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.ui.services.gieop_alpha_seed import AlphaGieopCandidate
from alpha_system.ui.services.gieop_fusion_desk import FusionRow
from alpha_system.ui.services.gieop_observe_board import (
    PORT_ACTION_HINT,
    PORT_ACTION_KO,
    PORT_BUY_REVIEW,
    ObserveUiRow,
    PortfolioBridgeRow,
    classify_port_action,
)
from alpha_system.ui.services.gieop_verdict import review_lock

MODEL_VERSION = "gieop-today-loop-v1"
DEFAULT_MAX_PICKS = 3


@dataclass(frozen=True)
class TodayGieopPick:
    ticker: str
    name: str
    why_ko: str
    quant_label: str
    draft_ko: str
    port_action: str
    port_action_ko: str
    next_ko: str
    in_soft: bool
    in_held: bool
    pass_value: bool
    buy_locked: bool = False


@dataclass
class TodayGieopLoopBoard:
    market: str
    picks: list[TodayGieopPick] = field(default_factory=list)
    loop_ko: str = (
        "① 관찰 파이프 → ② 본질(논리·퀄·Soft) 상위 2~3종만 박홍기 해부 → "
        "③ 할 일(사/유지/팔/대기) → Soft·HTS · target 사람만 · 시총 하한 없음"
    )
    empty_ko: str = "후보 없음 · 확인① 정량 후 관찰 파이프 (시총 제외·본질 기준)"
    writes_target: bool = False


def _bridge_by(rows: Sequence[PortfolioBridgeRow]) -> dict[str, PortfolioBridgeRow]:
    out: dict[str, PortfolioBridgeRow] = {}
    for r in rows or []:
        tk = norm_ticker(r.ticker)
        if tk:
            out[tk] = r
    return out


def _deep_set(rows: Sequence[ObserveUiRow]) -> set[str]:
    return {
        norm_ticker(r.ticker)
        for r in (rows or [])
        if norm_ticker(getattr(r, "ticker", None))
    }


def build_today_gieop_loop(
    *,
    market: str,
    fusion_rows: Sequence[FusionRow],
    bridge_rows: Sequence[PortfolioBridgeRow] | None = None,
    deep_pick: Sequence[ObserveUiRow] | None = None,
    candidates: Sequence[AlphaGieopCandidate] | None = None,
    max_picks: int = DEFAULT_MAX_PICKS,
) -> TodayGieopLoopBoard:
    """정량·Soft·심층으로 오늘 해부 2~3종 · Soft 점수 가산 없음."""
    bridge_map = _bridge_by(bridge_rows or [])
    deep = _deep_set(deep_pick or [])
    cand_by = {
        norm_ticker(c.ticker): c
        for c in (candidates or [])
        if norm_ticker(getattr(c, "ticker", None))
    }

    scored: list[tuple[int, FusionRow | AlphaGieopCandidate, str]] = []
    seen: set[str] = set()

    for r in fusion_rows or []:
        tk = norm_ticker(r.ticker)
        if not tk or tk in seen:
            continue
        seen.add(tk)
        q = r.quant.n_ok if r.quant else 0
        pri = 0
        if r.in_soft and r.pass_value:
            pri += 100
        elif r.in_soft:
            pri += 60
        elif r.pass_value:
            pri += 40
        if tk in deep:
            pri += 25
        if r.quant and r.quant.n_ok >= 6:
            pri += 15
        if r.draft and r.draft.status == "done":
            pri -= 30  # 이미 완료면 오늘 우선순위↓
        scored.append((pri * 10 + q, r, "fusion"))

    for c in candidates or []:
        tk = norm_ticker(c.ticker)
        if not tk or tk in seen:
            continue
        seen.add(tk)
        pri = 0
        if c.in_soft and c.pass_value:
            pri += 100
        elif c.in_soft:
            pri += 60
        elif c.pass_value:
            pri += 40
        if tk in deep:
            pri += 25
        scored.append((pri, c, "cand"))

    scored.sort(key=lambda x: (-x[0], getattr(x[1], "ticker", "")))

    def _make_pick(obj: object, kind: str) -> TodayGieopPick | None:
        if kind == "fusion":
            r = obj  # type: ignore[assignment]
            assert isinstance(r, FusionRow)
            tk = r.ticker
            br = bridge_map.get(tk)
            in_soft = r.in_soft
            in_held = bool(br.in_held) if br else False
            action = (
                br.port_action
                if br
                else classify_port_action(in_soft=in_soft, in_held=in_held)
            )
            why_bits = [r.source_ko, "본질"]
            if r.pass_value:
                why_bits.append("논리")
            if tk in deep:
                why_bits.append("심층")
            draft_ko = r.draft.status_ko if r.draft else "초안없음"
            locked = review_lock(
                action=action,
                action_ko=PORT_ACTION_KO.get(action, action),
                hint=PORT_ACTION_HINT.get(action, ""),
                verdict=r.verdict,
                buy_action=PORT_BUY_REVIEW,
            )
            if locked is None:
                return None
            action, action_ko, hint, buy_locked = locked
            return TodayGieopPick(
                ticker=tk,
                name=r.name or tk,
                why_ko=" · ".join(why_bits),
                quant_label=r.quant.label if r.quant else "—",
                draft_ko=draft_ko,
                port_action=action,
                port_action_ko=action_ko,
                next_ko=hint,
                in_soft=in_soft,
                in_held=in_held,
                pass_value=r.pass_value,
                buy_locked=buy_locked,
            )
        c = obj  # type: ignore[assignment]
        assert isinstance(c, AlphaGieopCandidate)
        tk = c.ticker
        br = bridge_map.get(tk)
        in_held = bool(br.in_held) if br else bool(c.in_held)
        action = (
            br.port_action
            if br
            else classify_port_action(in_soft=c.in_soft, in_held=in_held)
        )
        why_bits = [c.source_ko, "본질"]
        if c.pass_value:
            why_bits.append("논리")
        if tk in deep:
            why_bits.append("심층")
        return TodayGieopPick(
            ticker=tk,
            name=c.name or tk,
            why_ko=" · ".join(why_bits),
            quant_label="—",
            draft_ko="초안없음",
            port_action=action,
            port_action_ko=PORT_ACTION_KO.get(action, action),
            next_ko=PORT_ACTION_HINT.get(action, ""),
            in_soft=c.in_soft,
            in_held=in_held,
            pass_value=c.pass_value,
        )

    def _sector_of(obj: object, kind: str) -> str:
        if kind == "fusion":
            c = cand_by.get(getattr(obj, "ticker", ""))
            return str(c.sector or "") if c else ""
        return str(getattr(obj, "sector", "") or "")

    picks: list[TodayGieopPick] = []
    picked_tk: set[str] = set()
    used_sector: set[str] = set()
    limit = max(1, int(max_picks))

    # 1차: 업종 다양
    for _score, obj, kind in scored:
        if len(picks) >= limit:
            break
        tk = norm_ticker(getattr(obj, "ticker", None))
        if not tk or tk in picked_tk:
            continue
        sec = _sector_of(obj, kind)
        if sec and sec in used_sector:
            continue
        pick = _make_pick(obj, kind)
        if not pick:
            continue
        picks.append(pick)
        picked_tk.add(tk)
        if sec:
            used_sector.add(sec)

    # 2차: 부족분 채움
    for _score, obj, kind in scored:
        if len(picks) >= limit:
            break
        tk = norm_ticker(getattr(obj, "ticker", None))
        if not tk or tk in picked_tk:
            continue
        pick = _make_pick(obj, kind)
        if not pick:
            continue
        picks.append(pick)
        picked_tk.add(tk)

    return TodayGieopLoopBoard(market=str(market), picks=picks)


def today_gieop_loop_html(board: TodayGieopLoopBoard) -> str:
    esc = escape
    if not board.picks:
        return (
            '<div class="pf-today-gieop">'
            '<div class="pf-today-h">오늘 해부 (2~3종)</div>'
            f'<p class="pf-today-empty">{esc(board.empty_ko)}</p>'
            f'<p class="pf-today-loop">{esc(board.loop_ko)}</p>'
            "</div>"
        )
    rows = ""
    for i, p in enumerate(board.picks, start=1):
        rows += (
            f'<div class="pf-today-row">'
            f'<div class="pf-today-rank">{i}</div>'
            f'<div class="pf-today-main">'
            f"<strong>{esc(p.name)}</strong> "
            f'<span class="pf-ticker">{esc(p.ticker)}</span>'
            f'<div class="pf-today-why">{esc(p.why_ko)} · 정량 {esc(p.quant_label)} · 해부 {esc(p.draft_ko)}</div>'
            f"</div>"
            f'<div class="pf-today-next">'
            f'<span class="pf-today-act">{esc(p.port_action_ko)}</span>'
            f'<div class="pf-today-hint">{esc(p.next_ko)}</div>'
            f"</div></div>"
        )
    return (
        '<div class="pf-today-gieop" role="region" aria-label="오늘 해부">'
        '<div class="pf-today-h">오늘 해부 · 본질 기준 · '
        f"{len(board.picks)}종"
        '<span class="pf-today-sub">시총 하한 없음 · Soft 불변</span>'
        "</div>"
        f'<p class="pf-today-loop">{esc(board.loop_ko)}</p>'
        f"{rows}"
        '<p class="pf-today-foot">'
        "해부 끝나면 할 일만 실행 · 전 종목 해부 금지 · target 자동 없음"
        "</p></div>"
    )


__all__ = [
    "DEFAULT_MAX_PICKS",
    "MODEL_VERSION",
    "TodayGieopLoopBoard",
    "TodayGieopPick",
    "build_today_gieop_loop",
    "today_gieop_loop_html",
]
