"""중기 Soft 매매 우선순위 — 사람 열·오늘 매매 기본값 (Review-only).

목표: Soft 슬롯 ≠ 전부 사기.
여유·목표가 품질·오늘 한도로 객관 기본안을 붙인다.
target·점수·자동주문 불변.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from alpha_system.proposal_chart import norm_ticker

# 목표가 여유( (tp-px)/tp ) — 이하면 보류
THIN_UPSIDE_PCT = 5.0
# 조건부 사기 하한 (초안·여유 중간)
COND_UPSIDE_PCT = 15.0


@dataclass(frozen=True)
class SoftTradeHint:
    ticker: str
    name: str
    rank: int  # 1 = 최우선 사기 후보
    stance: str  # 사기 | 조건부사기 | 보류 | 패스 | 보유참조
    human_ko: str
    program_ko: str
    upside_pct: float | None
    target_kind: str  # yaml | quant_draft | missing
    today_slot: bool  # 오늘 신규 한도 안


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


def _upside(px: float | None, tp: float | None) -> float | None:
    if px is None or tp is None or tp <= 0:
        return None
    return round(100.0 * (tp - px) / tp, 2)


def _target_kind(row: Any) -> str:
    gap = str(getattr(row, "target_gap_kind", None) or "")
    if gap == "quant_draft":
        return "quant_draft"
    if bool(getattr(row, "has_target", False)) and _f(getattr(row, "target_price", None)):
        return "yaml"
    if _f(getattr(row, "target_price", None)):
        return "quant_draft"
    return "missing"


def rank_soft_trade_hints(
    soft_rows: Sequence[Any],
    *,
    held: set[str] | None = None,
    today_buy_max: int = 2,
    thin_upside_pct: float = THIN_UPSIDE_PCT,
    cond_upside_pct: float = COND_UPSIDE_PCT,
) -> list[SoftTradeHint]:
    """Soft 신규 후보에 사람 기본 스탠스·오늘 슬롯 부여."""
    held_set = {norm_ticker(t) for t in (held or []) if norm_ticker(t)}
    scored: list[tuple[float, float, float, Any, float | None, str]] = []
    for r in soft_rows or []:
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        if tk in held_set or bool(getattr(r, "is_held", False)):
            continue
        px = _f(getattr(r, "current_price", None))
        tp = _f(getattr(r, "target_price", None))
        up = _upside(px, tp)
        kind = _target_kind(r)
        score = _f(getattr(r, "total_score", None)) or 0.0
        # sort key: yaml before draft; upside; score
        kind_rank = float({"yaml": 0, "quant_draft": 1, "missing": 2}.get(kind, 2))
        up_key = -(up if up is not None else -999.0)
        scored.append((kind_rank, up_key, -score, r, up, kind))

    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    today_n = max(0, int(today_buy_max))
    out: list[SoftTradeHint] = []
    buy_slots = 0
    for i, (_kr, _u, _s, r, up, kind) in enumerate(scored, start=1):
        tk = norm_ticker(getattr(r, "ticker", None)) or ""
        name = str(getattr(r, "name", None) or tk)
        if kind == "missing" or up is None:
            stance = "보류"
            human = "보류 · 목표가 없음 · 사기 금지"
            prog = "신규 차단"
            slot = False
        elif up < thin_upside_pct:
            stance = "패스"
            human = f"패스 · 여유 {up:g}% < {thin_upside_pct:g}% · 추격 금지"
            prog = "여유 얇음"
            slot = False
        elif kind == "quant_draft" and up < cond_upside_pct:
            stance = "보류"
            human = f"보류 · 초안·여유 {up:g}% · YAML 승인 후"
            prog = "초안 조건부"
            slot = False
        elif buy_slots < today_n:
            buy_slots += 1
            slot = True
            if kind == "quant_draft":
                stance = "조건부사기"
                human = (
                    f"조건부 사기 {buy_slots}순위 · 초안 · "
                    f"여유 {up:g}% · 오늘≤{today_n} · ≤33%"
                )
                prog = f"오늘 슬롯 {buy_slots}/{today_n} · 초안"
            else:
                stance = "사기"
                human = (
                    f"사기 {buy_slots}순위 · 여유 {up:g}% · "
                    f"오늘≤{today_n} · ≤33%"
                )
                prog = f"오늘 슬롯 {buy_slots}/{today_n}"
        else:
            stance = "보류"
            human = f"보류 · 오늘 한도 {today_n} 밖 · 여유 {up:g}%"
            prog = "한도 밖"
            slot = False
        out.append(
            SoftTradeHint(
                ticker=tk,
                name=name,
                rank=i,
                stance=stance,
                human_ko=human,
                program_ko=prog,
                upside_pct=up,
                target_kind=kind,
                today_slot=slot,
            )
        )
    return out


def hints_by_ticker(hints: Sequence[SoftTradeHint]) -> dict[str, SoftTradeHint]:
    return {h.ticker: h for h in hints}


def activist_human_default(
    *,
    upside_soft_pct: float | None = None,
    weak_6m: bool = False,
    today_rank: int | None = None,
    today_max: int = 1,
) -> str:
    """행동주의 사람 열 기본 · Soft와 합산 금지."""
    if weak_6m:
        return "보류 · 6M 약세 · Soft컷 유의 · 합산 금지"
    if today_rank is not None and today_rank <= max(1, int(today_max)):
        return (
            f"시드 Review {today_rank}순위 · 오늘≤{today_max} · "
            "Soft와 합산 금지 · ≤33%"
        )
    return "보류 · 오늘 한도 밖 · Soft와 합산 금지"


__all__ = [
    "COND_UPSIDE_PCT",
    "THIN_UPSIDE_PCT",
    "SoftTradeHint",
    "activist_human_default",
    "hints_by_ticker",
    "rank_soft_trade_hints",
]
