from __future__ import annotations

from pathlib import Path

import yaml

from src.alpha.loaders import load_universe_filter_config
from src.alpha.universe_presets import (
    resolve_universe_filter_config,
    save_active_preset,
)


def test_resolve_standard_preset():
    cfg = {
        "active_preset": "standard",
        "presets": {},
        "liquidity": {"min_market_cap_krw": 1},
    }
    out = resolve_universe_filter_config(cfg)
    assert out["liquidity"]["min_market_cap_krw"] == 500_000_000_000
    assert out["_resolved_preset"]["name"] == "standard"


def test_resolve_conservative_preset():
    cfg = {"active_preset": "conservative", "presets": {}}
    out = resolve_universe_filter_config(cfg)
    assert out["liquidity"]["min_market_cap_krw"] == 1_000_000_000_000
    assert out["liquidity"]["min_20d_avg_trading_value_krw"] == 2_000_000_000


def test_save_and_load_preset(tmp_path):
    path = tmp_path / "universe_filter.yaml"
    path.write_text(
        yaml.dump({"active_preset": "aggressive", "presets": {}, "liquidity": {}}, allow_unicode=True),
        encoding="utf-8",
    )
    save_active_preset(path, "conservative")
    loaded = load_universe_filter_config(path)
    assert loaded["liquidity"]["min_market_cap_krw"] == 1_000_000_000_000
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["active_preset"] == "conservative"
