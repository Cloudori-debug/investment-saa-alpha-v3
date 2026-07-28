from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from src.config import load_yaml

PRESET_ORDER = ("aggressive", "standard", "conservative")

DEFAULT_PRESETS: dict[str, dict[str, Any]] = {
    "aggressive": {
        "label": "공격적 — 중소형 일부 포함",
        "description": "시총 3,000억+, 거래대금 10억/일. 알파 후보를 넓게.",
        "min_market_cap_krw": 300_000_000_000,
        "min_20d_avg_trading_value_krw": 1_000_000_000,
        "min_60d_avg_trading_value_krw": 800_000_000,
    },
    "standard": {
        "label": "표준 (권장) — 중형 이상",
        "description": "시총 5,000억+, 거래대금 15억/일. 균형.",
        "min_market_cap_krw": 500_000_000_000,
        "min_20d_avg_trading_value_krw": 1_500_000_000,
        "min_60d_avg_trading_value_krw": 1_200_000_000,
    },
    "conservative": {
        "label": "보수적 — 대형·준대형",
        "description": "시총 1조+, 거래대금 20억/일. 유동성·슬리피지 우선.",
        "min_market_cap_krw": 1_000_000_000_000,
        "min_20d_avg_trading_value_krw": 2_000_000_000,
        "min_60d_avg_trading_value_krw": 1_500_000_000,
    },
}

_LIQUIDITY_KEYS = (
    "min_market_cap_krw",
    "min_20d_avg_trading_value_krw",
    "min_60d_avg_trading_value_krw",
)


def format_krw_eok(amount: float | int) -> str:
    """원 → 억 원 표시."""
    eok = float(amount) / 100_000_000
    if eok >= 10_000:
        return f"{eok / 10_000:.1f}조"
    if eok == int(eok):
        return f"{int(eok):,}억"
    return f"{eok:,.1f}억"


def merged_presets(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    base = copy.deepcopy(DEFAULT_PRESETS)
    for name, spec in (cfg.get("presets") or {}).items():
        if name in base:
            base[name].update(spec)
        else:
            base[name] = spec
    return base


def resolve_universe_filter_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """active_preset → liquidity 블록에 반영."""
    out = copy.deepcopy(cfg)
    presets = merged_presets(out)
    name = str(out.get("active_preset", "standard"))
    if name not in presets:
        name = "standard"
    preset = presets[name]
    liq = out.setdefault("liquidity", {})
    for key in _LIQUIDITY_KEYS:
        if key in preset:
            liq[key] = preset[key]
    out["_resolved_preset"] = {
        "name": name,
        "label": preset.get("label", name),
        "description": preset.get("description", ""),
    }
    return out


def load_resolved_universe_filter(path: Path) -> dict[str, Any]:
    return resolve_universe_filter_config(load_yaml(path))


def save_active_preset(path: Path, preset_name: str) -> dict[str, Any]:
    if preset_name not in DEFAULT_PRESETS:
        raise ValueError(f"unknown preset: {preset_name}")
    cfg = load_yaml(path) if path.exists() else {}
    cfg.setdefault("presets", copy.deepcopy(DEFAULT_PRESETS))
    cfg["active_preset"] = preset_name
    preset = merged_presets(cfg)[preset_name]
    liq = cfg.setdefault("liquidity", {})
    for key in _LIQUIDITY_KEYS:
        liq[key] = preset[key]
    if "min_listed_days" not in liq:
        liq["min_listed_days"] = 252
    if "max_order_to_adv_ratio" not in liq:
        liq["max_order_to_adv_ratio"] = 0.05
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return resolve_universe_filter_config(cfg)


def preset_summary_rows(cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    presets = merged_presets(cfg or {})
    active = (cfg or {}).get("active_preset", "standard")
    rows = []
    for name in PRESET_ORDER:
        p = presets[name]
        rows.append({
            "preset": name,
            "label": str(p.get("label", name)),
            "시총 하한": format_krw_eok(p["min_market_cap_krw"]),
            "20일 거래대금": format_krw_eok(p["min_20d_avg_trading_value_krw"]),
            "active": "✓" if name == active else "",
        })
    return rows
