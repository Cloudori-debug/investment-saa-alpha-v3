"""L3 crash defense + re-entry ladder — Review-only.

docs/CRASH_DEFENSE_REENTRY_SPEC.md · docs/TRAIL_EXIT_REVIEW_SPEC.md
Never writes target_portfolio.csv · never exit_full from L3 alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Sequence

from alpha_system.ui.services.ops_exit_signal import OpsExitSignal, OpsSignalKind
from alpha_system.ui.services.trail_exit_signal import (
    T2 as L1_T2,
    TrailExitSignal,
    merge_l0_l1,
)

CrashKind = Literal["hold", "trim", "cash_half"]

# Operator-approved draft (2026-10-23)
C1 = -0.12
C2 = -0.18
C3 = -0.25
CRASH_LOOKBACK = 5
R1 = 0.06
R2 = 0.12
R3 = 0.18
RECLAIM_HIGH_DAYS = 20

TRIM_NOTE_REL = Path("data") / "local" / "crash_defense_trim.json"

_STRENGTH: dict[str, int] = {
    "hold": 0,
    "missing": 0,
    "invalid": 0,
    "trim": 1,
    "cash_half": 2,
    "exit_full": 3,
}


@dataclass(frozen=True)
class CrashDefenseSignal:
    kind: CrashKind
    label: str
    detail: str
    trim_pct: Optional[int]
    ret_nd: float
    n_days: int
    crash_low: float
    last: float
    code: str  # hold | C1 | C2 | C3
    suggest_full_review: bool = False
    step_id: str = "L3"


@dataclass(frozen=True)
class ReentryRung:
    id: str  # R1 | R2 | R3
    price: float
    fraction: float  # of trimmed quantity
    label_ko: str
    hit: bool


@dataclass(frozen=True)
class ReentryLadder:
    crash_low: float
    last: float
    trim_frac: float
    rungs: tuple[ReentryRung, ...]
    high_20d: float | None
    active_rung: str  # next to buy or DONE
    review_only: bool = True


def n_day_return(closes: Sequence[float], *, n: int = CRASH_LOOKBACK) -> float | None:
    """(last / close[-n-1]) - 1 over n sessions. Needs n+1 points."""
    vals = [float(c) for c in closes if c is not None and float(c) > 0]
    if len(vals) < n + 1:
        return None
    base = vals[-(n + 1)]
    last = vals[-1]
    if base <= 0 or last <= 0:
        return None
    return (last / base) - 1.0


def crash_window_low(closes: Sequence[float], *, n: int = CRASH_LOOKBACK) -> float:
    vals = [float(c) for c in closes if c is not None and float(c) > 0]
    if not vals:
        return 0.0
    window = vals[-(n + 1) :] if len(vals) >= n + 1 else vals
    return min(window) if window else 0.0


def classify_crash_defense(
    closes: Sequence[float],
    *,
    last: float | None = None,
    l1_drawdown: float | None = None,
    c1: float = C1,
    c2: float = C2,
    c3: float = C3,
    n: int = CRASH_LOOKBACK,
    l1_t2: float = L1_T2,
) -> CrashDefenseSignal:
    vals = [float(c) for c in closes if c is not None and float(c) > 0]
    px = float(last) if last is not None and float(last) > 0 else (vals[-1] if vals else 0.0)
    ret = n_day_return(vals, n=n)
    low = crash_window_low(vals, n=n)

    if ret is None or px <= 0 or low <= 0:
        return CrashDefenseSignal(
            kind="hold",
            label="유지",
            detail="급락 데이터 없음",
            trim_pct=None,
            ret_nd=0.0,
            n_days=n,
            crash_low=low,
            last=px,
            code="hold",
        )

    ret_pct = ret * 100.0
    l1_boost = (
        l1_drawdown is not None
        and float(l1_drawdown) >= float(l1_t2)
        and ret <= c1
    )

    if ret <= c3:
        return CrashDefenseSignal(
            kind="cash_half",
            label="급락환금",
            detail=(
                f"{n}일 {ret_pct:.1f}% · 환금 절반 Review · "
                "전량 검토(강제 아님) · L3"
            ),
            trim_pct=50,
            ret_nd=ret,
            n_days=n,
            crash_low=low,
            last=px,
            code="C3",
            suggest_full_review=True,
        )

    if ret <= c2 or l1_boost:
        why = (
            f"{n}일 {ret_pct:.1f}%"
            if ret <= c2
            else f"{n}일 {ret_pct:.1f}% + L1고점−{float(l1_drawdown) * 100:.0f}%"
        )
        return CrashDefenseSignal(
            kind="cash_half",
            label="급락환금",
            detail=f"{why} · 환금 절반 Review · L3",
            trim_pct=50,
            ret_nd=ret,
            n_days=n,
            crash_low=low,
            last=px,
            code="C2",
        )

    if ret <= c1:
        return CrashDefenseSignal(
            kind="trim",
            label="급락줄이기",
            detail=f"{n}일 {ret_pct:.1f}% · 줄이기 ¼ Review · L3",
            trim_pct=25,
            ret_nd=ret,
            n_days=n,
            crash_low=low,
            last=px,
            code="C1",
        )

    return CrashDefenseSignal(
        kind="hold",
        label="유지",
        detail=f"{n}일 {ret_pct:.1f}% · C1({c1 * 100:.0f}%) 미만",
        trim_pct=None,
        ret_nd=ret,
        n_days=n,
        crash_low=low,
        last=px,
        code="hold",
    )


def build_reentry_ladder(
    *,
    crash_low: float,
    last: float,
    trim_frac: float,
    closes: Sequence[float] | None = None,
    r1: float = R1,
    r2: float = R2,
    r3: float = R3,
    reclaim_days: int = RECLAIM_HIGH_DAYS,
) -> ReentryLadder | None:
    if crash_low <= 0 or last <= 0 or trim_frac <= 0:
        return None
    vals = [float(c) for c in (closes or ()) if c is not None and float(c) > 0]
    high_20: float | None = None
    if len(vals) >= reclaim_days:
        high_20 = max(vals[-reclaim_days:])

    p1 = crash_low * (1.0 + r1)
    p2 = crash_low * (1.0 + r2)
    p3 = crash_low * (1.0 + r3)
    # 20일 고가 회복: 고가가 급락 저점보다  meaningfully 높을 때만 (평탄 구간 오발화 방지)
    reclaim = (
        high_20 is not None
        and high_20 > crash_low * (1.0 + r1)
        and last >= high_20
    )

    hit1 = last >= p1
    hit2 = last >= p2 or reclaim
    hit3 = last >= p3

    rungs = (
        ReentryRung("R1", p1, 1.0 / 3.0, f"저점+{r1 * 100:.0f}% · ⅓", hit1),
        ReentryRung(
            "R2",
            p2,
            1.0 / 3.0,
            f"저점+{r2 * 100:.0f}% 또는 {reclaim_days}일고가 · ⅓",
            hit2,
        ),
        ReentryRung("R3", p3, 1.0 / 3.0, f"저점+{r3 * 100:.0f}% · 잔여", hit3),
    )
    if hit3:
        active = "DONE"
    elif hit2:
        active = "R3"
    elif hit1:
        active = "R2"
    else:
        active = "R1"
    return ReentryLadder(
        crash_low=crash_low,
        last=last,
        trim_frac=float(trim_frac),
        rungs=rungs,
        high_20d=high_20,
        active_rung=active,
    )


def merge_l0_l1_l3(
    l0: OpsExitSignal,
    l1: TrailExitSignal | None,
    l3: CrashDefenseSignal | None,
) -> OpsExitSignal:
    """L3 never alone → exit_full. Stronger trim/half merges with L0+L1."""
    base = merge_l0_l1(l0, l1)
    if l3 is None or l3.kind == "hold":
        return base
    if base.kind == "exit_full" or base.step_id == "S0":
        return OpsExitSignal(
            kind=base.kind,
            label=base.label,
            detail=f"{base.detail} · {l3.detail}",
            trim_pct=base.trim_pct,
            proximity_pct=base.proximity_pct,
            exit_leg=base.exit_leg,
            rationale=f"{base.rationale}|L3",
            step_id=base.step_id,
        )

    s_base = _STRENGTH.get(base.kind, 0)
    s3 = _STRENGTH.get(l3.kind, 0)
    # Cap L3 at cash_half
    if s3 > 2:
        s3 = 2
    if s3 > s_base:
        kind: OpsSignalKind = l3.kind  # type: ignore[assignment]
        return OpsExitSignal(
            kind=kind,
            label=l3.label,
            detail=l3.detail,
            trim_pct=l3.trim_pct,
            proximity_pct=base.proximity_pct,
            exit_leg=base.exit_leg,
            rationale=f"L3:{l3.detail}",
            step_id=l3.step_id,
        )
    if s3 == s_base and s3 > 0:
        return OpsExitSignal(
            kind=base.kind,
            label=base.label if base.label else l3.label,
            detail=f"{base.detail} · {l3.detail}",
            trim_pct=base.trim_pct if base.trim_pct is not None else l3.trim_pct,
            proximity_pct=base.proximity_pct,
            exit_leg=base.exit_leg,
            rationale=f"{base.rationale}|L3",
            step_id=base.step_id or l3.step_id,
        )
    return base


def _norm_ticker(raw: object) -> str:
    text = str(raw or "").strip()
    if text.isdigit():
        return text.zfill(6)
    return text


def load_closes_by_ticker(
    root: Path,
    tickers: Sequence[str] | None = None,
    *,
    n: int = 40,
) -> dict[str, list[float]]:
    """Batch load recent closes from data/prices.csv."""
    path = Path(root) / "data" / "prices.csv"
    if not path.exists():
        return {}
    want: set[str] | None = None
    if tickers is not None:
        want = {_norm_ticker(t) for t in tickers if t}
    try:
        import pandas as pd

        df = pd.read_csv(path, usecols=lambda c: c in {"date", "ticker", "close"})
    except Exception:
        return {}
    if df.empty or "ticker" not in df.columns or "close" not in df.columns:
        return {}
    df = df.copy()
    df["ticker"] = df["ticker"].map(_norm_ticker)
    if want is not None:
        df = df[df["ticker"].isin(want)]
    if "date" in df.columns:
        df["_date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["_date"]).sort_values("_date")
    df["_close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["_close"])
    df = df[df["_close"] > 0]
    out: dict[str, list[float]] = {}
    for t, g in df.groupby("ticker", sort=False):
        closes = [float(x) for x in g["_close"].tolist()[-n:]]
        if closes:
            out[str(t)] = closes
    return out


def load_trim_notes(root: Path) -> dict[str, dict[str, Any]]:
    path = Path(root) / TRIM_NOTE_REL
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw = data.get("tickers") if isinstance(data.get("tickers"), dict) else data
    out: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                out[_norm_ticker(k)] = v
    return out


def save_trim_note(
    root: Path,
    ticker: str,
    *,
    crash_low: float,
    trim_frac: float,
    note: str = "",
) -> Path:
    path = Path(root) / TRIM_NOTE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_trim_notes(root)
    t = _norm_ticker(ticker)
    existing[t] = {
        "crash_low": crash_low,
        "trim_frac": trim_frac,
        "note": note,
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "review_only": True,
    }
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tickers": existing,
        "never_writes_target": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def ladder_as_extra(ladder: ReentryLadder | None) -> dict[str, Any]:
    if ladder is None:
        return {}
    return {
        "reentry_crash_low": ladder.crash_low,
        "reentry_trim_frac": ladder.trim_frac,
        "reentry_active": ladder.active_rung,
        "reentry_rungs": [
            {
                "id": r.id,
                "price": round(r.price, 2),
                "fraction": r.fraction,
                "label": r.label_ko,
                "hit": r.hit,
            }
            for r in ladder.rungs
        ],
        "reentry_high_20d": ladder.high_20d,
    }


def crash_params_from_defaults(defaults: Mapping[str, Any] | None) -> tuple[float, float, float, int]:
    d = defaults or {}
    crash = d.get("crash") if isinstance(d.get("crash"), dict) else {}
    c1 = float(crash.get("c1", d.get("crash_c1", C1)))
    c2 = float(crash.get("c2", d.get("crash_c2", C2)))
    c3 = float(crash.get("c3", d.get("crash_c3", C3)))
    n = int(crash.get("n_days", d.get("crash_n_days", CRASH_LOOKBACK)))
    return c1, c2, c3, n


__all__ = [
    "C1",
    "C2",
    "C3",
    "CRASH_LOOKBACK",
    "CrashDefenseSignal",
    "ReentryLadder",
    "ReentryRung",
    "n_day_return",
    "crash_window_low",
    "classify_crash_defense",
    "build_reentry_ladder",
    "merge_l0_l1_l3",
    "load_closes_by_ticker",
    "load_trim_notes",
    "save_trim_note",
    "ladder_as_extra",
    "crash_params_from_defaults",
]
