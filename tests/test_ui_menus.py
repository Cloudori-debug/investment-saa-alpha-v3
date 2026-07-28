from __future__ import annotations

from pathlib import Path

import pytest

from src.backtest.regime_backtest import run_regime_backtest, write_backtest_outputs
from src.backtest.saa_backtest import run_saa_backtest, write_saa_backtest_outputs
from src.backtest.alpha_backtest import run_alpha_lite_backtest, write_alpha_backtest_outputs

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_saa_backtest_static_weights(tmp_path):
    result = run_saa_backtest(DATA_DIR, profile=None)
    assert result.profile == "core_absolute_return"
    assert result.rows
    assert abs(sum(result.rows[0].weights.values()) - 100) < 0.01
    write_saa_backtest_outputs(result, tmp_path)
    assert (tmp_path / "saa_backtest_results.csv").exists()
    assert (tmp_path / "saa_backtest_report.md").exists()


def test_taa_backtest_writes_extended_outputs(tmp_path):
    hist = DATA_DIR / "market_indicators_history.csv"
    if not hist.exists():
        pytest.skip("market_indicators_history.csv missing")
    result = run_regime_backtest(DATA_DIR)
    write_backtest_outputs(result, tmp_path)
    assert (tmp_path / "taa_backtest_results.csv").exists()
    assert (tmp_path / "taa_backtest_report.md").exists()
    assert len(result.rows) >= 1
    assert result.rows[0].group_targets.get("kr_alpha", 0) >= 0


def test_alpha_backtest_report_includes_limitations(tmp_path):
    result = run_alpha_lite_backtest(DATA_DIR)
    write_alpha_backtest_outputs(result, tmp_path)
    text = (tmp_path / "alpha_backtest_report.md").read_text(encoding="utf-8")
    assert "한계" in text
    assert "6~8종" in text


def test_ui_panel_imports():
    from src.ui import (
        allocation_panel,
        alpha_panel,
        backtest_panel,
        compass_panel,
        dashboard_panel,
        integrated_portfolio_panel,
        nav_shortcuts,
    )

    assert callable(dashboard_panel.render_dashboard_page)
    assert callable(nav_shortcuts.apply_pending_navigation)
    assert callable(nav_shortcuts.navigate)
    assert callable(allocation_panel.render_allocation_page)
    assert callable(compass_panel.render_compass_page)
    assert callable(alpha_panel.render_alpha_page)
    assert callable(integrated_portfolio_panel.render_integrated_portfolio_page)
    assert callable(backtest_panel.render_backtest_page)
