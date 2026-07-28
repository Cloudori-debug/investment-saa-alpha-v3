from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.compass.regime_auto import should_auto_sync_regime, sync_regime_from_compass
from src.compass.tier2_macro import load_macro_tier2
from src.data_refresh.tier2_refresh import refresh_macro_tier2
from src.models import MarketIndicators


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _fred_mock(base_url, *, series_id, api_key, transform):
    mapping = {
        "CPIAUCSL": (2.8, "2026-05-01", None),
        "T10Y2Y": (0.42, "2026-06-18", None),
        "BAMLH0A0HYM2": (3.85, "2026-06-18", None),
        "UMCSENT": (65.5, "2026-06-01", None),
    }
    if not api_key:
        return None, "", "FRED_API_KEY 미설정"
    val, dt, err = mapping.get(series_id, (None, "", "unknown"))
    if series_id == "BAMLH0A0HYM2" and val is not None:
        val = round(val * 100, 1)
    return val, dt, err


def _kosis_mock(base_url, query, *, api_key):
    if not api_key:
        return None, "", "KOSIS_API_KEY 미설정"
    target = query.get("target_field", "")
    if target == "cpi_kr_yoy":
        return 2.3, "202605", None
    if target == "pmi_kr":
        return 51.0, "202605", None
    return None, "", "empty"


def test_refresh_macro_tier2_with_mocks(tmp_path):
    import shutil

    shutil.copy(DATA_DIR / "macro_tier2.csv", tmp_path / "macro_tier2.csv")
    shutil.copy(DATA_DIR / "tier2_sources.yaml", tmp_path / "tier2_sources.yaml")
    shutil.copy(DATA_DIR / "market_indicators.csv", tmp_path / "market_indicators.csv")

    with patch("src.data_refresh.tier2_refresh.fetch_fred_field", side_effect=_fred_mock):
        with patch("src.data_refresh.tier2_refresh.fetch_kosis_field", side_effect=_kosis_mock):
            with patch("src.data_refresh.tier2_refresh._fred_api_key", return_value="test-fred"):
                with patch("src.data_refresh.tier2_refresh._kosis_api_key", return_value="test-kosis"):
                    result = refresh_macro_tier2(tmp_path, as_of="2026-06-20")

    assert result.path
    assert result.api_fields_fetched >= 4
    df = pd.read_csv(tmp_path / "macro_tier2.csv", dtype=str)
    row = df.iloc[-1]
    assert row["date"] == "2026-06-20"
    assert float(row["yield_spread_2y10y"]) == pytest.approx(0.42)
    assert (tmp_path / "tier2_provenance.json").exists()
    assert (tmp_path / "macro_tier2_history.csv").exists()


def test_refresh_preserves_on_api_failure(tmp_path):
    import shutil

    shutil.copy(DATA_DIR / "macro_tier2.csv", tmp_path / "macro_tier2.csv")
    shutil.copy(DATA_DIR / "tier2_sources.yaml", tmp_path / "tier2_sources.yaml")

    with patch("src.data_refresh.tier2_refresh.fetch_fred_field", return_value=(None, "", "network")):
        with patch("src.data_refresh.tier2_refresh.fetch_kosis_field", return_value=(None, "", "network")):
            with patch("src.data_refresh.tier2_refresh._fred_api_key", return_value="x"):
                with patch("src.data_refresh.tier2_refresh._kosis_api_key", return_value="y"):
                    result = refresh_macro_tier2(tmp_path, as_of="2026-06-21")

    df = pd.read_csv(tmp_path / "macro_tier2.csv", dtype=str)
    assert float(df.iloc[-1]["pmi_kr"]) == pytest.approx(51.2)
    assert any("이전값 유지" in w for w in result.warnings)


def test_load_macro_tier2_history_as_of(tmp_path):
    import shutil

    shutil.copy(DATA_DIR / "macro_tier2.csv", tmp_path / "macro_tier2.csv")
    hist = pd.DataFrame([
        {"date": "2026-06-10", "pmi_kr": "49", "pmi_us": "50", "cpi_kr_yoy": "2.0",
         "cpi_us_yoy": "2.5", "yield_spread_2y10y": "0.1", "hy_oas_bp": "400", "real_rate_kr": "1.5"},
    ])
    hist.to_csv(tmp_path / "macro_tier2_history.csv", index=False)

    macro = load_macro_tier2(tmp_path / "macro_tier2.csv", as_of="2026-06-12")
    assert macro is not None
    assert macro.pmi_kr == pytest.approx(49.0)


def test_should_auto_sync_regime():
    auto = MarketIndicators(date="2026-06-20", regime="AUTO")
    assert should_auto_sync_regime(auto) is True

    manual = MarketIndicators(
        date="2026-06-20",
        regime="YELLOW_STABLE",
        regime_expires_date="2026-07-01",
    )
    assert should_auto_sync_regime(manual) is False

    expired = MarketIndicators(
        date="2026-06-20",
        regime="YELLOW_STABLE",
        regime_expires_date="2026-06-01",
    )
    assert should_auto_sync_regime(expired) is True


def test_sync_regime_respects_manual_override(tmp_path):
    import shutil

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_dir = tmp_path / "outputs"
    for name in (
        "market_indicators.csv", "macro_tier2.csv", "compass_rules.yaml",
        "saa_profiles.yaml", "tier2_sources.yaml",
    ):
        shutil.copy(DATA_DIR / name, data_dir / name)

    # Force legacy override-respect mode even if live yaml is pure_auto.
    src = (data_dir / "tier2_sources.yaml").read_text(encoding="utf-8")
    if "regime_sync_mode:" in src:
        src = src.replace("regime_sync_mode: pure_auto", "regime_sync_mode: respect_override")
    else:
        src = "regime_sync_mode: respect_override\n" + src
    (data_dir / "tier2_sources.yaml").write_text(src, encoding="utf-8")

    mi = pd.read_csv(data_dir / "market_indicators.csv", dtype=str)
    mi.iloc[-1, mi.columns.get_loc("regime")] = "CAUTION"
    mi.iloc[-1, mi.columns.get_loc("regime_expires_date")] = "2099-01-01"
    mi.to_csv(data_dir / "market_indicators.csv", index=False)

    result = sync_regime_from_compass(data_dir, out_dir, as_of="2026-06-20")
    assert result.synced is False
    assert result.reason == "수동 레짐 유효 — override 유지"
    assert (out_dir / "regime_auto_suggestion.json").exists()


def test_sync_regime_pure_auto_overrides_manual(tmp_path):
    import shutil

    from src.compass.regime_auto import is_pure_auto_mode

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_dir = tmp_path / "outputs"
    for name in (
        "market_indicators.csv", "macro_tier2.csv", "compass_rules.yaml",
        "saa_profiles.yaml", "tier2_sources.yaml",
    ):
        shutil.copy(DATA_DIR / name, data_dir / name)

    src = (data_dir / "tier2_sources.yaml").read_text(encoding="utf-8")
    if "regime_sync_mode:" not in src:
        src = "regime_sync_mode: pure_auto\n" + src
    else:
        src = src.replace("regime_sync_mode: respect_override", "regime_sync_mode: pure_auto")
    (data_dir / "tier2_sources.yaml").write_text(src, encoding="utf-8")
    assert is_pure_auto_mode(data_dir=data_dir) is True

    mi = pd.read_csv(data_dir / "market_indicators.csv", dtype=str)
    mi.iloc[-1, mi.columns.get_loc("regime")] = "CAUTION"
    mi.iloc[-1, mi.columns.get_loc("regime_expires_date")] = "2099-01-01"
    mi.iloc[-1, mi.columns.get_loc("regime_override_reason")] = "manual hold"
    as_of = mi.iloc[-1]["date"]
    mi.to_csv(data_dir / "market_indicators.csv", index=False)

    result = sync_regime_from_compass(data_dir, out_dir, as_of=as_of)
    assert result.synced is True
    assert result.sync_mode == "pure_auto"
    assert result.applied_regime == result.computed_regime
    mi2 = pd.read_csv(data_dir / "market_indicators.csv", dtype=str)
    assert mi2.iloc[-1]["regime"] == result.computed_regime
    assert "pure" in str(mi2.iloc[-1]["regime_override_reason"])


def test_sync_regime_auto_when_neutral(tmp_path):
    import shutil

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_dir = tmp_path / "outputs"
    for name in (
        "market_indicators.csv", "macro_tier2.csv", "compass_rules.yaml",
        "saa_profiles.yaml", "tier2_sources.yaml",
    ):
        shutil.copy(DATA_DIR / name, data_dir / name)

    mi = pd.read_csv(data_dir / "market_indicators.csv", dtype=str)
    mi.iloc[-1, mi.columns.get_loc("regime")] = "AUTO"
    mi.iloc[-1, mi.columns.get_loc("regime_expires_date")] = ""
    mi.to_csv(data_dir / "market_indicators.csv", index=False)

    result = sync_regime_from_compass(data_dir, out_dir, as_of=mi.iloc[-1]["date"])
    assert result.synced is True
    assert result.applied_regime == result.computed_regime

    mi2 = pd.read_csv(data_dir / "market_indicators.csv", dtype=str)
    assert mi2.iloc[-1]["regime"] == result.computed_regime
