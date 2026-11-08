"""Soft fear rebalance A/B — Review-only, gated on indicator history length.

When fear Soft is hot: cash→equity restore vs buy&hold on KOSPI.
Never writes target / QVM / posture.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from alpha_system.economy_compass.mean_reversion_review import (
    KOSPI_DD_HOT,
    KOSPI_DD_WATCH,
    VIX_HOT,
    VIX_WATCH,
)
from src.backtest.cost_model import (
    sample_quality_banner,
    sample_quality_label,
)

HISTORY_GATE = 60  # Phase-2 style WAIT below this


@dataclass
class FearSoftRebalReport:
    as_of: str
    status: str  # ok | wait | missing
    dates_used: int
    quality: str
    quality_banner: str
    hot_days: int = 0
    mean_bh_fwd20: Optional[float] = None
    mean_rebal_fwd20: Optional[float] = None
    excess_fwd20: Optional[float] = None
    notes: list[str] = field(default_factory=list)
    review_only: bool = True
    never_writes_target: bool = True
    cnn_not_used: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _fear_status(vix: Optional[float], dd: Optional[float]) -> str:
    ranks = {"ok": 0, "watch": 1, "hot": 2, "missing": -1}

    def one_vix() -> str:
        if vix is None:
            return "missing"
        if vix >= VIX_HOT:
            return "hot"
        if vix >= VIX_WATCH:
            return "watch"
        return "ok"

    def one_dd() -> str:
        if dd is None:
            return "missing"
        if dd <= KOSPI_DD_HOT:
            return "hot"
        if dd <= KOSPI_DD_WATCH:
            return "watch"
        return "ok"

    a, b = one_vix(), one_dd()
    if a == "missing":
        return b
    if b == "missing":
        return a
    return a if ranks[a] >= ranks[b] else b


def load_indicator_history(root: Path) -> list[dict[str, Any]]:
    path = Path(root) / "data" / "market_indicators_history.csv"
    if not path.is_file():
        # Fall back to single snapshot file (not enough for BT)
        snap = Path(root) / "data" / "market_indicators.csv"
        if not snap.is_file():
            return []
        path = snap
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str)
    except Exception:
        return []
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        kospi = _f(row.get("kospi"))
        high = _f(row.get("kospi_recent_high"))
        dd = None
        if kospi is not None and high is not None and high > 0:
            dd = kospi / high - 1.0
        rows.append(
            {
                "date": str(row.get("date") or "").strip(),
                "vix": _f(row.get("vix")),
                "kospi": kospi,
                "kospi_dd": dd,
            }
        )
    rows = [r for r in rows if r["date"] and r["kospi"] is not None]
    rows.sort(key=lambda r: r["date"])
    return rows


def run_fear_soft_rebal_backtest(root: Path) -> FearSoftRebalReport:
    """A/B: on fear hot day, be long next 20d vs always long (buy&hold)."""
    root = Path(root)
    hist = load_indicator_history(root)
    n = len(hist)
    quality = sample_quality_label(n)
    banner = sample_quality_banner(quality)
    notes = [
        "Fear Soft = VIX Soft ∪ 코스피 고가대비 · CNN Fear&Greed 원본 미사용",
        "리밸 A/B = hot 날 이후 20일 코스피 vs 동일 구간의 buy&hold 평균",
        "target·QVM·자세 가산 없음",
    ]
    if n == 0:
        return FearSoftRebalReport(
            as_of=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            status="missing",
            dates_used=0,
            quality=quality,
            quality_banner=banner,
            notes=notes + ["market_indicators(_history) 없음"],
        )
    if n < HISTORY_GATE:
        return FearSoftRebalReport(
            as_of=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            status="wait",
            dates_used=n,
            quality=quality,
            quality_banner=banner,
            notes=notes
            + [f"표본 {n} < 게이트 {HISTORY_GATE} · Soft 리밸 A/B WAIT"],
        )

    bh: list[float] = []
    rebal: list[float] = []
    hot_days = 0
    for i, row in enumerate(hist):
        if i + 20 >= n:
            break
        px0 = row["kospi"]
        px1 = hist[i + 20]["kospi"]
        if px0 is None or px1 is None or px0 <= 0:
            continue
        ret = px1 / px0 - 1.0
        bh.append(ret)
        fear = _fear_status(row["vix"], row["kospi_dd"])
        if fear == "hot":
            hot_days += 1
            rebal.append(ret)  # fully invested on fear (contrarian restore)
        # else: rebal stays in cash → 0 for that window (not averaged into rebal list)

    def _mean(xs: list[float]) -> Optional[float]:
        return sum(xs) / len(xs) if xs else None

    mean_bh = _mean(bh)
    mean_re = _mean(rebal)
    excess = None
    if mean_bh is not None and mean_re is not None:
        excess = mean_re - mean_bh

    return FearSoftRebalReport(
        as_of=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        status="ok",
        dates_used=n,
        quality=quality,
        quality_banner=banner,
        hot_days=hot_days,
        mean_bh_fwd20=mean_bh,
        mean_rebal_fwd20=mean_re,
        excess_fwd20=excess,
        notes=notes
        + [
            f"hot 발화일 {hot_days} · buy&hold 창 {len(bh)} · "
            "hot 구간의 20일 코스피만 리밸 표본"
        ],
    )


def fear_soft_card_html(report: FearSoftRebalReport | dict[str, Any]) -> str:
    from html import escape

    def esc(x: object) -> str:
        return escape(str(x or ""), quote=True)

    r = report.to_dict() if isinstance(report, FearSoftRebalReport) else dict(report)
    status = str(r.get("status") or "")
    title = {
        "wait": "Fear Soft 리밸 A/B · WAIT",
        "missing": "Fear Soft 리밸 A/B · 데이터없음",
        "ok": "Fear Soft 리밸 A/B · Review",
    }.get(status, "Fear Soft 리밸 A/B")

    def pct(v: object) -> str:
        try:
            if v is None:
                return "—"
            return f"{float(v) * 100:.1f}%"
        except (TypeError, ValueError):
            return "—"

    body = esc(r.get("quality_banner") or "")
    if status == "ok":
        body = (
            f"hot {int(r.get('hot_days') or 0)}일 · "
            f"BH+20 {pct(r.get('mean_bh_fwd20'))} · "
            f"역발상+20 {pct(r.get('mean_rebal_fwd20'))} · "
            f"초과 {pct(r.get('excess_fwd20'))}"
        )
    elif status == "wait":
        body = (
            f"표본 {int(r.get('dates_used') or 0)}/{HISTORY_GATE} · "
            f"{esc(r.get('quality_banner'))}"
        )
    return (
        f'<div class="l3-bt l3-bt-fg">'
        f'<div class="l3-bt-kicker">Fear Soft · 예비</div>'
        f'<div class="l3-bt-title">{esc(title)}</div>'
        f'<div class="l3-bt-sub">{body}</div>'
        f'<div class="l3-bt-foot">CNN 원본 아님 · target·QVM 불변</div>'
        f"</div>"
    )


def save_fear_soft_report(report: FearSoftRebalReport, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "HISTORY_GATE",
    "FearSoftRebalReport",
    "fear_soft_card_html",
    "load_indicator_history",
    "run_fear_soft_rebal_backtest",
    "save_fear_soft_report",
]
