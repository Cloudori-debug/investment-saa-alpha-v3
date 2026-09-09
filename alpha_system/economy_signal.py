"""Review-only equity-share ladder from FRED tightening inputs.

Does not write target_portfolio.csv, change QVM ranks, or edit alpha_book_ops.yaml.
Missing series fail-open (no stage) instead of guessing RISK_OFF.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
CACHE_REL = Path("data") / "local" / "economy_signal.json"

# (stage, equity, cash, label)
STAGES: tuple[tuple[int, float, float, str], ...] = (
    (1, 0.90, 0.10, "기본"),
    (2, 0.75, 0.25, "조금 줄임"),
    (3, 0.60, 0.40, "중립"),
    (4, 0.40, 0.60, "방어"),
    (5, 0.20, 0.80, "현금 우대"),
)

SERIES_DFF = "DFF"
SERIES_DFII10 = "DFII10"
SERIES_HY = "BAMLH0A0HYM2"
SERIES_CURVE = "T10Y2Y"
SERIES_JP = "IRSTCI01JPM156N"

MIN_KNOWN = 3


@dataclass
class SignalInput:
    key: str
    label: str
    value: float | None = None
    as_of: str = ""
    score: int | None = None
    unit: str = ""
    note: str = ""


@dataclass
class EconomySignal:
    stage: int | None = None
    equity_share: float = 0.90
    cash_share: float = 0.10
    stage_label: str = ""
    tightening: int = 0
    known: int = 0
    inputs: list[SignalInput] = field(default_factory=list)
    fetched_at: str = ""
    detail: str = ""
    target_portfolio_written: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "equity_share": self.equity_share,
            "cash_share": self.cash_share,
            "stage_label": self.stage_label,
            "tightening": self.tightening,
            "known": self.known,
            "inputs": [asdict(item) for item in self.inputs],
            "fetched_at": self.fetched_at,
            "detail": self.detail,
            "target_portfolio_written": False,
        }


def stage_row(stage: int) -> tuple[int, float, float, str]:
    for row in STAGES:
        if row[0] == stage:
            return row
    return STAGES[0]


def score_hy_oas_bp(value: float | None) -> int | None:
    if value is None:
        return None
    if value < 350:
        return 0
    if value < 500:
        return 1
    return 2


def score_real_yield(value: float | None) -> int | None:
    if value is None:
        return None
    if value < 1.0:
        return 0
    if value < 2.0:
        return 1
    return 2


def score_rate_change(delta: float | None) -> int | None:
    """3-month change in policy / call rate (percentage points). Hikes add stress."""
    if delta is None:
        return None
    if delta <= 0:
        return 0
    if delta <= 0.25:
        return 1
    return 2


def score_curve(value: float | None) -> int | None:
    if value is None:
        return None
    if value >= 0.20:
        return 0
    if value >= -0.20:
        return 1
    return 2


def stage_from_scores(scores: Sequence[int | None]) -> tuple[int | None, int, int]:
    known_scores = [int(s) for s in scores if s is not None]
    known = len(known_scores)
    tightening = sum(known_scores)
    if known < MIN_KNOWN:
        return None, tightening, known
    cap = known * 2
    ratio = tightening / cap if cap else 0.0
    if ratio < 0.16:
        stage = 1
    elif ratio < 0.36:
        stage = 2
    elif ratio < 0.56:
        stage = 3
    elif ratio < 0.76:
        stage = 4
    else:
        stage = 5
    return stage, tightening, known


def three_month_change(observations: Sequence[Mapping[str, Any]]) -> float | None:
    """``observations`` newest-first with ``date`` and ``value``."""
    rows = [
        (str(row.get("date") or "")[:10], float(row["value"]))
        for row in observations
        if row.get("date") and row.get("value") is not None
    ]
    if len(rows) < 2:
        return None
    try:
        latest_d = date.fromisoformat(rows[0][0])
    except ValueError:
        return None
    cutoff = latest_d - timedelta(days=80)
    for raw_d, val in rows[1:]:
        try:
            older = date.fromisoformat(raw_d)
        except ValueError:
            continue
        if older <= cutoff:
            return round(rows[0][1] - val, 4)
    return None


def assemble_signal(inputs: Sequence[SignalInput], *, fetched_at: str = "") -> EconomySignal:
    scores = [item.score for item in inputs]
    stage, tightening, known = stage_from_scores(scores)
    if stage is None:
        return EconomySignal(
            stage=None,
            equity_share=0.90,
            cash_share=0.10,
            stage_label="",
            tightening=tightening,
            known=known,
            inputs=list(inputs),
            fetched_at=fetched_at,
            detail=(
                f"지표 {known}개만 측정 · 단계 미산출 (필요 {MIN_KNOWN})"
                if known
                else "금리 지표 없음 · 단계 미산출"
            ),
        )
    n, eq, cash, label = stage_row(stage)
    return EconomySignal(
        stage=n,
        equity_share=eq,
        cash_share=cash,
        stage_label=label,
        tightening=tightening,
        known=known,
        inputs=list(inputs),
        fetched_at=fetched_at,
        detail=f"{n}단계 {label} · 개별주 {eq:.0%} / 단기채 {cash:.0%}",
    )


def cache_path(root: Path) -> Path:
    return Path(root) / CACHE_REL


def load_cached_signal(root: Path) -> EconomySignal | None:
    path = cache_path(root)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    inputs = [SignalInput(**item) for item in raw.get("inputs") or [] if isinstance(item, dict)]
    stage = raw.get("stage")
    return EconomySignal(
        stage=int(stage) if stage is not None else None,
        equity_share=float(raw.get("equity_share") or 0.90),
        cash_share=float(raw.get("cash_share") or 0.10),
        stage_label=str(raw.get("stage_label") or ""),
        tightening=int(raw.get("tightening") or 0),
        known=int(raw.get("known") or 0),
        inputs=inputs,
        fetched_at=str(raw.get("fetched_at") or ""),
        detail=str(raw.get("detail") or ""),
        target_portfolio_written=False,
    )


def save_cached_signal(root: Path, signal: EconomySignal) -> Path:
    path = cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(signal.to_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


GetFred = Callable[..., Any]


def refresh_economy_signal(
    root: Path,
    *,
    api_key: str | None = None,
    get_fred: GetFred | None = None,
) -> EconomySignal:
    """Pull FRED series and cache a Review-only ladder. Never writes target."""
    from src.data_refresh.fred_client import _fred_get, extract_last

    root = Path(root)
    data_dir = root / "data"
    key = (api_key or "").strip() or os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        try:
            from src.settings.user_secrets import apply_secrets_to_env, load_user_secrets

            apply_secrets_to_env(data_dir)
            key = (
                os.environ.get("FRED_API_KEY", "").strip()
                or load_user_secrets(data_dir).fred_api_key
            )
        except Exception:
            key = ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not key:
        signal = assemble_signal([], fetched_at=now)
        signal.detail = "FRED 키가 없습니다. 설정 › API 키에 넣으면 단계를 산출합니다."
        save_cached_signal(root, signal)
        return signal

    fetch = get_fred or (lambda series_id, limit=120: _fred_get(FRED_BASE, series_id=series_id, api_key=key, limit=limit))

    def last_and_delta(series_id: str) -> tuple[float | None, str, float | None, str]:
        result = fetch(series_id)
        err = getattr(result, "error", None)
        obs = getattr(result, "observations", None) or []
        if err or not obs:
            return None, "", None, str(err or "empty")
        rows = [{"date": o.date, "value": o.value} for o in obs]
        val, dt = extract_last(obs)
        delta = three_month_change(rows)
        return val, dt, delta, ""

    dff, dff_dt, dff_d, dff_err = last_and_delta(SERIES_DFF)
    real, real_dt, _rd, real_err = last_and_delta(SERIES_DFII10)
    hy, hy_dt, _hd, hy_err = last_and_delta(SERIES_HY)
    curve, curve_dt, _cd, curve_err = last_and_delta(SERIES_CURVE)
    jp, jp_dt, jp_d, jp_err = last_and_delta(SERIES_JP)
    hy_bp = None if hy is None else round(hy * 100.0, 1)

    inputs = [
        SignalInput(
            key="hy_oas",
            label="미국 HY OAS",
            value=hy_bp,
            as_of=hy_dt,
            score=score_hy_oas_bp(hy_bp),
            unit="bp",
            note=hy_err or "회사채 가산금리",
        ),
        SignalInput(
            key="real_us",
            label="미국 10년 실질금리",
            value=real,
            as_of=real_dt,
            score=score_real_yield(real),
            unit="%",
            note=real_err or "물가연동 10년",
        ),
        SignalInput(
            key="fed_hike",
            label="연준 금리 3개월 변화",
            value=dff_d,
            as_of=dff_dt,
            score=score_rate_change(dff_d),
            unit="%p",
            note=dff_err or (f"기준금리 {dff}" if dff is not None else ""),
        ),
        SignalInput(
            key="boj_hike",
            label="일본 콜금리 3개월 변화",
            value=jp_d,
            as_of=jp_dt,
            score=score_rate_change(jp_d),
            unit="%p",
            note=jp_err or "월간 통계 · 늦을 수 있음",
        ),
        SignalInput(
            key="curve",
            label="미국 장단기 금리차",
            value=curve,
            as_of=curve_dt,
            score=score_curve(curve),
            unit="%p",
            note=curve_err or "10년 − 2년",
        ),
    ]
    signal = assemble_signal(inputs, fetched_at=now)
    save_cached_signal(root, signal)
    return signal
