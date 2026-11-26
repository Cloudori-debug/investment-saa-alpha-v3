"""중기 Soft 운영 데스크 — 표 B→A→C (실보유→슬롯→관찰).

프로그램 신호와 사람 판단을 열로 분리.
Soft 순위 변동 ≠ 매도 · Review-only · target 불변.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

from alpha_system.proposal_chart import norm_ticker
from alpha_system.ui.services.next_buy_queue import (
    NextBuyItem,
    NextBuyQueue,
    build_next_buy_queue,
    enrich_scoreboard_prices,
)
from alpha_system.ui.services.weight_action import (
    WeightAction,
    build_weight_actions_for_rows,
    step_label_ko,
)


@dataclass(frozen=True)
class SoftOpsLegend:
    market: str
    proposal_n: int
    held_soft_n: int
    wait_n: int
    observe_n: int
    sell_n: int
    buy_n: int
    today_buy_max: int
    hold_lo: int
    hold_hi: int
    line_ko: str
    counts_ko: str
    review_only: bool = True
    writes_target: bool = False


@dataclass(frozen=True)
class SoftOpsDesk:
    legend: SoftOpsLegend
    # B 실보유 · A Soft 슬롯 · C 관찰 (설계 캔버스)
    hold_rows: tuple[dict[str, Any], ...] = ()
    slot_rows: tuple[dict[str, Any], ...] = ()
    observe_rows: tuple[dict[str, Any], ...] = ()
    rotation_rows: tuple[dict[str, Any], ...] = ()
    # 호환 alias (테스트·구호출)
    proposal_rows: tuple[dict[str, Any], ...] = ()
    wait_rows: tuple[dict[str, Any], ...] = ()
    hold_ratio_rows: tuple[dict[str, Any], ...] = ()
    proposal_tickers: tuple[str, ...] = ()
    wait_tickers: tuple[str, ...] = ()
    queue: NextBuyQueue | None = None
    track_rows: tuple[dict[str, Any], ...] = ()
    track_note_ko: str = ""
    review_only: bool = True
    writes_target: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


def _f(v: object) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    return x


def _ticker_set(rows: Sequence[Any]) -> set[str]:
    out: set[str] = set()
    for r in rows or []:
        tk = norm_ticker(
            r.get("ticker") if isinstance(r, dict) else getattr(r, "ticker", None)
        )
        if tk and tk != "000000":
            out.add(tk)
    return out


def _funnel_limits(root: Path) -> tuple[int, int, int]:
    today_n, hold_lo, hold_hi = 2, 4, 6
    try:
        from alpha_system.ui.services.alpha_book_ops import (
            load_alpha_book_ops,
            today_buy_names_max,
        )

        pol = load_alpha_book_ops(root)
        today_n = int(today_buy_names_max(policy=pol))
        hold_lo = int(pol.funnel.hold_soft_min)
        hold_hi = int(pol.funnel.hold_soft_max)
    except Exception:  # noqa: BLE001
        pass
    return today_n, hold_lo, hold_hi


def _build_slot_table(
    soft_rows: Sequence[Any],
    *,
    held: set[str],
    today_buy_max: int,
) -> list[dict[str, Any]]:
    """표 A · Soft 슬롯 (신규용) · 사람 열=객관 기본안."""
    from alpha_system.ui.services.soft_trade_priority import rank_soft_trade_hints

    ranked_hints = rank_soft_trade_hints(
        soft_rows, held=held, today_buy_max=today_buy_max
    )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for h in ranked_hints:
        seen.add(h.ticker)
        rows.append(
            {
                "우선": h.rank,
                "종목": f"{h.name} {h.ticker}".strip(),
                "티커": h.ticker,
                "Soft": "슬롯",
                "프로그램": h.program_ko,
                "사람": h.human_ko,
            }
        )
    for r in soft_rows or []:
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk or tk in seen:
            continue
        name = str(getattr(r, "name", None) or tk)
        is_held = tk in held or bool(getattr(r, "is_held", False))
        if not is_held:
            continue
        rows.append(
            {
                "우선": None,
                "종목": f"{name} {tk}".strip(),
                "티커": tk,
                "Soft": "슬롯",
                "프로그램": "슬롯 · 이미 보유",
                "사람": "보유는 표 B · 배지만",
            }
        )
    return rows


def _hold_program_human(
    *,
    in_soft: bool,
    act: WeightAction,
) -> tuple[str, str]:
    """배지 신호를 Soft 밀림과 분리해 사람 열에 완화."""
    badge = step_label_ko(act.kind, move=act.move_pct)
    if act.kind == "cash_half":
        return badge, "배지 Review · HTS"
    if act.kind == "trim":
        return badge, "배지만 집행 · Soft 순위 추종 금지"
    # Soft 슬롯 밖 전량 Soft → 즉시 매도로 읽히지 않게
    if not in_soft and act.kind == "exit_full" and act.stance == "매도":
        return "슬롯 밖", "밀림 ≠ 매도 · 월 Review · 미정"
    if act.stance == "매도":
        return badge, "배지만 집행 · Soft 순위 추종 금지"
    if act.stance == "매수" and act.kind == "add_ready":
        return badge, "미정 · 추매 여부"
    return "유지", "손대지 않음 · 미정"


def _build_hold_table(
    ops_rows: Sequence[Any],
    *,
    soft: set[str],
    action_by: dict[str, WeightAction],
) -> list[dict[str, Any]]:
    """표 B · 실보유 (중기 본체)."""
    rows: list[dict[str, Any]] = []
    for r in ops_rows or []:
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        extra = getattr(r, "extra", None) or {}
        if str(extra.get("ops_book") or "") == "short":
            continue
        in_soft = tk in soft
        is_held = bool(getattr(r, "is_held", False)) or (
            (_f(getattr(r, "weight_pct", None)) or 0) > 0.05
        )
        if not is_held:
            continue
        name = str(getattr(r, "name", None) or tk)
        act = action_by.get(tk)
        if act is None:
            soft_rel = "슬롯 안" if in_soft else "슬롯 밖 (관찰)"
            rows.append(
                {
                    "종목": f"{name} {tk}".strip(),
                    "티커": tk,
                    "보유": "Y",
                    "프로그램": "—",
                    "Soft관계": soft_rel,
                    "사람": "미정",
                }
            )
            continue
        prog, human = _hold_program_human(in_soft=in_soft, act=act)
        soft_rel = "슬롯 안" if in_soft else "슬롯 밖 (관찰)"
        rows.append(
            {
                "종목": f"{name} {tk}".strip(),
                "티커": tk,
                "보유": "Y",
                "프로그램": prog,
                "Soft관계": soft_rel,
                "사람": human,
            }
        )

    def _key(row: dict[str, Any]) -> tuple:
        tk = str(row.get("티커") or "")
        act = action_by.get(tk)
        pri = act.priority if act else 999
        # Soft 밖을 위로 두지 않음 · Soft 안 먼저 · 그다음 priority
        return (0 if tk in soft else 1, pri, str(row.get("종목") or ""))

    rows.sort(key=_key)
    return rows


def _build_observe_table(
    *,
    wait_items: Sequence[NextBuyItem],
    alt_rows: Sequence[Any],
    soft: set[str],
    wait_tickers: set[str],
) -> list[dict[str, Any]]:
    """표 C · Soft 대기 + 게이트보류·관찰 (매수 지시 아님)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for it in wait_items:
        tk = norm_ticker(it.ticker)
        if not tk or tk in soft or tk in seen:
            continue
        seen.add(tk)
        rows.append(
            {
                "종목": f"{it.name} {tk}".strip(),
                "티커": tk,
                "층": "Soft 대기",
                "프로그램": f"Soft 통과 · 점수 {it.total_score:.0f}",
                "사람": "미정 · 여유 시만 · 추격 금지",
            }
        )

    for r in alt_rows or []:
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk or tk in soft or tk in seen:
            continue
        seen.add(tk)
        src = str(getattr(r, "source_ko", None) or "관찰")
        note = str(getattr(r, "note", None) or "")
        sc = getattr(r, "score", None)
        try:
            score_s = f" · 점수 {float(sc):.0f}" if sc is not None else ""
        except (TypeError, ValueError):
            score_s = ""
        if src == "게이트보류":
            layer = "게이트보류"
            human = "비중 금지 · 해부만 · 미정"
        elif "비적격" in src:
            layer = "점수·비적격"
            human = "관찰 · 미정"
        elif tk in wait_tickers:
            layer = "Soft 대기"
            human = "미정 · 여유 시만"
        else:
            layer = "점수·관찰"
            human = "해부·대기 · 비중 금지"
        rows.append(
            {
                "종목": f"{getattr(r, 'name', tk)} {tk}".strip(),
                "티커": tk,
                "층": layer,
                "프로그램": f"{src}{score_s}",
                "사람": human if not note.startswith("제안 N") else human,
            }
        )
    return rows


def _build_rotation_table(
    sells: Sequence[tuple[Any, WeightAction]],
    queue: NextBuyQueue,
) -> list[dict[str, Any]]:
    if not sells:
        return []
    row_a, act_a = sells[0]
    tk_a = norm_ticker(getattr(row_a, "ticker", None)) or ""
    name_a = str(getattr(row_a, "name", None) or tk_a)
    badge = step_label_ko(act_a.kind, move=act_a.move_pct)
    # Soft 밀림 전량은 순환 A로 올리지 않음
    if act_a.kind == "exit_full" and "proposal" in (act_a.body or "").lower():
        return []
    if act_a.kind == "exit_full" and badge == "전량":
        # still allow thesis exits; soft-out softened in hold table
        pass
    buy: NextBuyItem | None = queue.items[0] if queue.items else None
    if buy is None:
        b_lab = "(대기 없음 → 단기채)"
        todo = f"{badge} 후 현금/단기채 · 사람"
    else:
        b_lab = f"{buy.name} {buy.ticker}".strip()
        todo = f"{badge} → {buy.name} 분할 · 미정"
    return [
        {
            "팔": f"{name_a} {tk_a}".strip(),
            "살": b_lab,
            "사람": todo,
        }
    ]


def _ma_label_map(root: Path, market: str) -> dict[str, str]:
    try:
        from alpha_system.proposal_chart import load_cached_charts

        board = load_cached_charts(Path(root), str(market or "KOSPI").upper())
        if board is None:
            return {}
        out: dict[str, str] = {}
        for it in board.items or []:
            lab = str(getattr(it, "ma_label", "") or "")
            tk = norm_ticker(getattr(it, "ticker", ""))
            if tk and lab:
                out[tk] = lab
        return out
    except Exception:  # noqa: BLE001
        return {}


def _weight_action_map(
    rows: Sequence[Any],
    *,
    root: Path,
    chart_map: dict[str, Any] | None = None,
) -> dict[str, WeightAction]:
    if not rows:
        return {}
    flow_dir = Path(root) / "data"
    try:
        pairs = build_weight_actions_for_rows(
            list(rows),
            chart_map=chart_map or {},
            flow_data_dir=flow_dir,
        )
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, WeightAction] = {}
    for r, a in pairs:
        tk = norm_ticker(getattr(r, "ticker", None))
        if tk:
            out[tk] = a
    return out


def _sell_pairs(
    ops_rows: Sequence[Any],
    *,
    soft: set[str],
    root: Path,
    chart_map: dict[str, Any] | None = None,
) -> list[tuple[Any, WeightAction]]:
    """순환 A 후보 · Soft 밀림 전량만인 건 제외 (배지·목표가 매도만)."""
    action_by = _weight_action_map(ops_rows, root=root, chart_map=chart_map)
    sells: list[tuple[Any, WeightAction]] = []
    for r in ops_rows or []:
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        act = action_by.get(tk)
        if act is None or act.stance != "매도":
            continue
        if act.kind == "exit_full" and tk not in soft:
            # Soft 슬롯 밖 전량 Soft → 순환 자동 A 금지
            body = (act.body or "") + (act.board_line or "")
            if "제안" in body or "proposal" in body.lower() or "탈락" in body:
                continue
        sells.append((r, act))
    sells.sort(key=lambda t: (t[1].priority, -(t[1].move_pct or 0)))
    return sells


def build_soft_ops_desk(
    ctx: Any,
    *,
    root: Path | None = None,
) -> SoftOpsDesk:
    """중기 Soft A/B/C 데스크 · writes_target=false."""
    base = Path(root or getattr(ctx, "root", ".") or ".")
    market = str(
        getattr(ctx, "screen_market", None)
        or getattr(ctx, "market", None)
        or "KOSPI"
    ).upper()
    soft_rows = list(getattr(ctx, "portfolio_rows", None) or [])
    ops_rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    scoreboard = list(getattr(ctx, "scoreboard_rows", None) or [])
    blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])

    soft = _ticker_set(soft_rows)
    held = _ticker_set(ops_rows)
    for r in scoreboard:
        if getattr(r, "is_held", False):
            tk = norm_ticker(getattr(r, "ticker", None))
            if tk:
                held.add(tk)

    today_n, hold_lo, hold_hi = _funnel_limits(base)
    ma_map = _ma_label_map(base, market)
    chart_map: dict[str, Any] = {}
    try:
        from alpha_system.ui.services.proposal_chart_board import reads_by_ticker

        chart_map = reads_by_ticker(ctx) or {}
    except Exception:  # noqa: BLE001
        chart_map = {}

    action_by = _weight_action_map(
        list(soft_rows) + list(ops_rows),
        root=base,
        chart_map=chart_map,
    )

    slot_rows = _build_slot_table(
        soft_rows, held=held, today_buy_max=today_n
    )
    hold_rows = _build_hold_table(
        ops_rows, soft=soft, action_by=action_by
    )

    enriched = enrich_scoreboard_prices(scoreboard, soft_rows, ops_rows, blocked)
    sells = _sell_pairs(
        ops_rows, soft=soft, root=base, chart_map=chart_map
    )
    queue = build_next_buy_queue(
        scoreboard=enriched,
        proposal_rows=soft_rows,
        held_rows=ops_rows,
        sell_pressure=bool(sells),
        top_k=8,
        exclude_proposal=True,
        ma_label_by_ticker=ma_map or None,
    )
    wait_tks = {norm_ticker(it.ticker) for it in queue.items if it.ticker}

    alt_rows: list[Any] = []
    try:
        from alpha_system.ui.services.mid_soft_alt_candidates import (
            build_mid_soft_alt_candidates,
        )

        alt_board = build_mid_soft_alt_candidates(
            market=market,
            soft_rows=soft_rows,
            scoreboard_rows=scoreboard,
            blocked_rows=blocked,
            theme_draft_tickers=[],
            theme_names={},
            max_rows=12,
        )
        alt_rows = list(alt_board.rows or [])
    except Exception:  # noqa: BLE001
        alt_rows = []

    observe_rows = _build_observe_table(
        wait_items=queue.items,
        alt_rows=alt_rows,
        soft=soft,
        wait_tickers=wait_tks,
    )
    rotation = _build_rotation_table(sells, queue)

    buy_n = sum(
        1 for r in slot_rows if "오늘 슬롯" in str(r.get("프로그램") or "")
    )
    sell_n = len(sells)
    held_soft_n = len(soft & held)
    wait_n = len(queue.items)

    legend = SoftOpsLegend(
        market=market,
        proposal_n=len(slot_rows),
        held_soft_n=held_soft_n,
        wait_n=wait_n,
        observe_n=len(observe_rows),
        sell_n=sell_n,
        buy_n=buy_n,
        today_buy_max=today_n,
        hold_lo=hold_lo,
        hold_hi=hold_hi,
        line_ko=(
            "Soft 순위 변동 ≠ 매도 · 보유 출구=배지·월 Review · "
            f"신규≤{today_n} · 사람·HTS"
        ),
        counts_ko=(
            f"{market} · 보유 Soft {held_soft_n} · 슬롯 {len(slot_rows)} · "
            f"관찰 {len(observe_rows)}"
        ),
    )

    prop_tks = tuple(r["티커"] for r in slot_rows if r.get("티커"))
    wait_tk_t = tuple(sorted(wait_tks))
    notes: list[str] = []
    if set(prop_tks) & set(wait_tk_t):
        notes.append("대기열이 슬롯과 겹침")
    if not rotation:
        notes.append("순환 없음 · 보유 유지")

    track_rows: list[dict[str, Any]] = []
    track_note = (
        "제안→보유→슬롯아웃 · 윈도우 28일 · "
        "아웃 14일부터 월 Review · 밀림 ≠ 매도 · target 불변"
    )
    try:
        from alpha_system.ui.services.soft_proposal_track import (
            soft_names_from_rows,
            sync_soft_proposal_track,
            track_rows_for_table,
        )

        track_board = sync_soft_proposal_track(
            base,
            market=market,
            soft_names=soft_names_from_rows(soft_rows),
            held_tickers=held,
            as_of=getattr(ctx, "as_of", None),
            persist=True,
        )
        track_rows = track_rows_for_table(track_board)
        track_note = (
            f"제안→보유→슬롯아웃 · 윈도우 {track_board.rule.window_days}일 · "
            f"아웃 {track_board.rule.monthly_from_days}일~ 월 Review · "
            "밀림 ≠ 매도 · local만"
        )
    except Exception:  # noqa: BLE001
        track_rows = []

    # 레거시 필드: wait = Soft 대기만
    wait_legacy = [
        {
            "순위": i,
            "종목": r["종목"],
            "티커": r["티커"],
            "점수": None,
            "할 일": r["사람"],
        }
        for i, r in enumerate(
            (x for x in observe_rows if x.get("층") == "Soft 대기"), start=1
        )
    ]

    return SoftOpsDesk(
        legend=legend,
        hold_rows=tuple(hold_rows),
        slot_rows=tuple(slot_rows),
        observe_rows=tuple(observe_rows),
        rotation_rows=tuple(rotation),
        proposal_rows=tuple(slot_rows),
        wait_rows=tuple(wait_legacy),
        hold_ratio_rows=tuple(hold_rows),
        proposal_tickers=prop_tks,
        wait_tickers=wait_tk_t,
        queue=queue,
        track_rows=tuple(track_rows),
        track_note_ko=track_note,
        notes=tuple(notes),
    )


def _df_display(rows: Sequence[dict[str, Any]], *, drop_ticker: bool = True) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(list(rows))
    if drop_ticker and "티커" in df.columns:
        df = df.drop(columns=["티커"])
    return df


def render_soft_ops_desk(st: Any, desk: SoftOpsDesk) -> None:
    """전략 › 중기 Soft · B→A→C."""
    leg = desk.legend
    st.markdown(f"**Soft 운영** · {leg.counts_ko}")
    st.info(leg.line_ko)
    st.caption(
        "읽는 순: 실보유(B) → Soft 슬롯(A) → 관찰(C) → 트래킹(D) · 중기면 B만 HTS"
    )

    st.markdown("**B. 실보유** · 중기 본체 · Soft 순위와 분리")
    st.caption("출구=배지·월 Review · Soft 밀림만으로 전량 금지")
    df_b = _df_display(desk.hold_rows)
    if df_b.empty:
        st.caption("보유 없음 · 포트에서 보유 체크")
    else:
        st.dataframe(df_b, use_container_width=True, hide_index=True)

    if desk.rotation_rows:
        st.markdown("**순환 Review** · 배지 매도 여유만")
        st.dataframe(
            _df_display(desk.rotation_rows),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("**A. Soft 슬롯** · 신규만 · 전부 사지 않음")
    st.caption(f"오늘 신규≤{leg.today_buy_max} · 슬롯 변동 ≠ 보유 매도")
    df_a = _df_display(desk.slot_rows)
    if df_a.empty:
        st.caption("슬롯 없음 · 정량 후 확인")
    else:
        st.dataframe(df_a, use_container_width=True, hide_index=True)

    st.markdown("**C. 대기·관찰** · Soft 본선과 다른 축 · 매수 지시 아님")
    st.caption("게이트보류≠Soft 하위 · Soft 대기는 여유 시에만")
    df_c = _df_display(desk.observe_rows)
    if df_c.empty:
        st.caption("관찰 없음")
    else:
        st.dataframe(df_c, use_container_width=True, hide_index=True)

    st.markdown("**D. 제안 트래킹** · 틸트·리밸 시간 주기")
    st.caption(desk.track_note_ko or "제안→보유→슬롯아웃 · 밀림 ≠ 매도")
    df_d = _df_display(desk.track_rows)
    if df_d.empty:
        st.caption("추적 없음 · Soft 슬롯이 생기면 자동 기록")
    else:
        st.dataframe(df_d, use_container_width=True, hide_index=True)


__all__ = [
    "SoftOpsDesk",
    "SoftOpsLegend",
    "build_soft_ops_desk",
    "render_soft_ops_desk",
]
