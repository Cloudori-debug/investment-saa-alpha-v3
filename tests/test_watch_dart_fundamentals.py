from __future__ import annotations

import pandas as pd

from alpha_system.ui.services.watch_dart_fundamentals import (
    apply_watch_dart_rows,
    collect_watch_dart_financials,
    merge_watch_dart_row,
    watch_depth_tickers,
)


def test_watch_depth_is_top_n_gate_pass() -> None:
    scores = pd.DataFrame(
        [
            {"ticker": "000003", "composite_score": 90.0, "gate_pass": True},
            {"ticker": "000001", "composite_score": 80.0, "gate_pass": True},
            {"ticker": "000002", "composite_score": 99.0, "gate_pass": False},
            {"ticker": "000004", "composite_score": 70.0, "gate_pass": True},
        ]
    )
    assert watch_depth_tickers(scores, depth=2) == ["000003", "000001"]


def test_merge_watch_dart_fills_stub_quality_fields() -> None:
    row = pd.Series(
        {
            "ticker": "017800",
            "source": "liquid_stub",
            "verified": "stub",
            "roe": 7.0,
            "roe_3y_avg": 10.0,
            "opm": "",
            "debt_ratio": "",
            "per": 8.1,
            "pbr": 0.7,
        }
    )
    out = merge_watch_dart_row(
        row,
        {"opm": 12.5, "debt_ratio": 90.0, "roe": 11.2, "net_income_y1": 1e9, "net_income_y2": 8e8},
    )
    assert out["opm"] == 12.5
    assert out["debt_ratio"] == 90.0
    assert out["roe"] == 11.2
    assert out["per"] == 8.1
    assert out["source"] == "opendart_watch"
    assert out["verified"] == "dart"
    assert pd.isna(out["roe_3y_avg"])


def test_collect_watch_dart_uses_injected_fetch() -> None:
    def fake(ticker: str, as_of: str) -> dict:
        if ticker == "017800":
            return {"opm": 10.0, "debt_ratio": 40.0, "roe": 15.0}
        return {}

    filled, info = collect_watch_dart_financials(
        ["017800", "000001"],
        as_of="2026-09-05",
        fetch_one=fake,
    )
    assert info.requested == 2
    assert info.filled == 1
    assert "017800" in filled
    universe = pd.DataFrame(
        [{"ticker": "017800", "source": "liquid_stub", "opm": "", "debt_ratio": "", "roe": 7.0}]
    )
    merged = apply_watch_dart_rows(universe, filled)
    assert float(merged.iloc[0]["opm"]) == 10.0
