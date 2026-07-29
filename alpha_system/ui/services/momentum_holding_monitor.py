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
    "ENTER_OK": "추가·진입 검토",
    "HOLD_UP": "상방 유지",
    "TRIM_PACE": "속도 축소·축소 검토",
    "EXIT_REVIEW": "청산·교체 검토",
}

BEARING_HELP_KO: dict[Bearing, str] = {
    "ENTER_OK": "중기 상승·교차 60↑·1·3개월 비약세·변동 정상·진행일 때 추가·진입 검토",
    "HOLD_UP": "중기 상승·교차 40↑·단기 비약세일 때 상방 유지(관측)",
    "TRIM_PACE": "느리게·고변동·추가매수 중지·중기 약세 또는 1·3개월 약세 → 분할 중단·축소 검토",
    "EXIT_REVIEW": "중기·단기 약세가 연속 N일이면 청산·교체만 검토(자동매도 아님)",
}

XS_BUCKET_KO: dict[XsBucket, str] = {
    "Strong": "강함",
    "Mid": "중간",
    "Weak": "약함",
    "—": "—",
}

SOURCE_KO: dict[str, str] = {
    "momentum_role": "모멘텀 역할",
    "scale_in": "분할매수 중",
    "ops_held": "실보유",
}

EXIT_STREAK_DEFAULT = 5
LOG_REL = Path("data") / "local" / "momentum_holding_log.jsonl"

# 매매 전략 접목 (Review-only · SCALE_IN / EXIT 규칙과 맞춤, 자동주문 없음)
STRATEGY_ACTION_KO: dict[Bearing, str] = {
    "ENTER_OK": "분할매수 진행",
    "HOLD_UP": "보유 유지",
    "TRIM_PACE": "분할 중단·축소",
    "EXIT_REVIEW": "청산·교체 검토",
}


def strategy_playbook(
    *,
    bearing: Bearing,
    source: str,
    short_weak: bool,
    vol_flag: bool,
    weak_streak: int,
    exit_streak_n: int,
) -> tuple[str, str]:
    """(짧은 행동 라벨, 운영 안내 한 줄). 자동매매·target 변경 없음."""
    action = STRATEGY_ACTION_KO[bearing]
    scale = source == "scale_in"

    if bearing == "ENTER_OK":
        if scale:
            detail = (
                "남은 분할회차(기본 1/3·균등) 진행 검토 · "
                "회차 사이 ≥3거래일 · 하루 전액 투입 금지"
            )
        else:
            detail = (
                "추가 분할매수 검토 가능(기본 3회 균등) · "
                "하루 전액 금지 · 목표가 없으면 신규매수 금지"
            )
        return action, detail

    if bearing == "HOLD_UP":
        detail = (
            "보유 유지 · 새 분할은 서두르지 않음 · "
            "익절(목표가 근접·도달)은 포트폴리오·익절 점검 규칙을 따름"
        )
        return action, detail

    if bearing == "TRIM_PACE":
        bits = []
        if scale:
            bits.append("남은 분할매수 회차 중단")
        else:
            bits.append("추가매수·물타기 금지")
        if short_weak:
            bits.append("단기(1·3개월) 약세 — 중기만 보고 더 사지 말 것")
        if vol_flag:
            bits.append("고변동 — 노출 축소 검토")
        bits.append("이미 산 분은 익절·논지 규칙으로만 처리")
        return action, " · ".join(bits)

    # EXIT_REVIEW
    detail = (
        f"약세 {weak_streak}일(임계 {exit_streak_n}) · "
        "전량·교체만 사람 검토 · 자동매도 아님 · 추가매수 금지 · "
        "포트폴리오 익절/제안탈락 바늘과 함께 확인"
    )
    return action, detail


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
    """True = mid UP · xs>=40 · not short_weak."""
    bearing: Bearing
    bearing_ko: str
    weak_streak: int
    """Consecutive calendar log days with mid or short weakness."""
    vs_prev: str
    """bearing change vs last log: ↑/↓/→/신규"""
    reason: str
    source: str
    """momentum_role | scale_in | ops_held"""
    ret_1m: float | None = None
    ret_3m: float | None = None
    short_weak: bool = False
    short_1m_sign: TsSign = "—"
    short_3m_sign: TsSign = "—"
    strategy_action: str = ""
    """짧은 매매 행동 (분할매수 진행 / 보유 유지 / …)."""
    strategy_detail: str = ""
    """운영 규칙과 맞춘 Review-only 안내."""


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


def _ret_sign(ret: float | None) -> TsSign:
    if ret is None:
        return "—"
    return "UP" if ret > 0 else "DOWN"


def is_short_weak(
    ret_1m: float | None,
    ret_3m: float | None,
) -> bool:
    """1개월 또는 3개월 수익률이 음수면 단기 약세 (결측은 무시)."""
    if ret_1m is not None and ret_1m < 0:
        return True
    if ret_3m is not None and ret_3m < 0:
        return True
    return False


def compute_upside(
    *,
    ts_sign: TsSign,
    xs_pct: float | None,
    short_weak: bool,
) -> bool:
    """중기 상승 ∧ 교차≥40 ∧ 단기 비약세."""
    return (
        ts_sign == "UP"
        and xs_pct is not None
        and xs_pct >= CROSS_WAIT
        and not short_weak
    )


def classify_bearing(
    *,
    ts_sign: TsSign,
    xs_pct: float | None,
    vol_flag: bool,
    grade: Grade,
    weak_streak: int,
    exit_streak_n: int = EXIT_STREAK_DEFAULT,
    short_weak: bool = False,
) -> tuple[Bearing, str]:
    """Review-only bearing. EXIT_REVIEW needs weak_streak >= N.

    Mid-term (12-1) remains the backbone; short_weak (1M/3M≤0) blocks
    ENTER/HOLD_UP and counts toward weakness with mid-term signals.
    """
    mid_weak = ts_sign == "DOWN" or (xs_pct is not None and xs_pct < CROSS_WAIT)
    weak_now = mid_weak or short_weak
    if weak_now and weak_streak >= exit_streak_n:
        return (
            "EXIT_REVIEW",
            f"하방/약세 {weak_streak}일≥{exit_streak_n} → 청산·교체 검토(자동매도 아님)",
        )
    if grade == "CUT_PACE" or vol_flag or grade == "SLOW":
        why = []
        if grade == "CUT_PACE":
            why.append(GRADE_KO.get("CUT_PACE", "추가매수 중지"))
        if vol_flag:
            why.append("고변동")
        if grade == "SLOW":
            why.append(GRADE_KO.get("SLOW", "천천히"))
        return "TRIM_PACE", " · ".join(why) + " → 분할 중단·축소 검토"
    if short_weak and not mid_weak:
        return (
            "TRIM_PACE",
            "중기는 상승이나 1·3개월 약세 → 속도 축소·관찰(급락 괴리 가드)",
        )
    if (
        ts_sign == "UP"
        and xs_pct is not None
        and xs_pct >= CROSS_GO
        and not vol_flag
        and not short_weak
        and grade == "GO"
    ):
        return "ENTER_OK", "중기 상승 · 교차≥60 · 단기 비약세 · 진행 → 추가·진입 검토"
    if (
        ts_sign == "UP"
        and xs_pct is not None
        and xs_pct >= CROSS_WAIT
        and not short_weak
        and grade != "CUT_PACE"
    ):
        return "HOLD_UP", "중기 상승 · 교차≥40 · 단기 비약세 → 상방 유지"
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
        ret_1 = getattr(item, "ret_1m", None)
        ret_3 = item.ret_3
        s_weak = is_short_weak(ret_1, ret_3)
        mid_weak = ts == "DOWN" or (xs is not None and xs < CROSS_WAIT)
        weak_now = mid_weak or s_weak
        upside = compute_upside(ts_sign=ts, xs_pct=xs, short_weak=s_weak)
        hist = _history_for_ticker(log, tk)
        streak = _weak_streak_from_history(hist, today_weak=weak_now, today=today)
        bearing, reason = classify_bearing(
            ts_sign=ts,
            xs_pct=xs,
            vol_flag=item.vol_high,
            grade=item.grade,
            weak_streak=streak,
            exit_streak_n=exit_streak_n,
            short_weak=s_weak,
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

        strat_action, strat_detail = strategy_playbook(
            bearing=bearing,
            source=source,
            short_weak=s_weak,
            vol_flag=item.vol_high,
            weak_streak=streak,
            exit_streak_n=exit_streak_n,
        )

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
                ret_1m=ret_1,
                ret_3m=ret_3,
                short_weak=s_weak,
                short_1m_sign=_ret_sign(ret_1),
                short_3m_sign=_ret_sign(ret_3),
                strategy_action=strat_action,
                strategy_detail=strat_detail,
            )
        )

    if persist_log and rows:
        _append_daily_log(root, as_of=as_of, rows=rows)

    exit_n = sum(1 for r in rows if r.bearing == "EXIT_REVIEW")
    up_n = sum(1 for r in rows if r.upside)
    enter_n = sum(1 for r in rows if r.bearing == "ENTER_OK")
    trim_n = sum(1 for r in rows if r.bearing == "TRIM_PACE")
    hold_n = sum(1 for r in rows if r.bearing == "HOLD_UP")
    if not rows:
        summary = (
            "점검 대상 없음 "
            "(모멘텀 역할·분할매수 중인 실보유 없음 · 「전체 실보유」로 확대 가능)"
        )
    else:
        summary = (
            f"{len(rows)}종 · 상방 {up_n} · "
            f"전략: 분할진행 {enter_n} · 유지 {hold_n} · 중단·축소 {trim_n} · "
            f"청산검토 {exit_n} · 자동매매 없음"
        )

    return MomentumHoldingBoard(
        as_of=as_of,
        price_as_of=mom_board.price_as_of,
        exit_streak_n=exit_streak_n,
        rows=tuple(rows),
        summary=summary,
    )


def strategy_priority(bearing: Bearing) -> int:
    """UI 정렬: 급한 전략부터."""
    order = {"EXIT_REVIEW": 0, "TRIM_PACE": 1, "ENTER_OK": 2, "HOLD_UP": 3}
    return order.get(bearing, 9)


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
                or row.short_weak
                or (row.xs_pct is not None and row.xs_pct < CROSS_WAIT),
                "weak_streak": row.weak_streak,
                "upside": row.upside,
                "short_weak": row.short_weak,
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
