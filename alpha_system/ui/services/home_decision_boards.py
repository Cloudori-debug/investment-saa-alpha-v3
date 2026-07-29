"""Home decision boards — glance portfolio → holdings analysis → proposal analysis.

Review-only · no auto orders · no target_portfolio writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

Tone = Literal["ok", "warn", "danger", "muted"]


@dataclass(frozen=True)
class CombinedRatioRow:
    ticker: str
    name: str
    role: str  # 보유·제안 | 보유 | 제안
    actual_pct: float | None
    proposal_pct: float | None
    target_pct: float | None
    gap_pct: float | None
    action: str
    action_tone: Tone
    note: str


@dataclass(frozen=True)
class HoldingsAnalysisRow:
    ticker: str
    name: str
    role: str
    actual_pct: float | None
    strategy: str
    guide: str
    mid_trend: str
    m1: str
    m3: str
    xs: str
    bearing: str
    exit_label: str
    source: str


@dataclass(frozen=True)
class ProposalAnalysisRow:
    rank: int
    ticker: str
    name: str
    role: str
    proposal_pct: float | None
    total_score: float | None
    score_q: float | None
    score_v: float | None
    score_sr: float | None
    momentum: str
    advice: str
    exit_label: str


@dataclass(frozen=True)
class HomeDecisionBoards:
    combined: tuple[CombinedRatioRow, ...]
    holdings: tuple[HoldingsAnalysisRow, ...]
    proposals: tuple[ProposalAnalysisRow, ...]
    summary: str
    alpha_equity_pct: float | None
    alpha_cash_pct: float | None
    n_held: int
    n_proposal: int


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _sign_ko(sign: str) -> str:
    return {"UP": "상승", "DOWN": "하락", "—": "—"}.get(sign, sign or "—")


def _tk(row: Any) -> str:
    return str(getattr(row, "ticker", "") or "").zfill(6)


def build_home_decision_boards(ctx: Any) -> HomeDecisionBoards:
    """Build the three home tables the operator expects."""
    from alpha_system.ui.services.alpha_book_ops import (
        alpha_target_map_from_saa_csv,
        build_alpha_actual_map,
        load_alpha_book_ops,
    )
    from alpha_system.ui.services.momentum_holding_monitor import (
        SOURCE_KO,
        build_momentum_holding_board,
    )
    from alpha_system.ui.services.momentum_review import (
        GRADE_KO,
        build_momentum_review_board,
    )
    from alpha_system.ui.services.ops_exit_signal import actionable_ops_signals
    from alpha_system.ui.services.today_actions_board import build_today_action_board

    root = getattr(ctx, "root", None)
    policy = load_alpha_book_ops(root)
    ops = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    proposal = list(getattr(ctx, "portfolio_rows", None) or [])
    proposal_by = {_tk(r): r for r in proposal if _tk(r)}
    ops_by = {_tk(r): r for r in ops if _tk(r)}
    proposal_tks = set(proposal_by)
    ops_tks = set(ops_by)

    actual_map = build_alpha_actual_map(root, ops, policy) if root else {}
    held_tks = set(actual_map) if actual_map else set(ops_tks)

    # SAA → alpha-book target %
    target_map: dict[str, tuple[str, float]] = {}
    try:
        import pandas as pd

        tp = root / "data" / "target_portfolio.csv" if root else None
        saa: dict[str, tuple[str, float]] = {}
        if tp is not None and tp.exists():
            df = pd.read_csv(tp, dtype=str)
            for _, row in df.iterrows():
                if str(row.get("asset_group") or "") != "kr_alpha":
                    continue
                tk = str(row.get("ticker") or "").zfill(6)
                if not tk or tk == "000000":
                    continue
                try:
                    w = float(row.get("target_weight") or row.get("weight") or 0)
                except (TypeError, ValueError):
                    w = 0.0
                if w <= 0:
                    continue
                saa[tk] = (str(row.get("name") or tk), w)
        target_map = alpha_target_map_from_saa_csv(saa, policy)
    except Exception:
        target_map = {}

    actions = {r.ticker: r for r in build_today_action_board(ctx).rows}
    exit_by = {
        _tk(r): r
        for r in actionable_ops_signals(proposal if proposal else ops)
    }

    mom = build_momentum_review_board(ctx)
    mom_by = {i.ticker: i for i in mom.items}
    mhm = build_momentum_holding_board(
        ctx, mom_board=mom, include_all_ops=True, persist_log=False
    )
    mhm_by = {r.ticker: r for r in mhm.rows}

    scores = list(getattr(ctx, "scoreboard_rows", None) or [])
    score_by = {str(r.ticker).zfill(6): r for r in scores}

    # --- ① Combined ratio ---
    universe = held_tks | proposal_tks
    # Cash sleeve only when alpha book has holdings or proposals
    cash = policy.cash_ticker
    if universe and (cash in actual_map or cash in target_map):
        universe.add(cash)
    elif cash in actual_map:
        universe.add(cash)

    combined: list[CombinedRatioRow] = []
    for tk in universe:
        held = tk in held_tks or tk in actual_map
        prop = tk in proposal_tks
        if held and prop:
            role = "보유·제안"
        elif held:
            role = "보유"
        else:
            role = "제안"

        name = (
            (actual_map.get(tk) or (None, None))[1]
            or (target_map.get(tk) or (None, None))[0]
            or (getattr(ops_by.get(tk), "name", None) if tk in ops_by else None)
            or (getattr(proposal_by.get(tk), "name", None) if tk in proposal_by else None)
            or tk
        )
        actual = actual_map[tk][0] if tk in actual_map else None
        prop_w = _f(getattr(proposal_by[tk], "weight_pct", None)) if prop else None
        tgt = target_map[tk][1] if tk in target_map else None
        gap = None
        if actual is not None and tgt is not None:
            gap = round(actual - tgt, 2)

        act_row = actions.get(tk)
        if act_row is not None:
            action = act_row.action
            tone: Tone = act_row.tone if act_row.tone in ("ok", "warn", "danger", "muted") else "warn"
            note = act_row.note
        else:
            ex = exit_by.get(tk)
            if ex is not None and getattr(ex, "ops_signal", "") not in ("", "hold"):
                action = str(getattr(ex, "ops_signal_label", "") or "")
                tone = "danger" if getattr(ex, "ops_signal", "") == "exit_full" else "warn"
                note = str(getattr(ex, "ops_signal_detail", "") or "")[:80]
            else:
                action = "유지"
                tone = "ok"
                note = ""

        combined.append(
            CombinedRatioRow(
                ticker=tk,
                name=str(name),
                role=role,
                actual_pct=actual,
                proposal_pct=prop_w,
                target_pct=tgt,
                gap_pct=gap,
                action=action,
                action_tone=tone,
                note=note,
            )
        )

    def _comb_key(r: CombinedRatioRow) -> tuple:
        # held first, then by actual weight desc, then proposal weight, then name
        held_rank = 0 if "보유" in r.role else 1
        return (
            held_rank,
            -(r.actual_pct or -1),
            -(r.proposal_pct or -1),
            r.name,
        )

    combined.sort(key=_comb_key)

    # --- ② Holdings analysis ---
    holdings: list[HoldingsAnalysisRow] = []
    seen_h: set[str] = set()
    for tk in sorted(held_tks | ops_tks, key=lambda t: -(actual_map.get(t, (0.0, ""))[0])):
        if tk == cash and tk not in held_tks and tk not in ops_tks:
            continue
        if tk in seen_h:
            continue
        seen_h.add(tk)
        name = (
            (actual_map.get(tk) or (None, None))[1]
            or getattr(ops_by.get(tk), "name", None)
            or tk
        )
        role = "보유·제안" if tk in proposal_tks else "보유"
        m = mhm_by.get(tk)
        mom_i = mom_by.get(tk)
        ex = exit_by.get(tk)
        exit_label = "—"
        if ex is not None and getattr(ex, "ops_signal", "") not in ("", "hold"):
            exit_label = str(getattr(ex, "ops_signal_label", "") or "—")
        if m is not None:
            detail = (m.strategy_detail or "").strip()
            if len(detail) > 48:
                detail = detail[:46] + "…"
            holdings.append(
                HoldingsAnalysisRow(
                    ticker=tk,
                    name=str(name),
                    role=role,
                    actual_pct=actual_map[tk][0] if tk in actual_map else None,
                    strategy=m.strategy_action or "—",
                    guide=detail or (m.reason or "—"),
                    mid_trend=_sign_ko(m.ts_sign),
                    m1=_sign_ko(m.short_1m_sign),
                    m3=_sign_ko(m.short_3m_sign),
                    xs=f"{m.xs_pct:.0f}" if m.xs_pct is not None else "—",
                    bearing=m.bearing_ko or "—",
                    exit_label=exit_label,
                    source=SOURCE_KO.get(m.source, m.source),
                )
            )
        else:
            holdings.append(
                HoldingsAnalysisRow(
                    ticker=tk,
                    name=str(name),
                    role=role,
                    actual_pct=actual_map[tk][0] if tk in actual_map else None,
                    strategy="—",
                    guide=(mom_i.advice if mom_i else "재검토 단서"),
                    mid_trend="—",
                    m1="—",
                    m3="—",
                    xs=(
                        f"{mom_i.cross_pct:.0f}"
                        if mom_i is not None and mom_i.cross_pct is not None
                        else "—"
                    ),
                    bearing=GRADE_KO.get(mom_i.grade, "—") if mom_i else "—",
                    exit_label=exit_label,
                    source="보유",
                )
            )

    # --- ③ Proposal analysis ---
    proposals: list[ProposalAnalysisRow] = []
    for rank, r in enumerate(proposal, start=1):
        tk = _tk(r)
        mom_i = mom_by.get(tk)
        sc = score_by.get(tk)
        ex = exit_by.get(tk)
        exit_label = "—"
        if ex is not None and getattr(ex, "ops_signal", "") not in ("", "hold"):
            exit_label = str(getattr(ex, "ops_signal_label", "") or "—")
        role = "보유·제안" if tk in held_tks or tk in ops_tks else "제안"
        proposals.append(
            ProposalAnalysisRow(
                rank=rank,
                ticker=tk,
                name=str(getattr(r, "name", None) or tk),
                role=role,
                proposal_pct=_f(getattr(r, "weight_pct", None)),
                total_score=_f(getattr(r, "total_score", None))
                if getattr(r, "total_score", None) is not None
                else (_f(getattr(sc, "total_score", None)) if sc else None),
                score_q=_f(getattr(sc, "score_q", None)) if sc else None,
                score_v=_f(getattr(sc, "score_v", None)) if sc else None,
                score_sr=_f(getattr(sc, "score_sr", None)) if sc else None,
                momentum=GRADE_KO.get(mom_i.grade, "—") if mom_i else "—",
                advice=(mom_i.advice if mom_i else "—"),
                exit_label=exit_label,
            )
        )

    cash_pct = actual_map.get(cash, (None, None))[0] if actual_map else None
    equity_pct = None
    if actual_map:
        equity_pct = round(
            sum(v for tk, (v, _) in actual_map.items() if tk != cash), 1
        )
        if cash_pct is None:
            cash_pct = round(100.0 - (equity_pct or 0.0), 1)

    n_held = len([t for t in held_tks if t != cash])
    n_prop = len(proposal)
    summary = (
        f"비중표 {len(combined)}종 · 보유 {n_held} · 제안 {n_prop} · "
        "①로 전략 · ②③로 근거 · Review-only"
    )
    return HomeDecisionBoards(
        combined=tuple(combined),
        holdings=tuple(holdings),
        proposals=tuple(proposals),
        summary=summary,
        alpha_equity_pct=equity_pct,
        alpha_cash_pct=cash_pct,
        n_held=n_held,
        n_proposal=n_prop,
    )


def combined_as_table(rows: Sequence[CombinedRatioRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "구분": r.role,
                "종목": f"{r.name} ({r.ticker})",
                "실%": f"{r.actual_pct:.1f}" if r.actual_pct is not None else "—",
                "제안%": f"{r.proposal_pct:.1f}" if r.proposal_pct is not None else "—",
                "목표%": f"{r.target_pct:.1f}" if r.target_pct is not None else "—",
                "괴리": f"{r.gap_pct:+.1f}" if r.gap_pct is not None else "—",
                "조치": r.action,
                "비고": r.note,
            }
        )
    return out


def holdings_as_table(rows: Sequence[HoldingsAnalysisRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "종목": f"{r.name} ({r.ticker})",
                "구분": r.role,
                "실%": f"{r.actual_pct:.1f}" if r.actual_pct is not None else "—",
                "전략": r.strategy,
                "안내": r.guide,
                "중기": r.mid_trend,
                "1개월": r.m1,
                "3개월": r.m3,
                "교차": r.xs,
                "바늘": r.bearing,
                "익절": r.exit_label,
                "출처": r.source,
            }
        )
    return out


def proposals_as_table(rows: Sequence[ProposalAnalysisRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "순위": r.rank,
                "종목": f"{r.name} ({r.ticker})",
                "구분": r.role,
                "제안%": f"{r.proposal_pct:.1f}" if r.proposal_pct is not None else "—",
                "점수": f"{r.total_score:.1f}" if r.total_score is not None else "—",
                "Q": f"{r.score_q:.0f}" if r.score_q is not None else "—",
                "V": f"{r.score_v:.0f}" if r.score_v is not None else "—",
                "SR": f"{r.score_sr:.0f}" if r.score_sr is not None else "—",
                "모멘텀": r.momentum,
                "권고": r.advice,
                "익절": r.exit_label,
            }
        )
    return out
