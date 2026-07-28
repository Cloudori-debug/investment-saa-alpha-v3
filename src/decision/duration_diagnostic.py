from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml

from src.models import GapRow, PositionRow, TargetRow

SleeveType = Literal["cash_short", "kr_duration_bond", "global_duration_bond"]
GapStatus = Literal["ok", "underweight", "overweight", "absent"]

DEFAULT_SHADOW_TARGETS = {
    "cash_short": {"min": 15.0, "target": 17.5, "max": 20.0},
    "kr_duration_bond": {"min": 10.0, "target": 12.5, "max": 15.0},
    "global_duration_bond": {"min": 5.0, "target": 7.5, "max": 10.0},
}


def load_duration_sleeve_config(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "duration_sleeve_tags.yaml"
    if not path.exists():
        return {"shadow_targets_pct": DEFAULT_SHADOW_TARGETS}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_look_through_instruments(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / "look_through_tags.yaml"
    if not path.exists():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get("instruments") or {}


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip().upper()
    return t if t == "CASH" else t.zfill(6) if t.isdigit() else t


def resolve_sleeve(
    ticker: str,
    *,
    style: str = "",
    role: str = "",
    instruments: dict[str, dict[str, Any]],
    sleeve_cfg: dict[str, Any],
) -> SleeveType:
    norm = _normalize_ticker(ticker)
    by_ticker = sleeve_cfg.get("sleeve_by_ticker") or {}
    if norm in by_ticker or ticker in by_ticker:
        val = str(by_ticker.get(norm) or by_ticker.get(ticker))
        if val in {"cash_short", "kr_duration_bond", "global_duration_bond"}:
            return val  # type: ignore[return-value]

    inst = instruments.get(norm) or instruments.get(ticker) or {}
    lt = inst.get("look_through") or {}
    asset_class = str(lt.get("asset_class") or "")
    by_class = sleeve_cfg.get("sleeve_by_asset_class") or {}
    if asset_class in by_class:
        return str(by_class[asset_class])  # type: ignore[return-value]

    text = f"{style} {role}".lower()
    for sleeve, keywords in (sleeve_cfg.get("sleeve_by_style_keyword") or {}).items():
        if any(kw in text for kw in keywords):
            return sleeve  # type: ignore[return-value]

    return "cash_short"


def _weight_pct(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round(value / total * 100, 2)


def _gap_status(current: float, bounds: dict[str, float]) -> GapStatus:
    if current <= 0.01:
        return "absent"
    if current < float(bounds.get("min", 0)):
        return "underweight"
    if current > float(bounds.get("max", 100)):
        return "overweight"
    return "ok"


def build_duration_bond_status(
    *,
    positions: list[PositionRow],
    targets: list[TargetRow] | None,
    gap_rows: list[GapRow] | None,
    allocation_groups: list[Any] | None,
    data_dir: Path,
) -> dict[str, Any]:
    """cash_short_bond를 cash_short / duration 슬리브로 shadow 분해 — v1.0.2 실행 변경 없음."""
    sleeve_cfg = load_duration_sleeve_config(data_dir)
    instruments = load_look_through_instruments(data_dir)
    shadow_targets = sleeve_cfg.get("shadow_targets_pct") or DEFAULT_SHADOW_TARGETS

    total = sum(p.current_value for p in positions)
    if total <= 0:
        total = 1.0

    sleeves: dict[SleeveType, float] = {
        "cash_short": 0.0,
        "kr_duration_bond": 0.0,
        "global_duration_bond": 0.0,
    }
    holdings: list[dict[str, Any]] = []

    for pos in positions:
        if getattr(pos, "asset_group", None) != "cash_short_bond":
            continue
        sleeve = resolve_sleeve(
            pos.ticker,
            style=getattr(pos, "style", "") or "",
            instruments=instruments,
            sleeve_cfg=sleeve_cfg,
        )
        w = _weight_pct(pos.current_value, total)
        sleeves[sleeve] += w
        holdings.append({
            "ticker": pos.ticker,
            "name": pos.name,
            "weight_pct": w,
            "shadow_sleeve": sleeve,
        })

    for k in sleeves:
        sleeves[k] = round(sleeves[k], 2)

    cash_short_bond_current = round(sleeves["cash_short"] + sleeves["kr_duration_bond"] + sleeves["global_duration_bond"], 2)

    v1_target = 40.0
    if allocation_groups:
        for g in allocation_groups:
            ag = getattr(g, "asset_group", None) or (g.get("asset_group") if isinstance(g, dict) else None)
            if ag == "cash_short_bond":
                v1_target = float(getattr(g, "final_target", None) or g.get("final_target") or v1_target)

    kr_bounds = shadow_targets.get("kr_duration_bond") or DEFAULT_SHADOW_TARGETS["kr_duration_bond"]
    cash_bounds = shadow_targets.get("cash_short") or DEFAULT_SHADOW_TARGETS["cash_short"]
    global_bounds = shadow_targets.get("global_duration_bond") or DEFAULT_SHADOW_TARGETS["global_duration_bond"]

    kr_gap = _gap_status(sleeves["kr_duration_bond"], kr_bounds)
    global_gap = _gap_status(sleeves["global_duration_bond"], global_bounds)
    cash_gap = _gap_status(sleeves["cash_short"], cash_bounds)

    diagnosis_parts: list[str] = []
    if cash_gap in {"overweight", "ok"} and sleeves["cash_short"] > float(cash_bounds.get("max", 20)):
        diagnosis_parts.append("단기채/현금 과다")
    elif cash_gap == "overweight":
        diagnosis_parts.append("cash_short 과다")
    if kr_gap == "absent":
        diagnosis_parts.append("중장기 국채 부재")
    elif kr_gap == "underweight":
        diagnosis_parts.append("kr_duration 부족")
    if global_gap in {"absent", "underweight"}:
        diagnosis_parts.append("global_duration 부족")
    if not diagnosis_parts:
        diagnosis_parts.append("shadow sleeve 균형 관찰")

    return {
        "execution_impact": "none — v1.0.2 unchanged",
        "v1_0_2_cash_short_bond_target_pct": round(v1_target, 2),
        "v1_0_2_cash_short_bond_current_pct": cash_short_bond_current,
        "cash_short_current_pct": sleeves["cash_short"],
        "kr_duration_bond_current_pct": sleeves["kr_duration_bond"],
        "global_duration_bond_current_pct": sleeves["global_duration_bond"],
        "shadow_targets_pct": shadow_targets,
        "kr_duration_bond_target_shadow_pct": kr_bounds,
        "duration_gap": kr_gap if kr_gap != "ok" else global_gap if global_gap != "ok" else cash_gap,
        "kr_duration_gap": kr_gap,
        "global_duration_gap": global_gap,
        "cash_short_gap": cash_gap,
        "diagnosis": " · ".join(diagnosis_parts),
        "note": "v1.0.2 execution unchanged — concept sleeve for v1.1b review",
        "holdings_split": holdings,
    }


def format_duration_report_line(status: dict[str, Any]) -> str:
    return (
        f"cash_short {status.get('cash_short_current_pct', 0)}% · "
        f"kr_duration {status.get('kr_duration_bond_current_pct', 0)}% "
        f"(shadow tgt {status.get('kr_duration_bond_target_shadow_pct', {}).get('target', '—')}%) · "
        f"gap `{status.get('duration_gap', '—')}` · "
        f"{status.get('diagnosis', '')}"
    )
