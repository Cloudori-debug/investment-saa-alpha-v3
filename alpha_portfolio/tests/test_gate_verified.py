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


def test_insurer_high_debt_exempt_via_sector() -> None:
    """DART rows often leave is_financial=false; sector must still skip high_debt."""
    row = pd.Series(
        {
            "ticker": "001450",
            "name": "현대해상",
            "sector": "손해보험",
            "market_cap": 3e12,
            "avg_trading_value_20d": 2e10,
            "verified": "dart",
            "audit_opinion": "unqualified",
            "debt_ratio": 651.2,
            "is_financial": False,
        }
    )
    out = apply_gate(row, _cfg())
    assert out.pass_gate is True
    assert out.fail_reason is None


def test_non_financial_name_with_high_debt_still_fails() -> None:
    row = pd.Series(
        {
            "ticker": "000000",
            "name": "일반제조",
            "sector": "기계·장비",
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
