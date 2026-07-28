"""Monthly rebalance ops board — Review-only checklist for home UI.

Rules (operator-facing, no auto orders / no target_portfolio writes):
1. kr_alpha: rebalance only when weight is outside target ± band
2. Prefer weekly gate / exit signals as the trigger for name trades
3. CRISIS regime → exception rebalance allowed (do not wait for month-start)
4. SCALE_IN in progress → exclude name from full monthly align (legs only)

Does not write target_portfolio.csv.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal, Sequence

Tone = Literal["ok", "warn", "danger", "muted"]

DEFAULT_BAND_REL = 0.25  # ±25% relative to target weight
MONTH_START_WINDOW_DAYS = 3  # treat day 1–3 as "month-start window"


@dataclass(frozen=True)
class RebalItem:
    ticker: str
    name: str
    action: str
    detail: str
    tone: Tone = "warn"


@dataclass(frozen=True)
class RebalRuleCard:
    key: str
    title: str
    status: str
    detail: str
    tone: Tone
    do_now: bool
    items: tuple[RebalItem, ...] = ()


@dataclass(frozen=True)
class MonthlyRebalBoard:
    as_of: date
    is_month_start_window: bool
    regime_label: str
    crisis: bool
    band_rel: float
    cards: tuple[RebalRuleCard, ...]
    do_now_count: int
    summary: str


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_scale_in_open_tickers(root: Path) -> set[str]:
    """Tickers with unfinished SCALE_IN — journal + optional runtime file."""
    out: set[str] = set()
    path = root / "data" / "scale_in_open.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            tickers = raw.get("tickers") if isinstance(raw, dict) else raw
            if isinstance(tickers, list):
                out.update(str(t).zfill(6) for t in tickers if str(t).strip())
        except (OSError, ValueError, TypeError):
            pass
    # Journal heuristic: recent SCALE_IN leg without complete
    journal = root / "data" / "alpha_action_journal.jsonl"
    if not journal.exists():
        journal = root / "outputs" / "alpha_action_journal.jsonl"
    if journal.exists():
        try:
            lines = journal.read_text(encoding="utf-8").splitlines()[-200:]
        except OSError:
            lines = []
        open_map: dict[str, int] = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = str(row.get("action_kind") or "")
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            tk = str(payload.get("ticker") or row.get("subject") or "").zfill(6)
            if not tk.strip("0"):
                continue
            if "SCALE_IN" in kind.upper() or payload.get("scale_in_leg") is not None:
                leg = int(payload.get("scale_in_leg") or 0)
                n = int(payload.get("scale_in_n_legs") or 3)
                if leg > 0 and leg < n:
                    open_map[tk] = max(open_map.get(tk, 0), leg)
                elif "COMPLETE" in kind.upper() or leg >= n:
                    open_map.pop(tk, None)
        out.update(open_map.keys())
    return out


def _band_breach(
    actual: float | None,
    target: float | None,
    *,
    band_rel: float,
) -> tuple[bool, str]:
    if actual is None or target is None:
        return False, "목표/실비중 없음"
    if target <= 0:
        if actual > 0.05:
            return True, f"목표 0 · 실 {actual:.2f}%p (정리 검토)"
        return False, "목표 0"
    lo = target * (1.0 - band_rel)
    hi = target * (1.0 + band_rel)
    if actual < lo or actual > hi:
        return True, f"실 {actual:.2f}% · 목표 {target:.2f}% · 밴드 {lo:.2f}~{hi:.2f}%"
    return False, f"실 {actual:.2f}% · 목표 {target:.2f}% · 밴드 내"


def build_monthly_rebal_board(
    ctx: Any,
    *,
    band_rel: float = DEFAULT_BAND_REL,
    as_of: date | None = None,
) -> MonthlyRebalBoard:
    """Build home checklist from live ctx (ops book + exit cues + regime)."""
    as_of = as_of or getattr(ctx, "as_of", None) or date.today()
    root = Path(ctx.root)
    is_month_start = as_of.day <= MONTH_START_WINDOW_DAYS

    from alpha_system.ui.services.v2_chrome import regime_info

    reg = regime_info(root)
    regime_label = str(reg.get("label") or reg.get("regime") or "—")
    crisis = "CRISIS" in regime_label.upper() or bool(reg.get("crisis"))

    ops = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    proposal = list(getattr(ctx, "portfolio_rows", None) or [])
    open_scale = _load_scale_in_open_tickers(root)

    # target weights: prefer ops.initial_weight_pct, fallback target_portfolio.csv
    target_map: dict[str, tuple[str, float]] = {}
    tpath = root / "data" / "target_portfolio.csv"
    if tpath.exists():
        try:
            import pandas as pd

            tdf = pd.read_csv(tpath, dtype=str)
            if not tdf.empty and "ticker" in tdf.columns:
                for _, row in tdf.iterrows():
                    if str(row.get("asset_group") or "") != "kr_alpha":
                        continue
                    tk = str(row.get("ticker") or "").zfill(6)
                    tw = _f(row.get("target_weight"))
                    if tw is None:
                        continue
                    target_map[tk] = (str(row.get("name") or tk), tw)
        except Exception:
            target_map = {}
    for r in ops:
        tw = _f(getattr(r, "initial_weight_pct", None))
        if tw is not None:
            target_map[str(r.ticker).zfill(6)] = (str(r.name or r.ticker), tw)

    actual_map = {
        str(r.ticker).zfill(6): (_f(getattr(r, "weight_pct", None)) or 0.0, str(r.name or r.ticker))
        for r in ops
    }

    # --- Rule 1: band ---
    band_items: list[RebalItem] = []
    for tk, (name, tgt) in sorted(target_map.items()):
        act = actual_map.get(tk, (0.0, name))[0]
        nm = actual_map.get(tk, (0.0, name))[1] or name
        breached, detail = _band_breach(act, tgt, band_rel=band_rel)
        if not breached:
            continue
        if tk not in actual_map and not (is_month_start or crisis):
            continue
        band_items.append(
            RebalItem(
                ticker=tk,
                name=nm,
                action="밴드 밖 → 리밸 검토" if tk in actual_map else "미보유 · 목표>0",
                detail=detail
                + (
                    ""
                    if tk in actual_map
                    else " · 편입은 게이트·SCALE_IN 후"
                ),
                tone="warn" if tk in actual_map else "muted",
            )
        )
    for tk, (act, nm) in actual_map.items():
        if tk in target_map:
            continue
        if act > 0.05:
            band_items.append(
                RebalItem(
                    ticker=tk,
                    name=nm,
                    action="목표 없음 · 정리 검토",
                    detail=f"실 {act:.2f}% · target에 kr_alpha 행 없음",
                    tone="warn",
                )
            )

    band_do = bool(band_items) and (is_month_start or crisis)
    card_band = RebalRuleCard(
        key="band",
        title="① kr_alpha 밴드만 리밸",
        status=(
            f"밴드 밖 {len(band_items)}종"
            if band_items
            else "전 종목 밴드 내 (전량 월 리밸 불필요)"
        ),
        detail=(
            f"목표 대비 ±{int(band_rel * 100)}% 상대 밴드. "
            "밴드 안이면 매달 1일에 맞추지 않습니다."
            + (
                " · 월초 창이라 오늘 정렬 검토"
                if is_month_start and band_items
                else ""
            )
        ),
        tone="warn" if band_do else ("ok" if not band_items else "muted"),
        do_now=band_do,
        items=tuple(band_items[:12]),
    )

    # --- Rule 2: exit / weekly signals ---
    from alpha_system.ui.services.ops_exit_signal import actionable_ops_signals

    sig_rows = actionable_ops_signals(proposal) if proposal else []
    # also check ops book if proposal empty
    if not sig_rows and ops:
        sig_rows = actionable_ops_signals(ops)
    sig_items = [
        RebalItem(
            ticker=str(r.ticker).zfill(6),
            name=str(r.name or r.ticker),
            action=str(getattr(r, "ops_signal_label", None) or "신호"),
            detail=str(getattr(r, "ops_signal_detail", None) or ""),
            tone="danger"
            if getattr(r, "ops_signal", "") in ("exit_full", "review")
            else "warn",
        )
        for r in sig_rows
    ]
    card_signal = RebalRuleCard(
        key="signal",
        title="② 주간 게이트·익절 신호 우선",
        status=(
            f"실행 검토 {len(sig_items)}종"
            if sig_items
            else "줄이기·환금·전량 신호 없음"
        ),
        detail="월 리밸보다 익절/게이트 신호를 먼저 수행합니다. 자동 주문 없음.",
        tone="warn" if sig_items else "ok",
        do_now=bool(sig_items),
        items=tuple(sig_items[:12]),
    )

    # --- Rule 3: CRISIS exception ---
    card_crisis = RebalRuleCard(
        key="crisis",
        title="③ CRISIS 예외 리밸",
        status="CRISIS — 월초 기다리지 말고 방어 정렬 허용" if crisis else "비위기 — 예외 리밸 불필요",
        detail=(
            f"현재 레짐: {regime_label}. "
            + (
                "ETF·현금 방어 비중과 kr_alpha 과다 노출을 오늘 점검하세요."
                if crisis
                else "정기 리밸은 월초 창(1~3일) 또는 밴드 이탈·신호 시."
            )
        ),
        tone="danger" if crisis else "ok",
        do_now=crisis,
        items=tuple(
            i
            for i in band_items
            if crisis
        )[:8],
    )

    # --- Rule 4: SCALE_IN exclude ---
    scale_items = [
        RebalItem(
            ticker=tk,
            name=tk,
            action="월 전량 정렬 제외",
            detail="분할매수 진행 중 — 회차만 진행, 한날 전액 금지",
            tone="warn",
        )
        for tk in sorted(open_scale)
    ]
    # Also flag band items that are in scale-in
    overlap = [i for i in band_items if i.ticker in open_scale]
    card_scale = RebalRuleCard(
        key="scale_in",
        title="④ SCALE_IN 중 → 월 리밸 제외",
        status=(
            f"진행 {len(open_scale)}종 · 월 정렬에서 빼기"
            if open_scale
            else "진행 중 분할매수 없음 (data/scale_in_open.json 또는 저널)"
        ),
        detail=(
            "진행 종목은 회차만 집행. "
            + (
                f"밴드 밖이면서 SCALE_IN 중: {', '.join(i.ticker for i in overlap)}"
                if overlap
                else "밴드 겹침 없음."
            )
        ),
        tone="warn" if open_scale else "ok",
        do_now=False,  # informational — do NOT rebalance these
        items=tuple(scale_items[:12]),
    )

    cards = (card_band, card_signal, card_crisis, card_scale)
    do_now_count = sum(1 for c in cards if c.do_now)
    if do_now_count:
        summary = f"오늘 수행할 리밸 규칙 {do_now_count}건 · 자동매매 아님"
    elif is_month_start:
        summary = "월초 창 · 당장 할 리밸 없음 (밴드 내·신호 없음)"
    else:
        summary = "정기 월 리밸 대기 · 신호·밴드·CRISIS만 감시"

    return MonthlyRebalBoard(
        as_of=as_of,
        is_month_start_window=is_month_start,
        regime_label=regime_label,
        crisis=crisis,
        band_rel=band_rel,
        cards=cards,
        do_now_count=do_now_count,
        summary=summary,
    )
