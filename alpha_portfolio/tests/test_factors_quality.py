from __future__ import annotations

import pandas as pd

from src.factors import quality_inputs_present, score_quality


def _cfg() -> dict:
    return {
        "quality": {
            "sub_weights": {"default": {"roe": 0.40, "opm": 0.25, "debt": 0.20, "earnings_stability": 0.15}},
            "roe_linear": {"low": 5, "high": 20},
            "debt_linear": {"low": 50, "high": 200, "invert": True},
        }
    }


def test_stub_quality_uses_trailing_roe_not_dummy_3y() -> None:
    dummy = pd.Series(
        {
            "source": "liquid_stub",
            "verified": "stub",
            "roe": 31.83,
            "roe_3y_avg": 10.0,
            "opm": None,
            "debt_ratio": 80.0,
            "is_financial": False,
            "is_holding": False,
            "sector": "기타금융",
            "net_income_y1": None,
            "net_income_y2": None,
        }
    )
    df = pd.DataFrame([dummy])
    # Dummy 3y=10 + debt=80 used to pin every stub at 50.83.
    q = score_quality(dummy, df, _cfg())
    assert q > 70.0
    assert quality_inputs_present(dummy) is True


def test_watch_dart_ignores_dummy_3y_roe() -> None:
    row = pd.Series(
        {
            "source": "opendart_watch",
            "verified": "dart",
            "roe": 19.38,
            "roe_3y_avg": 10.0,
            "opm": 18.7,
            "debt_ratio": 191.18,
            "is_financial": False,
            "is_holding": False,
            "sector": "기계·장비",
            "net_income_y1": 1.0,
            "net_income_y2": 1.0,
        }
    )
    q_trailing = score_quality(row, pd.DataFrame([row]), _cfg())
    row_dummy = row.copy()
    row_dummy["source"] = "manual"
    q_if_3y = score_quality(row_dummy, pd.DataFrame([row_dummy]), _cfg())
    assert q_trailing > q_if_3y


def test_stub_uses_dart_debt_when_present() -> None:
    row = pd.Series(
        {
            "source": "opendart_watch",
            "verified": "dart",
            "roe": 15.0,
            "roe_3y_avg": None,
            "opm": 12.0,
            "debt_ratio": 80.0,
            "is_financial": False,
            "is_holding": False,
            "sector": "기계·장비",
            "net_income_y1": 1.0,
            "net_income_y2": 1.0,
        }
    )
    df = pd.DataFrame([row])
    q = score_quality(row, df, _cfg())
    # ROE 15 → 66.7, OPM present, debt 80 invert → 80, earnings both profit → 85
    assert q > 60.0


def test_stub_without_trailing_roe_is_not_a_silent_pass() -> None:
    row = pd.Series(
        {
            "source": "liquid_stub",
            "verified": "stub",
            "roe": None,
            "roe_3y_avg": 10.0,
            "sector": "금속",
        }
    )
    assert quality_inputs_present(row) is False


def test_ops_composite_uses_core_weights_not_momentum() -> None:
    from src.screener import _composite

    scores = {"q": 50.0, "v": 50.0, "sr": 50.0, "r": 50.0, "m": 100.0}
    core = {"q": 0.35, "v": 0.30, "sr": 0.25, "r": 0.10, "m": 0.00}
    sat = {"q": 0.30, "v": 0.20, "sr": 0.15, "r": 0.10, "m": 0.25}
    assert _composite(core, scores) == 50.0
    assert _composite(sat, scores) == 62.5


def test_strip_stub_quality_placeholders_drops_dummy_3y() -> None:
    from src.collect.liquid_fundamentals import strip_stub_quality_placeholders

    df = pd.DataFrame(
        [
            {
                "ticker": "138930",
                "source": "liquid_stub",
                "verified": "stub",
                "roe": 7.22,
                "roe_3y_avg": 10.0,
                "debt_ratio": 80.0,
                "sector": "은행/금융지주",
                "is_financial": False,
            },
            {
                "ticker": "021240",
                "source": "manual",
                "verified": True,
                "roe": 18.2,
                "roe_3y_avg": 17.5,
                "debt_ratio": 45.3,
                "sector": "consumer",
                "is_financial": False,
            },
        ]
    )
    out = strip_stub_quality_placeholders(df)
    assert pd.isna(out.loc[0, "roe_3y_avg"])
    assert pd.isna(out.loc[0, "debt_ratio"])
    assert bool(out.loc[0, "is_financial"]) is True
    assert out.loc[1, "roe_3y_avg"] == 17.5
    assert out.loc[1, "debt_ratio"] == 45.3
    dart = pd.DataFrame(
        [
            {
                "ticker": "017800",
                "source": "opendart_watch",
                "verified": "dart",
                "roe": 19.38,
                "roe_3y_avg": 10.0,
                "debt_ratio": 191.18,
                "sector": "기계·장비",
                "is_financial": False,
            }
        ]
    )
    dart_out = strip_stub_quality_placeholders(dart)
    assert pd.isna(dart_out.loc[0, "roe_3y_avg"])
    assert dart_out.loc[0, "debt_ratio"] == 191.18
