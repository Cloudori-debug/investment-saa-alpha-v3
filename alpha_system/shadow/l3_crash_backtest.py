"""L3 crash / re-entry historical replay — Review-only diagnostics.

Reuses classify_crash_defense + build_reentry_ladder.
Never writes target_portfolio.csv / QVM / orders.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from alpha_system.ui.services.crash_defense_signal import (
    C1,
    C2,
    C3,
    CRASH_LOOKBACK,
    R1,
    R2,
    R3,
    build_reentry_ladder,
    classify_crash_defense,
)
from src.backtest.cost_model import (
    apply_round_trip_cost_fraction,
    load_cost_assumptions,
    sample_quality_banner,
    sample_quality_label,
)

FWD_DAYS = (5, 20, 60)
_CODE_RANK = {"hold": 0, "C1": 1, "C2": 2, "C3": 3}


@dataclass(frozen=True)
class L3Event:
    ticker: str
    date: str
    code: str
    ret_nd: float
    crash_low: float
    close: float
    trim_frac: float
    fwd: dict[str, Optional[float]]  # "5"|"20"|"60" → fraction or None
    hold_fwd: dict[str, Optional[float]]  # buy&hold same windows
    rung_days: dict[str, Optional[int]]  # R1|R2|R3 → sessions to first hit
    net_fwd20: Optional[float] = None  # after one round-trip cost on trim leg


@dataclass
class L3BacktestReport:
    as_of: str
    market: str
    tickers: list[str]
    dates_used: int
    quality: str
    quality_banner: str
    event_count: int
    by_code: dict[str, int]
    mean_fwd: dict[str, Optional[float]]
    median_fwd: dict[str, Optional[float]]
    rung_hit_rate: dict[str, Optional[float]]
    rung_median_days: dict[str, Optional[float]]
    mean_hold_fwd20: Optional[float]
    mean_event_fwd20: Optional[float]
    mean_net_fwd20: Optional[float]
    cost_bps: float
    events: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    review_only: bool = True
    never_writes_target: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm_ticker(raw: object) -> str:
    text = str(raw or "").strip()
    if text.isdigit():
        return text.zfill(6)
    return text


def _median(vals: Sequence[float]) -> Optional[float]:
    xs = sorted(float(v) for v in vals if v is not None and not math.isnan(float(v)))
    if not xs:
        return None
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def _mean(vals: Sequence[float]) -> Optional[float]:
    xs = [float(v) for v in vals if v is not None and not math.isnan(float(v))]
    if not xs:
        return None
    return sum(xs) / len(xs)


def load_dated_closes(
    root: Path,
    tickers: Sequence[str] | None = None,
    *,
    max_rows_per_ticker: int = 400,
) -> dict[str, list[tuple[str, float]]]:
    """ticker → [(date_iso, close), ...] ascending."""
    root = Path(root)
    want = {_norm_ticker(t) for t in tickers} if tickers is not None else None
    path = root / "data" / "prices_history.csv"
    if not path.is_file():
        path = root / "data" / "prices.csv"
    if not path.is_file():
        return {}
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str)
    except Exception:
        return {}
    if df.empty or "ticker" not in df.columns or "close" not in df.columns:
        return {}
    df = df.copy()
    df["ticker"] = df["ticker"].map(_norm_ticker)
    if want is not None:
        df = df[df["ticker"].isin(want)]
    if df.empty:
        return {}
    if "date" not in df.columns:
        return {}
    df["_date"] = pd.to_datetime(df["date"], errors="coerce")
    df["_close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["_date", "_close"])
    df = df[df["_close"] > 0]
    df = df.sort_values(["ticker", "_date"])
    out: dict[str, list[tuple[str, float]]] = {}
    for t, g in df.groupby("ticker", sort=False):
        rows = [
            (d.strftime("%Y-%m-%d"), float(c))
            for d, c in zip(g["_date"], g["_close"])
        ]
        if max_rows_per_ticker > 0:
            rows = rows[-max_rows_per_ticker:]
        if rows:
            out[str(t)] = rows
    return out


def resolve_universe_tickers(
    root: Path,
    *,
    market: str = "KOSPI",
    include_target: bool = True,
) -> list[str]:
    """Mid holdings (+ optional target). One market book at a time."""
    root = Path(root)
    m = str(market or "KOSPI").upper()
    if m.startswith("KOSDAQ"):
        book = root / "data" / "books" / "kosdaq"
        pos = book / "positions.csv"
        tgt = book / "target_portfolio.csv"
    else:
        pos = root / "data" / "positions.csv"
        if not pos.is_file():
            pos = root / "data" / "books" / "kospi" / "positions.csv"
        tgt = root / "data" / "target_portfolio.csv"
        if not tgt.is_file():
            tgt = root / "data" / "books" / "kospi" / "target_portfolio.csv"

    tickers: set[str] = set()

    def _from_csv(path: Path, *, group_filter: bool) -> None:
        if not path.is_file():
            return
        try:
            import pandas as pd

            df = pd.read_csv(path, dtype=str)
        except Exception:
            return
        if df.empty or "ticker" not in df.columns:
            return
        if group_filter and "asset_group" in df.columns:
            df = df[df["asset_group"].astype(str).str.lower() == "kr_alpha"]
        for t in df["ticker"].tolist():
            nt = _norm_ticker(t)
            if nt:
                tickers.add(nt)

    _from_csv(pos, group_filter=True)
    if include_target:
        _from_csv(tgt, group_filter=False)
    return sorted(tickers)


def _fwd_return(
    closes: Sequence[float], i: int, horizon: int
) -> Optional[float]:
    j = i + horizon
    if j >= len(closes) or closes[i] <= 0 or closes[j] <= 0:
        return None
    return closes[j] / closes[i] - 1.0


def _rung_first_hit_days(
    *,
    series: Sequence[tuple[str, float]],
    event_i: int,
    crash_low: float,
    trim_frac: float,
) -> dict[str, Optional[int]]:
    out: dict[str, Optional[int]] = {"R1": None, "R2": None, "R3": None}
    if crash_low <= 0 or trim_frac <= 0:
        return out
    hit = {"R1": False, "R2": False, "R3": False}
    for k in range(event_i, len(series)):
        window = [c for _, c in series[: k + 1]]
        last = series[k][1]
        ladder = build_reentry_ladder(
            crash_low=crash_low,
            last=last,
            trim_frac=trim_frac,
            closes=window,
        )
        if ladder is None:
            continue
        days = k - event_i
        for r in ladder.rungs:
            if r.hit and not hit[r.id]:
                hit[r.id] = True
                out[r.id] = days
        if all(hit.values()):
            break
    return out


def scan_ticker_events(
    ticker: str,
    series: Sequence[tuple[str, float]],
    *,
    lookback: int = CRASH_LOOKBACK,
    cost_assumptions: Mapping[str, Any] | None = None,
) -> list[L3Event]:
    """Emit L3 events on enter/upgrade (not every day while in crash)."""
    if len(series) < lookback + 2:
        return []
    closes = [c for _, c in series]
    events: list[L3Event] = []
    prev_code = "hold"
    for i in range(lookback, len(closes)):
        window = closes[: i + 1]
        sig = classify_crash_defense(window, n=lookback)
        code = sig.code
        rank = _CODE_RANK.get(code, 0)
        prev_rank = _CODE_RANK.get(prev_code, 0)
        fire = rank >= 1 and rank > prev_rank
        prev_code = code if rank >= 1 else "hold"
        if not fire:
            continue
        trim_frac = (sig.trim_pct or 0) / 100.0
        fwd = {str(h): _fwd_return(closes, i, h) for h in FWD_DAYS}
        hold_fwd = dict(fwd)  # same path = buy&hold from event close
        rung_days = _rung_first_hit_days(
            series=series,
            event_i=i,
            crash_low=sig.crash_low,
            trim_frac=trim_frac or 0.25,
        )
        g20 = fwd.get("20")
        net20 = None
        if g20 is not None and trim_frac > 0:
            # Gross path return minus one round-trip cost on the trimmed notional.
            # apply_round_trip_cost_fraction(0) → −cost (fraction).
            cost_drag = -apply_round_trip_cost_fraction(0.0, 20, cost_assumptions)
            net20 = float(g20) - float(trim_frac) * float(cost_drag)
        events.append(
            L3Event(
                ticker=_norm_ticker(ticker),
                date=series[i][0],
                code=code,
                ret_nd=float(sig.ret_nd),
                crash_low=float(sig.crash_low),
                close=float(closes[i]),
                trim_frac=float(trim_frac),
                fwd=fwd,
                hold_fwd=hold_fwd,
                rung_days=rung_days,
                net_fwd20=net20,
            )
        )
    return events


def run_l3_crash_backtest(
    root: Path,
    *,
    market: str = "KOSPI",
    tickers: Sequence[str] | None = None,
    include_target: bool = True,
    max_events_in_report: int = 200,
) -> L3BacktestReport:
    root = Path(root)
    universe = (
        [_norm_ticker(t) for t in tickers if t]
        if tickers is not None
        else resolve_universe_tickers(
            root, market=market, include_target=include_target
        )
    )
    dated = load_dated_closes(root, universe)
    cost_path = root / "data" / "cost_assumptions.yaml"
    assumptions = load_cost_assumptions(cost_path if cost_path.is_file() else None)
    from src.backtest.cost_model import round_trip_cost_bps

    cost_bps = float(round_trip_cost_bps(assumptions))

    all_events: list[L3Event] = []
    date_set: set[str] = set()
    notes: list[str] = []
    if not universe:
        notes.append("유니버스 비어 있음 · 보유/target 확인")
    if not dated:
        notes.append("prices_history/prices 없음")

    for t in universe:
        series = dated.get(t) or []
        for d, _ in series:
            date_set.add(d)
        all_events.extend(
            scan_ticker_events(t, series, cost_assumptions=assumptions)
        )

    dates_used = len(date_set)
    quality = sample_quality_label(dates_used)
    banner = sample_quality_banner(quality)

    by_code: dict[str, int] = {"C1": 0, "C2": 0, "C3": 0}
    for ev in all_events:
        by_code[ev.code] = by_code.get(ev.code, 0) + 1

    mean_fwd: dict[str, Optional[float]] = {}
    median_fwd: dict[str, Optional[float]] = {}
    for h in FWD_DAYS:
        key = str(h)
        vals = [ev.fwd.get(key) for ev in all_events if ev.fwd.get(key) is not None]
        mean_fwd[key] = _mean([float(v) for v in vals if v is not None])
        median_fwd[key] = _median([float(v) for v in vals if v is not None])

    rung_hit_rate: dict[str, Optional[float]] = {}
    rung_median_days: dict[str, Optional[float]] = {}
    for rid in ("R1", "R2", "R3"):
        hits = [ev.rung_days.get(rid) for ev in all_events]
        known = [d for d in hits if d is not None]
        if not all_events:
            rung_hit_rate[rid] = None
            rung_median_days[rid] = None
        else:
            rung_hit_rate[rid] = len(known) / len(all_events)
            rung_median_days[rid] = _median([float(d) for d in known])

    mean_event_fwd20 = mean_fwd.get("20")
    hold_vals = [
        float(ev.hold_fwd["20"])
        for ev in all_events
        if ev.hold_fwd.get("20") is not None
    ]
    mean_hold_fwd20 = _mean(hold_vals)
    net_vals = [float(ev.net_fwd20) for ev in all_events if ev.net_fwd20 is not None]
    mean_net_fwd20 = _mean(net_vals)

    notes.append(
        "L3 단독 exit_full 없음 · trim/환금 Review 가정 · target·QVM 불변"
    )
    notes.append(
        f"발화=등급 진입/상향만 · lookback={CRASH_LOOKBACK} · "
        f"C1={C1} C2={C2} C3={C3} · R={R1}/{R2}/{R3}"
    )

    event_dicts = [asdict(ev) for ev in all_events[:max_events_in_report]]
    if len(all_events) > max_events_in_report:
        notes.append(f"이벤트 {len(all_events)}건 중 앞 {max_events_in_report}건만 JSON 수록")

    return L3BacktestReport(
        as_of=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        market=str(market or "KOSPI").upper(),
        tickers=list(universe),
        dates_used=dates_used,
        quality=quality,
        quality_banner=banner,
        event_count=len(all_events),
        by_code=by_code,
        mean_fwd=mean_fwd,
        median_fwd=median_fwd,
        rung_hit_rate=rung_hit_rate,
        rung_median_days=rung_median_days,
        mean_hold_fwd20=mean_hold_fwd20,
        mean_event_fwd20=mean_event_fwd20,
        mean_net_fwd20=mean_net_fwd20,
        cost_bps=cost_bps,
        events=event_dicts,
        notes=notes,
    )


def report_card_html(report: L3BacktestReport | Mapping[str, Any]) -> str:
    from html import escape

    def esc(x: object) -> str:
        return escape(str(x or ""), quote=True)

    r = report.to_dict() if isinstance(report, L3BacktestReport) else dict(report)
    q = esc(r.get("quality_banner") or "")
    by = r.get("by_code") or {}
    mf = r.get("mean_fwd") or {}

    def pct(v: object) -> str:
        try:
            if v is None:
                return "—"
            return f"{float(v) * 100:.1f}%"
        except (TypeError, ValueError):
            return "—"

    rh = r.get("rung_hit_rate") or {}
    return (
        '<div class="l3-bt">'
        '<div class="l3-bt-kicker">L3 이력 Review</div>'
        f'<div class="l3-bt-banner">{q}</div>'
        f'<div class="l3-bt-title">{esc(r.get("market"))} · 발화 {int(r.get("event_count") or 0)}건</div>'
        f'<div class="l3-bt-sub">표본일 {int(r.get("dates_used") or 0)} · '
        f'C1 {int(by.get("C1") or 0)} · C2 {int(by.get("C2") or 0)} · '
        f'C3 {int(by.get("C3") or 0)}</div>'
        '<div class="l3-bt-grid">'
        f'<div><span class="l3-bt-k">+5일 평균</span> {pct(mf.get("5"))}</div>'
        f'<div><span class="l3-bt-k">+20일 평균</span> {pct(mf.get("20"))}</div>'
        f'<div><span class="l3-bt-k">+60일 평균</span> {pct(mf.get("60"))}</div>'
        f'<div><span class="l3-bt-k">홀드+20</span> {pct(r.get("mean_hold_fwd20"))}</div>'
        f'<div><span class="l3-bt-k">Net+20</span> {pct(r.get("mean_net_fwd20"))}</div>'
        f'<div><span class="l3-bt-k">R1 도달</span> {pct(rh.get("R1"))}</div>'
        "</div>"
        '<div class="l3-bt-foot">Review-only · target·QVM·자동주문 없음 · '
        f'비용 {esc(r.get("cost_bps"))}bps 가정</div>'
        "</div>"
    )


def save_report(report: L3BacktestReport, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "FWD_DAYS",
    "L3BacktestReport",
    "L3Event",
    "load_dated_closes",
    "report_card_html",
    "resolve_universe_tickers",
    "run_l3_crash_backtest",
    "save_report",
    "scan_ticker_events",
]
