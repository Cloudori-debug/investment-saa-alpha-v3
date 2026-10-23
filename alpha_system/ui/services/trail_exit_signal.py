"""L1 trail take-profit Review — peak drawdown · docs/TRAIL_EXIT_REVIEW_SPEC.md

Review-only · never writes target_portfolio.csv.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence

from alpha_system.ui.services.ops_exit_signal import OpsExitSignal, OpsSignalKind

TrailKind = Literal["hold", "trim", "cash_half", "exit_full"]

# Operator-approved defaults (2026-10-21)
T1 = 0.12
T2 = 0.20
T3 = 0.28
DEFAULT_LOOKBACK = 120

_STRENGTH: dict[str, int] = {
    "hold": 0,
    "missing": 0,
    "invalid": 0,
    "trim": 1,
    "cash_half": 2,
    "exit_full": 3,
}


@dataclass(frozen=True)
class TrailExitSignal:
    kind: TrailKind
    label: str
    detail: str
    trim_pct: Optional[int]
    peak: float
    last: float
    drawdown: float
    channel_break: bool = False
    step_id: str = "L1"


def peak_drawdown(
    highs: Sequence[float],
    last: float,
) -> tuple[float, float]:
    """Return (peak, drawdown 0..1)."""
    vals = [float(h) for h in highs if h is not None and float(h) > 0]
    if not vals or last <= 0:
        return 0.0, 0.0
    peak = max(vals)
    if peak <= 0:
        return 0.0, 0.0
    dd = max(0.0, (peak - float(last)) / peak)
    return peak, dd


def channel_break_close(closes: Sequence[float], *, window: int = 60) -> bool:
    if len(closes) < window + 1:
        return False
    prior = [float(c) for c in closes[-(window + 1) : -1] if float(c) > 0]
    last = float(closes[-1])
    if not prior or last <= 0:
        return False
    return last < min(prior)


def classify_trail_exit(
    *,
    highs: Sequence[float],
    closes: Sequence[float],
    last: float | None = None,
    t1: float = T1,
    t2: float = T2,
    t3: float = T3,
    use_channel: bool = True,
) -> TrailExitSignal:
    px = float(last) if last is not None else (float(closes[-1]) if closes else 0.0)
    peak, dd = peak_drawdown(highs, px)
    ch = channel_break_close(closes) if use_channel else False

    if peak <= 0 or px <= 0:
        return TrailExitSignal(
            kind="hold",
            label="유지",
            detail="트레일 데이터 없음",
            trim_pct=None,
            peak=peak,
            last=px,
            drawdown=0.0,
        )

    # Spec §3.1: T3 OR channel break → exit_full
    if dd >= t3 or ch:
        kind: TrailKind = "exit_full"
        if ch and dd < t3:
            label = "채널이탈"
            detail = f"채널이탈 · 고점대비 −{dd * 100:.1f}% · 전량 Review"
        else:
            label = "트레일전량"
            detail = f"고점대비 −{dd * 100:.1f}% · 전량 Review"
            if ch:
                detail = f"채널이탈 · 고점대비 −{dd * 100:.1f}% · 전량 Review"
        return TrailExitSignal(
            kind=kind,
            label=label,
            detail=detail,
            trim_pct=100,
            peak=peak,
            last=px,
            drawdown=dd,
            channel_break=ch,
        )

    if dd >= t2:
        return TrailExitSignal(
            kind="cash_half",
            label="트레일환금",
            detail=f"고점대비 −{dd * 100:.1f}% · 환금 절반 Review",
            trim_pct=50,
            peak=peak,
            last=px,
            drawdown=dd,
            channel_break=ch,
        )

    if dd >= t1:
        return TrailExitSignal(
            kind="trim",
            label="트레일줄이기",
            detail=f"고점대비 −{dd * 100:.1f}% · 줄이기 ¼ Review",
            trim_pct=25,
            peak=peak,
            last=px,
            drawdown=dd,
            channel_break=ch,
        )

    return TrailExitSignal(
        kind="hold",
        label="유지",
        detail=f"고점대비 −{dd * 100:.1f}% · T1({t1 * 100:.0f}%) 미만",
        trim_pct=None,
        peak=peak,
        last=px,
        drawdown=dd,
        channel_break=ch,
    )


def trail_from_snapshot(
    *,
    close: float | None,
    high_52w: float | None = None,
    closes: Sequence[float] | None = None,
    highs: Sequence[float] | None = None,
    t1: float = T1,
    t2: float = T2,
    t3: float = T3,
) -> TrailExitSignal | None:
    """Build L1 from holding/lookback highs — never from high_52w alone.

    Spec peak = 편입 후(또는 감시 N일) 조정 고가. ``prices.csv`` 스냅샷의
    high_52w 를 peak로 쓰면 ATH 대비 되돌림이 대부분 T3(전량)로 과다 발화한다.
    high_52w 인자는 호환용으로 받되 peak에 쓰지 않는다.
    """
    del high_52w  # explicit: not a trail peak
    last = float(close) if close is not None and float(close) > 0 else 0.0
    if last <= 0:
        return None
    hi_list = [float(h) for h in (highs or ()) if h is not None and float(h) > 0]
    cl_list = [float(c) for c in (closes or ()) if c is not None and float(c) > 0]
    # Need real peak series (or close history thick enough to stand in)
    if len(hi_list) < 2 and len(cl_list) < 20:
        return None
    if not hi_list:
        hi_list = list(cl_list)
    if not cl_list:
        cl_list = [last]
    return classify_trail_exit(
        highs=hi_list,
        closes=cl_list,
        last=last,
        t1=t1,
        t2=t2,
        t3=t3,
        use_channel=len(cl_list) >= 61,
    )


def _to_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        x = float(v)
        return x if x == x and x > 0 else None
    except (TypeError, ValueError):
        return None


def load_trail_snapshot_map(
    prices_df: Any,
) -> dict[str, tuple[float, float | None]]:
    """ticker → (close, high_52w|None) from prices snapshot DataFrame."""
    out: dict[str, tuple[float, float | None]] = {}
    if prices_df is None:
        return out
    try:
        empty = prices_df.empty
    except Exception:
        return out
    if empty or "ticker" not in getattr(prices_df, "columns", []):
        return out
    for _, row in prices_df.iterrows():
        t = str(row.get("ticker") or "").strip()
        if t.isdigit():
            t = t.zfill(6)
        if not t:
            continue
        close = _to_float(row.get("close") or row.get("current_price") or row.get("price"))
        if close is None:
            continue
        high = _to_float(row.get("high_52w") or row.get("high"))
        out[t] = (close, high)
    return out


def merge_l0_l1(l0: OpsExitSignal, l1: TrailExitSignal | None) -> OpsExitSignal:
    """Stronger of L0 vs L1; L0 exit_full / S0 always wins (§3.4)."""
    if l1 is None or l1.kind == "hold":
        return l0
    if l0.step_id == "S0" or l0.kind == "exit_full":
        if l1.kind == "exit_full" and l0.kind == "exit_full":
            return OpsExitSignal(
                kind=l0.kind,
                label=l0.label,
                detail=f"{l0.detail} · {l1.detail}",
                trim_pct=l0.trim_pct,
                proximity_pct=l0.proximity_pct,
                exit_leg=l0.exit_leg,
                rationale=f"{l0.rationale}|L1",
                step_id=l0.step_id,
            )
        return l0
    s0 = _STRENGTH.get(l0.kind, 0)
    s1 = _STRENGTH.get(l1.kind, 0)
    if s1 > s0:
        kind: OpsSignalKind = l1.kind  # type: ignore[assignment]
        return OpsExitSignal(
            kind=kind,
            label=l1.label,
            detail=l1.detail,
            trim_pct=l1.trim_pct,
            proximity_pct=l0.proximity_pct,
            exit_leg=l0.exit_leg,
            rationale=f"L1:{l1.detail}",
            step_id=l1.step_id,
        )
    if s1 == s0 and s1 > 0:
        return OpsExitSignal(
            kind=l0.kind,
            label=l0.label,
            detail=f"{l0.detail} · {l1.detail}",
            trim_pct=l0.trim_pct if l0.trim_pct is not None else l1.trim_pct,
            proximity_pct=l0.proximity_pct,
            exit_leg=l0.exit_leg,
            rationale=f"{l0.rationale}|L1",
            step_id=l0.step_id or l1.step_id,
        )
    return l0


def trail_params_from_defaults(defaults: Mapping[str, Any] | None) -> tuple[float, float, float]:
    d = defaults or {}
    trail = d.get("trail") if isinstance(d.get("trail"), dict) else {}
    t1 = float(trail.get("t1", d.get("trail_t1", T1)))
    t2 = float(trail.get("t2", d.get("trail_t2", T2)))
    t3 = float(trail.get("t3", d.get("trail_t3", T3)))
    return t1, t2, t3


__all__ = [
    "T1",
    "T2",
    "T3",
    "DEFAULT_LOOKBACK",
    "TrailExitSignal",
    "peak_drawdown",
    "channel_break_close",
    "classify_trail_exit",
    "trail_from_snapshot",
    "load_trail_snapshot_map",
    "merge_l0_l1",
    "trail_params_from_defaults",
]
