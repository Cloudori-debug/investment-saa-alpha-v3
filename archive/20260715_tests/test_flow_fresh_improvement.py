"""Flow fresh ratio improvement — watched universe, cache, stale reasons."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.alpha.flow_refresh import _read_cache, refresh_investor_flows
from src.alpha_flow.flow_classifier import classify_stale_reason, summarize_stale_reasons
from src.alpha_flow.watched_universe import resolve_watched_universe_tickers


def test_classify_stale_reason_source_missing() -> None:
    assert classify_stale_reason(None) == "source_missing"
    assert classify_stale_reason({"source": "missing", "date": "2026-07-01"}) == "source_missing"


def test_classify_stale_reason_pykrx_failed() -> None:
    assert classify_stale_reason({"source": "auto_pykrx", "flow_signal": "STALE", "date": "2026-07-01"}, pykrx_failed=True) == "pykrx_fetch_failed"


def test_read_cache_within_threshold(tmp_path: Path) -> None:
    data = tmp_path / "data"
    cache_dir = data / "cache" / "flow_refresh"
    cache_dir.mkdir(parents=True)
    (cache_dir / "005830.json").write_text(
        '{"as_of": "2026-07-03", "row": {"date": "2026-07-03", "ticker": "005830", '
        '"flow_signal": "NEUTRAL", "source": "auto_pykrx", "staleness_days": 0, '
        '"foreign_5d_sum": 1.0, "institution_5d_sum": 2.0}}',
        encoding="utf-8",
    )
    row, status = _read_cache(data, "005830", "2026-07-05", max_age_days=3)
    assert status == "cache_hit"
    assert row is not None
    assert row.get("staleness_days", 0) >= 0


def test_watched_universe_includes_held_and_target(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    pd.DataFrame([
        {"ticker": "005830", "name": "DB", "asset_group": "kr_alpha", "quantity": 10,
         "current_value": 100, "sector": "insurance"},
    ]).to_csv(data / "positions.csv", index=False)
    pd.DataFrame([
        {"ticker": "005830", "name": "DB", "asset_group": "kr_alpha", "target_weight": 5,
         "min_weight": 0, "max_weight": 10, "sector": "insurance", "role": "core"},
    ]).to_csv(data / "target_portfolio.csv", index=False)
    tickers = resolve_watched_universe_tickers(data, out)
    assert any(t["ticker"] == "005830" for t in tickers)


def test_refresh_tracks_cache_metrics(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    cache_dir = data / "cache" / "flow_refresh"
    cache_dir.mkdir(parents=True)
    (cache_dir / "005830.json").write_text(
        '{"as_of": "2026-07-05", "row": {"date": "2026-07-05", "ticker": "005830", "name": "DB", '
        '"flow_signal": "NEUTRAL", "source": "auto_pykrx", "staleness_days": 0, '
        '"foreign_5d_sum": 100, "institution_5d_sum": 200, '
        '"foreign_5d_mcap_pct": 0.1, "institution_5d_mcap_pct": 0.1}}',
        encoding="utf-8",
    )
    with patch("src.data_refresh.pykrx_client.import_pykrx_stock", side_effect=ImportError("no krx")):
        result = refresh_investor_flows(
            data,
            [{"ticker": "005830", "name": "DB"}],
            as_of="2026-07-05",
            sleep_sec=0,
        )
    assert result.cache_hit_count >= 1
    assert "fresh" in result.stale_reason_summary or result.refreshed_count >= 1
    assert "+09:00" in result.last_successful_flow_refresh
    assert "Tpykrx" not in result.last_successful_flow_refresh


def test_build_flow_coverage_meta_ratios() -> None:
    from src.alpha_flow.flow_service import build_flow_coverage_meta

    meta = build_flow_coverage_meta(
        [{"flow_data_stale": False}, {"flow_data_stale": True}],
        as_of="2026-07-05",
    )
    assert meta["fresh_count"] == 1
    assert meta["stale_count"] == 1
    assert meta["fresh_ratio"] == 0.5
    assert meta["coverage_scope"] == "watched_universe"
