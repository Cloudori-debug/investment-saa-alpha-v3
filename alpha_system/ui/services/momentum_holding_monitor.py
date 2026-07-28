"""Momentum Holding Monitor (MHM) — Review-only UP/DOWN bearing for holdings.

Does not place orders or write target_portfolio.
Log: data/local/momentum_holding_log.jsonl (gitignored via data/local/).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from alpha_system.ui.services.momentum_review import (
    CROSS_GO,
    CROSS_WAIT,
    GRADE_KO,
    Grade,
    MomentumReviewBoard,
    MomentumReviewItem,
    build_momentum_review_board,
)

Bearing = Literal["ENTER_OK", "HOLD_UP", "TRIM_PACE", "EXIT_REVIEW"]
TsSign = Literal["UP", "DOWN", "—"]
XsBucket = Literal["Strong", "Mid", "Weak", "—"]

BEARING_KO: dict[Bearing, str] = {
    "ENTER_OK": "추가·진입 검토 OK",
    "HOLD_UP": "상방 유지",
    "TRIM_PACE": "속도 축소·축소 검토",
    "EXIT_REVIEW": "청산·교체 검토",
}

EXIT_STREAK_DEFAULT = 5
LOG_REL = Path("data") / "local" / "momentum_holding_log.jsonl"


@dataclass(frozen=True)
class MomentumHoldingRow:
    ticker: str
    name: str
    as_of: str
    ts_sign: TsSign
    xs_pct: float | None
    xs_bucket: XsBucket
    vol_flag: bool
    grade: Grade
    grade_ko: str
    upside: bool
    """True = UP and xs>=40 (objective upside)."""
    bearing: Bearing
    bearing_ko: str
    weak_streak: int
    """Consecutive calendar log days with DOWN or xs<40."""
    vs_prev: str
    """bearing change vs last log: ↑/↓/→/신규"""
    reason: str
    source: str
    """momentum_role | scale_in | ops_held"""


@dataclass(frozen=True)
class MomentumHoldingBoard:
    as_of: date
    price_as_of: str
    exit_streak_n: int
    rows: tuple[MomentumHoldingRow, ...]
    summary: str


def _xs_bucket(xs: float | None) -> XsBucket:
    if xs is None:
        return "—"
    if xs >= CROSS_GO:
        return "Strong"
    if xs >= CROSS_WAIT:
        return "Mid"
    return "Weak"


def classify_bearing(
    *,
    ts_sign: TsSign,
    xs_pct: float | None,
    vol_flag: bool,
    grade: Grade,
    weak_streak: int,
    exit_streak_n: int = EXIT_STREAK_DEFAULT,
) -> tuple[Bearing, str]:
    """Review-only bearing. EXIT_REVIEW needs weak_streak >= N."""
    weak_now = ts_sign == "DOWN" or (xs_pct is not None and xs_pct < CROSS_WAIT)
    if weak_now and weak_streak >= exit_streak_n:
        return (
            "EXIT_REVIEW",
            f"하방/약세 {weak_streak}일≥{exit_streak_n} → 청산·교체 검토(자동매도 아님)",
        )
    if grade == "CUT_PACE" or vol_flag or grade == "SLOW":
        why = []
        if grade == "CUT_PACE":
            why.append("CUT_PACE")
        if vol_flag:
            why.append("고변동")
        if grade == "SLOW":
            why.append("SLOW")
        return "TRIM_PACE", " · ".join(why) + " → 분할 중단·축소 검토"
    if (
        ts_sign == "UP"
        and xs_pct is not None
        and xs_pct >= CROSS_GO
        and not vol_flag
        and grade == "GO"
    ):
        return "ENTER_OK", "UP · 교차≥60 · GO → 추가·진입 검토 OK"
    if ts_sign == "UP" and xs_pct is not None and xs_pct >= CROSS_WAIT and grade != "CUT_PACE":
        return "HOLD_UP", "UP · 교차≥40 → 상방 유지"
    if weak_now:
        return (
            "TRIM_PACE",
            f"하방/약세 {weak_streak}일(<{exit_streak_n}) → 속도 축소·관찰",
        )
    return "HOLD_UP", "중간 신호 → 유지 관찰"


def _load_score_roles(root: Path) -> dict[str, str]:
    path = root / "alpha_portfolio" / "data" / "output" / "alpha_scores.csv"
    if not path.exists():
        return {}
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str)
    except Exception:
        return {}
    if df.empty or "ticker" not in df.columns:
        return {}
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        tk = str(row.get("ticker") or "").zfill(6)
        role = str(row.get("role_suggested") or "")
        tier = str(row.get("tier") or "")
        sat = str(row.get("satellite_track") or "").lower()
        tag = role
        if sat in {"true", "1", "yes"} or "satellite" in tier.lower():
            tag = f"{role}|satellite"
        out[tk] = tag
    return out


def _scale_in_tickers(root: Path) -> set[str]:
    path = root / "data" / "scale_in_open.json"
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        tickers = raw.get("tickers") if isinstance(raw, dict) else raw
        if not isinstance(tickers, list):
            return set()
        return {str(t).zfill(6) for t in tickers if str(t).strip()}
    except (OSError, ValueError, TypeError):
        return set()


def _is_momentum_role(tag: str) -> bool:
    t = tag.lower()
    return "momentum" in t


def select_monitor_subjects(
    ctx: Any,
    *,
    include_all_ops: bool = False,
) -> dict[str, tuple[str, str]]:
    """ticker → (name, source)."""
    root = Path(ctx.root)
    roles = _load_score_roles(root)
    scale = _scale_in_tickers(root)
    out: dict[str, tuple[str, str]] = {}

    for r in list(getattr(ctx, "ops_portfolio_rows", None) or []):
        tk = str(getattr(r, "ticker", "") or "").zfill(6)
        if not tk.strip("0"):
            continue
        name = str(getattr(r, "name", None) or tk)
        extra_role = str((getattr(r, "extra", None) or {}).get("role") or "")
        tag = roles.get(tk) or extra_role
        if include_all_ops or _is_momentum_role(tag) or _is_momentum_role(extra_role):
            src = "momentum_role" if _is_momentum_role(tag) or _is_momentum_role(extra_role) else "ops_held"
            out[tk] = (name, src)

    for tk in scale:
        if tk not in out:
            # Prefer name from ops/proposal
            name = tk
            for attr in ("ops_portfolio_rows", "portfolio_rows"):
                for r in list(getattr(ctx, attr, None) or []):
                    if str(getattr(r, "ticker", "") or "").zfill(6) == tk:
                        name = str(getattr(r, "name", None) or tk)
                        break
            out[tk] = (name, "scale_in")
        else:
            name, _ = out[tk]
            out[tk] = (name, "scale_in")

    return out


def _read_log(root: Path) -> list[dict[str, Any]]:
    path = root / LOG_REL
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows


def _history_for_ticker(log: Sequence[Mapping[str, Any]], ticker: str) -> list[dict[str, Any]]:
    tk = str(ticker).zfill(6)
    return [r for r in log if str(r.get("ticker") or "").zfill(6) == tk]


def _weak_streak_from_history(
    history: Sequence[Mapping[str, Any]],
    *,
    today_weak: bool,
    today: str,
) -> int:
    """Count consecutive days ending today that were weak (DOWN or xs<40)."""
    if not today_weak:
        return 0
    # Unique as_of descending
    by_day: dict[str, dict[str, Any]] = {}
    for r in history:
        d = str(r.get("as_of") or "")[:10]
        if d:
            by_day[d] = r
    days = sorted(by_day.keys(), reverse=True)
    streak = 1  # today
    # Walk prior days
    for d in days:
        if d == today:
            continue
        prev = by_day[d]
        weak = bool(prev.get("weak"))
        if not weak:
            break
        streak += 1
    return streak


def build_momentum_holding_board(
    ctx: Any,
    *,
    mom_board: MomentumReviewBoard | None = None,
    include_all_ops: bool = False,
    exit_streak_n: int = EXIT_STREAK_DEFAULT,
    persist_log: bool = True,
) -> MomentumHoldingBoard:
    as_of = getattr(ctx, "as_of", None) or date.today()
    root = Path(ctx.root)
    mom_board = mom_board or build_momentum_review_board(ctx, as_of=as_of)
    by_tk = {i.ticker: i for i in mom_board.items}
    subjects = select_monitor_subjects(ctx, include_all_ops=include_all_ops)
    log = _read_log(root)
    today = as_of.isoformat()

    rows: list[MomentumHoldingRow] = []
    for tk, (name, source) in sorted(subjects.items()):
        item: MomentumReviewItem | None = by_tk.get(tk)
        # Build synthetic metrics if not on review board
        if item is None:
            # Re-run board already covers ops∪proposal∪scale_in; skip orphans
            continue
        ts: TsSign = item.absolute if item.absolute in ("UP", "DOWN", "—") else "—"
        xs = item.cross_pct
        bucket = _xs_bucket(xs)
        weak_now = ts == "DOWN" or (xs is not None and xs < CROSS_WAIT)
        upside = ts == "UP" and xs is not None and xs >= CROSS_WAIT
        hist = _history_for_ticker(log, tk)
        streak = _weak_streak_from_history(hist, today_weak=weak_now, today=today)
        bearing, reason = classify_bearing(
            ts_sign=ts,
            xs_pct=xs,
            vol_flag=item.vol_high,
            grade=item.grade,
            weak_streak=streak,
            exit_streak_n=exit_streak_n,
        )
        prev_bearing = None
        if hist:
            last = sorted(hist, key=lambda r: str(r.get("as_of") or ""))[-1]
            if str(last.get("as_of") or "")[:10] != today:
                prev_bearing = last.get("bearing")
            elif len(hist) >= 2:
                prev_bearing = sorted(hist, key=lambda r: str(r.get("as_of") or ""))[-2].get(
                    "bearing"
                )
        if prev_bearing is None:
            vs = "신규"
        elif prev_bearing == bearing:
            vs = "→"
        elif bearing == "EXIT_REVIEW" or (
            bearing == "TRIM_PACE" and prev_bearing in ("ENTER_OK", "HOLD_UP")
        ):
            vs = "↓"
        elif bearing in ("ENTER_OK", "HOLD_UP") and prev_bearing in (
            "TRIM_PACE",
            "EXIT_REVIEW",
        ):
            vs = "↑"
        else:
            vs = "→"

        rows.append(
            MomentumHoldingRow(
                ticker=tk,
                name=name or item.name,
                as_of=item.as_of or today,
                ts_sign=ts,
                xs_pct=xs,
                xs_bucket=bucket,
                vol_flag=item.vol_high,
                grade=item.grade,
                grade_ko=GRADE_KO.get(item.grade, item.grade),
                upside=upside,
                bearing=bearing,
                bearing_ko=BEARING_KO[bearing],
                weak_streak=streak,
                vs_prev=vs,
                reason=reason,
                source=source,
            )
        )

    if persist_log and rows:
        _append_daily_log(root, as_of=as_of, rows=rows)

    exit_n = sum(1 for r in rows if r.bearing == "EXIT_REVIEW")
    up_n = sum(1 for r in rows if r.upside)
    if not rows:
        summary = (
            "모멘텀 모니터 대상 없음 "
            "(실보유 중 momentum 역할·SCALE_IN 없음 · 「전체 실보유」토글 가능)"
        )
    else:
        summary = (
            f"{len(rows)}종 · 상방 {up_n} · EXIT_REVIEW {exit_n} · "
            f"약세 {exit_streak_n}일 연속 시 청산 검토 · 자동매매 없음"
        )

    return MomentumHoldingBoard(
        as_of=as_of,
        price_as_of=mom_board.price_as_of,
        exit_streak_n=exit_streak_n,
        rows=tuple(rows),
        summary=summary,
    )


def _append_daily_log(
    root: Path,
    *,
    as_of: date,
    rows: Sequence[MomentumHoldingRow],
) -> None:
    path = root / LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    day = as_of.isoformat()
    existing = _read_log(root)
    # Drop same-day same-ticker lines then rewrite file (small log)
    keep = [
        r
        for r in existing
        if not (
            str(r.get("as_of") or "")[:10] == day
            and str(r.get("ticker") or "").zfill(6)
            in {x.ticker for x in rows}
        )
    ]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for row in rows:
        keep.append(
            {
                "recorded_at": now,
                "as_of": day,
                "ticker": row.ticker,
                "name": row.name,
                "ts_sign": row.ts_sign,
                "xs_pct": row.xs_pct,
                "xs_bucket": row.xs_bucket,
                "vol_flag": row.vol_flag,
                "grade": row.grade,
                "bearing": row.bearing,
                "weak": (not row.upside)
                or row.ts_sign == "DOWN"
                or (row.xs_pct is not None and row.xs_pct < CROSS_WAIT),
                "weak_streak": row.weak_streak,
                "upside": row.upside,
                "source": row.source,
                "review_only": True,
            }
        )
    # Cap log size
    if len(keep) > 5000:
        keep = keep[-5000:]
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep),
        encoding="utf-8",
    )


def rows_as_dicts(board: MomentumHoldingBoard) -> list[dict[str, Any]]:
    return [asdict(r) for r in board.rows]
