"""FRED 5축 → 월별 국면(stage) 시계열 · 스위칭 BT 입력 (Review-only).

운영 economy_signal 스냅샷과 분리. yaml/Executable/Soft/target 불변.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from alpha_system.economy_signal import (
    FRED_BASE,
    SERIES_CURVE,
    SERIES_DFF,
    SERIES_DFII10,
    SERIES_HY,
    SERIES_JP,
    score_curve,
    score_hy_oas_bp,
    score_rate_change,
    score_real_yield,
    stage_from_scores,
    three_month_change,
)

MODEL_VERSION = "economy-stage-history-v1"
CACHE_REL = Path("data") / "local" / "economy_stage_history.csv"
META_REL = Path("data") / "local" / "economy_stage_history_meta.json"

# BT용 · 운영 refresh(800일/24)와 분리
_BT_LOOKBACK_DAYS = 4000
_BT_LIMIT = 5000


@dataclass
class StageHistoryBoard:
    ok: bool = False
    error_ko: str = ""
    as_of: str = ""
    model_version: str = MODEL_VERSION
    n_months: int = 0
    start: str = ""
    end: str = ""
    # month-end date (Timestamp) → stage int
    stages: pd.Series = field(default_factory=lambda: pd.Series(dtype="Int64"))
    note_ko: str = (
        "Review-only · FRED 5축(HY·실질·연준3M·BOJ3M·커브) · "
        "CCC/IG·자세 Soft 제외 · target 불변"
    )
    writes_target: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_ko": self.error_ko,
            "as_of": self.as_of,
            "model_version": self.model_version,
            "n_months": self.n_months,
            "start": self.start,
            "end": self.end,
            "note_ko": self.note_ko,
            "writes_target": False,
            "charter": {
                "proposal_mode": "pure_qvm",
                "target_portfolio_written": False,
                "stress_overlay": False,
            },
        }


def stage_history_path(root: Path) -> Path:
    return Path(root) / CACHE_REL


def _resolve_fred_key(root: Path | None) -> str:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        return key
    if root is None:
        return ""
    try:
        from src.settings.user_secrets import apply_secrets_to_env, load_user_secrets

        data_dir = Path(root) / "data"
        apply_secrets_to_env(data_dir)
        key = (
            os.environ.get("FRED_API_KEY", "").strip()
            or load_user_secrets(data_dir).fred_api_key
        )
    except Exception:  # noqa: BLE001
        key = ""
    return (key or "").strip()


def _obs_to_series(observations: list[Any]) -> pd.Series:
    rows: list[tuple[pd.Timestamp, float]] = []
    for o in observations:
        d = getattr(o, "date", None) or (o.get("date") if isinstance(o, dict) else None)
        v = getattr(o, "value", None)
        if v is None and isinstance(o, dict):
            v = o.get("value")
        if not d or v is None:
            continue
        try:
            rows.append((pd.Timestamp(str(d)[:10]), float(v)))
        except (TypeError, ValueError):
            continue
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({d: v for d, v in rows}).sort_index()
    return s[~s.index.duplicated(keep="last")]


def fetch_fred_series_long(
    series_id: str,
    *,
    api_key: str,
    lookback_days: int = _BT_LOOKBACK_DAYS,
    limit: int = _BT_LIMIT,
) -> pd.Series:
    from src.data_refresh.fred_client import _fred_get

    fetched = _fred_get(
        FRED_BASE,
        series_id=series_id,
        api_key=api_key,
        limit=limit,
        lookback_days=lookback_days,
    )
    if fetched.error:
        return pd.Series(dtype=float)
    return _obs_to_series(fetched.observations)


def _month_end_last(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    s = s.sort_index()
    return s.resample("ME").last().dropna()


def _delta_at(
    daily_or_monthly: pd.Series, as_of: pd.Timestamp
) -> float | None:
    """three_month_change semantics · observations newest-first up to as_of."""
    sub = daily_or_monthly.loc[daily_or_monthly.index <= as_of].dropna()
    if sub.empty:
        return None
    rows = [
        {"date": ts.strftime("%Y-%m-%d"), "value": float(v)}
        for ts, v in sub.sort_index(ascending=False).items()
    ]
    return three_month_change(rows)


def stages_from_fred_frames(
    *,
    hy_pct: pd.Series,
    real: pd.Series,
    dff: pd.Series,
    jp: pd.Series,
    curve: pd.Series,
) -> pd.Series:
    """월말 stage Int64 · 입력은 레벨 시계열(일/월 혼재 OK)."""
    hy_m = _month_end_last(hy_pct)
    real_m = _month_end_last(real)
    curve_m = _month_end_last(curve)
    dff_m = _month_end_last(dff)
    jp_m = _month_end_last(jp)
    idx = hy_m.index.union(real_m.index).union(curve_m.index).union(dff_m.index).union(
        jp_m.index
    )
    idx = pd.DatetimeIndex(sorted(idx))
    out: dict[pd.Timestamp, int] = {}
    for ts in idx:
        hy_v = hy_m.asof(ts) if not hy_m.empty else None
        real_v = real_m.asof(ts) if not real_m.empty else None
        curve_v = curve_m.asof(ts) if not curve_m.empty else None
        try:
            hy_bp = None if hy_v is None or pd.isna(hy_v) else float(hy_v) * 100.0
        except (TypeError, ValueError):
            hy_bp = None
        try:
            real_f = None if real_v is None or pd.isna(real_v) else float(real_v)
        except (TypeError, ValueError):
            real_f = None
        try:
            curve_f = None if curve_v is None or pd.isna(curve_v) else float(curve_v)
        except (TypeError, ValueError):
            curve_f = None
        dff_d = _delta_at(dff, ts)
        jp_d = _delta_at(jp, ts)
        scores = [
            score_hy_oas_bp(hy_bp),
            score_real_yield(real_f),
            score_rate_change(dff_d),
            score_rate_change(jp_d),
            score_curve(curve_f),
        ]
        stage, _t, _k = stage_from_scores(scores)
        if stage is not None:
            out[pd.Timestamp(ts)] = int(stage)
    if not out:
        return pd.Series(dtype="Int64")
    return pd.Series(out, dtype="Int64").sort_index()


def build_stage_history(
    root: Path,
    *,
    api_key: str | None = None,
    ensure_fetch: bool = True,
    injected: Mapping[str, pd.Series] | None = None,
) -> StageHistoryBoard:
    """월별 stage 시계열. injected={hy,real,dff,jp,curve}면 FRED 생략."""
    root = Path(root)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if injected is not None:
        stages = stages_from_fred_frames(
            hy_pct=injected.get("hy", pd.Series(dtype=float)),
            real=injected.get("real", pd.Series(dtype=float)),
            dff=injected.get("dff", pd.Series(dtype=float)),
            jp=injected.get("jp", pd.Series(dtype=float)),
            curve=injected.get("curve", pd.Series(dtype=float)),
        )
        if stages.empty:
            return StageHistoryBoard(
                ok=False, error_ko="injected 시계열로 stage 미산출", as_of=as_of
            )
        return StageHistoryBoard(
            ok=True,
            as_of=as_of,
            n_months=int(len(stages)),
            start=str(stages.index[0].date()),
            end=str(stages.index[-1].date()),
            stages=stages,
            note_ko=StageHistoryBoard().note_ko + " · injected",
        )

    if not ensure_fetch:
        cached = load_stage_history(root)
        if cached is not None and cached.ok:
            return cached

    key = (api_key or "").strip() or _resolve_fred_key(root)
    if not key:
        cached = load_stage_history(root)
        if cached is not None and cached.ok:
            cached.note_ko = (cached.note_ko or "") + " · FRED키없음·캐시"
            return cached
        return StageHistoryBoard(
            ok=False,
            error_ko="FRED_API_KEY 없음 · stage 히스토리 미산출",
            as_of=as_of,
        )

    hy = fetch_fred_series_long(SERIES_HY, api_key=key)
    real = fetch_fred_series_long(SERIES_DFII10, api_key=key)
    dff = fetch_fred_series_long(SERIES_DFF, api_key=key)
    jp = fetch_fred_series_long(SERIES_JP, api_key=key)
    curve = fetch_fred_series_long(SERIES_CURVE, api_key=key)
    if hy.empty and real.empty and curve.empty:
        return StageHistoryBoard(
            ok=False,
            error_ko="FRED 관측 없음",
            as_of=as_of,
        )
    stages = stages_from_fred_frames(
        hy_pct=hy, real=real, dff=dff, jp=jp, curve=curve
    )
    if stages.empty:
        return StageHistoryBoard(
            ok=False, error_ko="월별 stage 미산출(지표 부족)", as_of=as_of
        )
    board = StageHistoryBoard(
        ok=True,
        as_of=as_of,
        n_months=int(len(stages)),
        start=str(stages.index[0].date()),
        end=str(stages.index[-1].date()),
        stages=stages,
    )
    try:
        save_stage_history(root, board)
    except OSError:
        pass
    return board


def save_stage_history(root: Path, board: StageHistoryBoard) -> Path:
    import json

    path = stage_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"stage": board.stages.astype("Int64")})
    df.index.name = "date"
    df.to_csv(path, encoding="utf-8")
    meta = {
        **board.to_dict(),
        "path": str(CACHE_REL).replace("\\", "/"),
    }
    (Path(root) / META_REL).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_stage_history(root: Path) -> StageHistoryBoard | None:
    path = stage_history_path(root)
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"])
    except (OSError, ValueError):
        return None
    if df.empty or "stage" not in df.columns:
        return None
    df = df.dropna(subset=["stage"])
    stages = pd.Series(
        df["stage"].astype(int).values,
        index=pd.to_datetime(df["date"]),
        dtype="Int64",
    ).sort_index()
    if stages.empty:
        return None
    return StageHistoryBoard(
        ok=True,
        as_of="",
        n_months=int(len(stages)),
        start=str(stages.index[0].date()),
        end=str(stages.index[-1].date()),
        stages=stages,
        note_ko=StageHistoryBoard().note_ko + " · 캐시",
    )


def stage_asof(stages: pd.Series, dt: pd.Timestamp) -> int | None:
    if stages is None or stages.empty:
        return None
    sub = stages.loc[stages.index <= pd.Timestamp(dt)]
    if sub.empty:
        return None
    try:
        return int(sub.iloc[-1])
    except (TypeError, ValueError):
        return None


__all__ = [
    "CACHE_REL",
    "MODEL_VERSION",
    "StageHistoryBoard",
    "build_stage_history",
    "fetch_fred_series_long",
    "load_stage_history",
    "save_stage_history",
    "stage_asof",
    "stage_history_path",
    "stages_from_fred_frames",
]
