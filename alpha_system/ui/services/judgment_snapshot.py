"""Home 「시스템 판정」snapshot — regime · T3 · next judgment (read-only)."""

from __future__ import annotations

import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.ui.services.v2_chrome import regime_info as load_regime_info

if TYPE_CHECKING:
    from alpha_system.ui.services.context import DashboardContext


@dataclass(frozen=True)
class JudgmentSnapshot:
    regime_label: str
    regime_detail: str
    regime_tone: str
    pure_auto: bool
    t3_summary: str
    t3_available: bool
    next_judgment: str
    show_settings_cta: bool


def next_judgment_hint(ctx: DashboardContext) -> str:
    as_of = ctx.as_of
    if as_of >= ctx.window_end:
        return f"논지 창 종료 ({ctx.window_end.isoformat()})"
    last = monthrange(as_of.year, as_of.month)[1]
    month_end = date(as_of.year, as_of.month, last)
    if as_of < month_end:
        return f"T3 {as_of.month}월 말"
    if as_of.month == 12:
        return "T3 1월 말"
    return f"T3 {as_of.month + 1}월 말"


def _t3_summary(ctx: DashboardContext) -> tuple[str, bool]:
    pbr = ctx.t3_pbr
    if not pbr.available:
        return (
            copy_get(
                "system_judgment",
                "t3_unavailable",
                default="이력 없음 · 월말 판정 연결 전",
            ),
            False,
        )
    if pbr.in_bottom_band is True:
        band = copy_get(
            "system_judgment",
            "t3_in_band",
            default="하단 밴드 진입",
        )
    elif pbr.in_bottom_band is False:
        band = copy_get(
            "system_judgment",
            "t3_out_band",
            default="하단 밴드 밖",
        )
    else:
        band = copy_get(
            "system_judgment",
            "t3_band_unknown",
            default="밴드 판정 불가",
        )
    bits = [band]
    if pbr.current_pbr is not None:
        bits.append(f"PBR {pbr.current_pbr:.2f}")
    if pbr.percentile_10y is not None:
        bits.append(f"10년 %ile {pbr.percentile_10y}")
    if pbr.as_of is not None:
        bits.append(f"as_of {pbr.as_of.isoformat()}")
    bits.append(
        copy_get("system_judgment", "t3_cadence", default="다음 판정: 매월 말")
    )
    return " · ".join(bits), True


def _tier2_stale(root: Path, *, warn_days: int = 45) -> bool:
    path = root / "data" / "tier2_provenance.json"
    if not path.exists():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict):
        return False
    fields = raw.get("fields")
    if not isinstance(fields, dict):
        return False
    for meta in fields.values():
        if not isinstance(meta, dict):
            continue
        if str(meta.get("status") or "").lower() == "stale":
            return True
        try:
            days = meta.get("stale_days")
            thresh = meta.get("threshold_days", warn_days)
            if days is not None and float(days) >= float(thresh):
                return True
        except (TypeError, ValueError):
            continue
    return False


def _regime_set_stale(root: Path, *, as_of: date, max_age_days: int = 14) -> bool:
    info = load_regime_info(root)
    # parse from market_indicators via detail is fragile; re-read set date lightly
    path = root / "data" / "market_indicators.csv"
    if not path.exists():
        return True
    try:
        import pandas as pd

        df = pd.read_csv(path)
        if df.empty or "regime_set_date" not in df.columns:
            return False
        set_s = str(df.iloc[-1].get("regime_set_date") or "").strip()
        if not set_s or set_s.lower() in {"nan", "none"}:
            return bool(info.get("label") in {None, "", "—"})
        set_d = date.fromisoformat(set_s[:10])
        return (as_of - set_d).days >= max_age_days
    except Exception:
        return False


def build_judgment_snapshot(ctx: DashboardContext) -> JudgmentSnapshot:
    regime = load_regime_info(ctx.root)
    t3_summary, t3_ok = _t3_summary(ctx)
    show_settings = _tier2_stale(ctx.root) or _regime_set_stale(
        ctx.root, as_of=ctx.as_of
    )
    return JudgmentSnapshot(
        regime_label=str(regime.get("label") or "—"),
        regime_detail=str(regime.get("detail") or ""),
        regime_tone=str(regime.get("tone") or "muted"),
        pure_auto=bool(regime.get("pure_auto")),
        t3_summary=t3_summary,
        t3_available=t3_ok,
        next_judgment=next_judgment_hint(ctx),
        show_settings_cta=show_settings,
    )
