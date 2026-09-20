from __future__ import annotations

import pandas as pd

from src.gate import apply_gate


def _cfg() -> dict:
    return {"market_cap_min": 1, "avg_trading_value_20d_min": 1, "debt_ratio_max": 200}


def test_dart_verified_passes_gate() -> None:
    row = pd.Series(
        {
            "ticker": "011560",
            "market_cap": 3e11,
            "avg_trading_value_20d": 2e9,
            "verified": "dart",
            "audit_opinion": "unqualified",
            "debt_ratio": 80.0,
            "is_financial": False,
        }
    )
    assert apply_gate(row, _cfg()).pass_gate is True


def test_dart_high_debt_fails_after_fill() -> None:
    row = pd.Series(
        {
            "ticker": "011560",
            "market_cap": 3e11,
            "avg_trading_value_20d": 2e9,
            "verified": "dart",
            "audit_opinion": "unqualified",
            "debt_ratio": 350.0,
            "is_financial": False,
        }
    )
    out = apply_gate(row, _cfg())
    assert out.pass_gate is False
    assert "high_debt" in (out.fail_reason or "")
