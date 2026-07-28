"""Momentum Review-only execution grades — no auto orders / no target writes.

Uses precomputed returns on data/prices.csv (return_12m_ex_1m = 12-1 proxy).
Grades: GO / SLOW / WAIT / CUT_PACE → SCALE_IN pace advice for the operator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

Grade = Literal["GO", "SLOW", "WAIT", "CUT_PACE"]
Tone = Literal["ok", "warn", "danger", "muted"]
Decision = Literal["execute", "hold", "unset"]

CROSS_GO = 60.0
CROSS_WAIT = 40.0
VOL_HIGH_PCTILE = 80.0

GRADE_KO: dict[Grade, str] = {
    "GO": "진행",
    "SLOW": "천천히",
    "WAIT": "관망",
    "CUT_PACE": "추가매수 중지",
}

GRADE_ADVICE: dict[Grade, str] = {
    "GO": "3회 균등 분할매수",
    "SLOW": "느리게(2회 또는 1회만)",
    "WAIT": "이번엔 사지 않음",
    "CUT_PACE": "남은 분할매수 중단 · 보유분만",
}


@dataclass(frozen=True)
class MomentumReviewItem:
    ticker: str
    name: str
    as_of: str
    ret_12_1: float | None
    ret_6: float | None
    ret_3: float | None
    cross_pct: float | None
    absolute: Literal["UP", "DOWN", "—"]
    vol_60d: float | None
    vol_high: bool
    grade: Grade
    advice: str
    reason: str
    tone: Tone
    execute_allowed: bool
    last_decision: Decision
    last_decision_at: str | None = None


@dataclass(frozen=True)
class MomentumReviewBoard:
    as_of: date
    price_as_of: str
    regime_label: str
    crisis: bool
    cadence_note: str
    items: tuple[MomentumReviewItem, ...]
    summary: str


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _pctile_rank(value: float, values: Sequence[float]) -> float:
    """Percentile 0–100 of value within values (average rank)."""
    if not values:
        return 50.0
    n = len(values)
    below = sum(1 for x in values if x < value)
    equal = sum(1 for x in values if x == value)
    return 100.0 * (below + 0.5 * equal) / n


def _aux_ok(ret_6: float | None, ret_3: float | None, absolute: str) -> bool:
    """True if auxiliaries do not clearly contradict UP 12-1."""
    if absolute != "UP":
        return True
    signs = [r for r in (ret_6, ret_3) if r is not None]
    if not signs:
        return True
    return any(r >= 0 for r in signs)


def classify_momentum_grade(
    *,
    ret_12_1: float | None,
    ret_6: float | None,
    ret_3: float | None,
    cross_pct: float | None,
    vol_high: bool,
    crisis: bool,
) -> tuple[Grade, str]:
    """Return (grade, reason). Priority: WAIT → CUT_PACE → GO → SLOW."""
    if ret_12_1 is None or cross_pct is None:
        return "WAIT", "가격/12-1 결측 → 매수 보류"

    absolute = "UP" if ret_12_1 > 0 else "DOWN"

    if absolute == "DOWN" or cross_pct < CROSS_WAIT:
        return (
            "WAIT",
            f"절대 {absolute} · 교차 {cross_pct:.0f}%ile (<{CROSS_WAIT:.0f} 또는 DOWN) → 보류",
        )

    if crisis or vol_high:
        why = "CRISIS" if crisis else f"변동성 상위(≥{VOL_HIGH_PCTILE:.0f}%ile)"
        return "CUT_PACE", f"{why} → 잔여 분할매수 중지 권고"

    aux = _aux_ok(ret_6, ret_3, absolute)
    if cross_pct >= CROSS_GO and absolute == "UP" and aux:
        return (
            "GO",
            f"12-1 교차 {cross_pct:.0f}%ile · UP · 변동성 정상 · 보조 비모순 → 3회 균등",
        )

    bits = []
    if cross_pct < CROSS_GO:
        bits.append(f"교차 {cross_pct:.0f}%ile (중간)")
    if not aux:
        bits.append("3M/6M 약세")
    return "SLOW", (" · ".join(bits) or "중간 신호") + " → 속도 축소"


def _load_price_rows(root: Path) -> tuple[str, dict[str, dict[str, float | None]]]:
    """Latest row per ticker from prices.csv → metrics map. Returns (max_date, map)."""
    path = root / "data" / "prices.csv"
    if not path.exists():
        return "", {}
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype={"ticker": str})
    except Exception:
        return "", {}
    if df.empty or "ticker" not in df.columns:
        return "", {}
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    if "date" in df.columns:
        df = df.sort_values("date")
        price_as_of = str(df["date"].iloc[-1])[:10]
        df = df.drop_duplicates("ticker", keep="last")
    else:
        price_as_of = ""
    out: dict[str, dict[str, float | None]] = {}
    for _, row in df.iterrows():
        tk = str(row.get("ticker") or "").zfill(6)
        out[tk] = {
            "ret_12_1": _f(row.get("return_12m_ex_1m")),
            "ret_6": _f(row.get("return_6m")),
            "ret_3": _f(row.get("return_3m")),
            "vol_60d": _f(row.get("volatility_60d")),
        }
    return price_as_of, out


def _universe_cross_and_vol(
    price_map: Mapping[str, Mapping[str, float | None]],
) -> tuple[dict[str, float], set[str]]:
    """cross_pct by ticker; set of tickers with vol_high."""
    ret_pairs = [
        (tk, m["ret_12_1"])
        for tk, m in price_map.items()
        if m.get("ret_12_1") is not None
    ]
    rets = [float(v) for _, v in ret_pairs if v is not None]
    cross: dict[str, float] = {}
    for tk, v in ret_pairs:
        if v is None:
            continue
        cross[tk] = _pctile_rank(float(v), rets)

    vol_pairs = [
        (tk, m["vol_60d"])
        for tk, m in price_map.items()
        if m.get("vol_60d") is not None and float(m["vol_60d"] or 0) > 0
    ]
    vols = [float(v) for _, v in vol_pairs if v is not None]
    high: set[str] = set()
    if vols:
        for tk, v in vol_pairs:
            if v is None:
                continue
            if _pctile_rank(float(v), vols) >= VOL_HIGH_PCTILE:
                high.add(tk)
    return cross, high


def _subject_tickers(ctx: Any, root: Path) -> dict[str, str]:
    """ticker → name from ops ∪ proposal ∪ scale_in_open."""
    names: dict[str, str] = {}
    for attr in ("ops_portfolio_rows", "portfolio_rows"):
        for r in list(getattr(ctx, attr, None) or []):
            tk = str(getattr(r, "ticker", "") or "").zfill(6)
            if not tk.strip("0"):
                continue
            names[tk] = str(getattr(r, "name", None) or tk)
    # scale_in_open.json
    path = root / "data" / "scale_in_open.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            tickers = raw.get("tickers") if isinstance(raw, dict) else raw
            if isinstance(tickers, list):
                for t in tickers:
                    tk = str(t).zfill(6)
                    if tk.strip("0"):
                        names.setdefault(tk, tk)
        except (OSError, ValueError, TypeError):
            pass
    return names


def _recent_decisions(root: Path) -> dict[str, tuple[Decision, str]]:
    """Latest MOMENTUM_EXECUTE/HOLD per ticker from system journal."""
    path = root / "data" / "alpha_system_journal.jsonl"
    if not path.exists():
        return {}
    out: dict[str, tuple[Decision, str]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-400:]
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = str(row.get("action_kind") or "")
        if kind == "MOMENTUM_EXECUTE":
            dec: Decision = "execute"
        elif kind == "MOMENTUM_HOLD":
            dec = "hold"
        else:
            continue
        tk = str(row.get("subject") or "").zfill(6)
        if not tk.strip("0"):
            continue
        at = str(row.get("recorded_at") or row.get("as_of") or "")
        out[tk] = (dec, at)
    return out


def grade_tone(grade: Grade) -> Tone:
    if grade == "GO":
        return "ok"
    if grade == "SLOW":
        return "warn"
    if grade == "WAIT":
        return "danger"
    return "muted"


def build_momentum_review_board(
    ctx: Any,
    *,
    as_of: date | None = None,
) -> MomentumReviewBoard:
    as_of = as_of or getattr(ctx, "as_of", None) or date.today()
    root = Path(ctx.root)

    from alpha_system.ui.services.v2_chrome import regime_info

    reg = regime_info(root)
    regime_label = str(reg.get("label") or reg.get("regime") or "—")
    crisis = "CRISIS" in regime_label.upper() or bool(reg.get("crisis"))

    price_as_of, price_map = _load_price_rows(root)
    cross, vol_high_set = _universe_cross_and_vol(price_map)
    subjects = _subject_tickers(ctx, root)
    decisions = _recent_decisions(root)

    items: list[MomentumReviewItem] = []
    for tk, name in sorted(subjects.items(), key=lambda x: x[0]):
        m = price_map.get(tk) or {}
        ret_12 = m.get("ret_12_1")
        ret_6 = m.get("ret_6")
        ret_3 = m.get("ret_3")
        vol = m.get("vol_60d")
        cp = cross.get(tk)
        vh = tk in vol_high_set
        grade, reason = classify_momentum_grade(
            ret_12_1=ret_12,
            ret_6=ret_6,
            ret_3=ret_3,
            cross_pct=cp,
            vol_high=vh,
            crisis=crisis,
        )
        absolute: Literal["UP", "DOWN", "—"]
        if ret_12 is None:
            absolute = "—"
        else:
            absolute = "UP" if ret_12 > 0 else "DOWN"
        last = decisions.get(tk)
        items.append(
            MomentumReviewItem(
                ticker=tk,
                name=name,
                as_of=price_as_of or as_of.isoformat(),
                ret_12_1=ret_12,
                ret_6=ret_6,
                ret_3=ret_3,
                cross_pct=cp,
                absolute=absolute,
                vol_60d=vol,
                vol_high=vh,
                grade=grade,
                advice=GRADE_ADVICE[grade],
                reason=reason,
                tone=grade_tone(grade),
                execute_allowed=grade != "WAIT",
                last_decision=last[0] if last else "unset",
                last_decision_at=last[1] if last else None,
            )
        )

    go_n = sum(1 for i in items if i.grade == "GO")
    wait_n = sum(1 for i in items if i.grade in ("WAIT", "CUT_PACE"))
    if not items:
        summary = "판정 대상 없음 (보유·후보·SCALE_IN 없음)"
    else:
        summary = (
            f"{len(items)}종 · GO {go_n} · WAIT/CUT {wait_n} · "
            "주간·회차일 집행 · 자동매매 없음"
        )

    return MomentumReviewBoard(
        as_of=as_of,
        price_as_of=price_as_of or "—",
        regime_label=regime_label,
        crisis=crisis,
        cadence_note=(
            "신호=prices.csv 최신 종가 · 매일 확인만 · "
            "매매 결정은 주간 또는 SCALE_IN 회차일"
        ),
        items=tuple(items),
        summary=summary,
    )


def record_momentum_decision(
    *,
    ticker: str,
    grade: Grade,
    decision: Literal["execute", "hold"],
    advice: str,
    as_of: date | None = None,
    rationale: str = "",
) -> None:
    """Append operator decision — does not place orders or write target."""
    from alpha_system.journal import append_record

    kind = "MOMENTUM_EXECUTE" if decision == "execute" else "MOMENTUM_HOLD"
    append_record(
        action_kind=kind,
        as_of=as_of or date.today(),
        subject=str(ticker).zfill(6),
        rationale=rationale or f"momentum {grade} → {decision}",
        payload={
            "grade": grade,
            "advice": advice,
            "decision": decision,
            "review_only": True,
        },
        trigger_snapshot={"source": "momentum_review_board"},
    )
