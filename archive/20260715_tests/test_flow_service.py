"""P3: Common Flow API — stale policy, cache, unified counts."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.alpha_flow.flow_cache import load_cache_fallback_row
from src.alpha_flow.flow_classifier import (
    apply_execution_gates,
    apply_stale_policy,
    count_fresh_stale,
    is_flow_record_stale,
)
from src.alpha_v2.trigger_engine import build_flow_triggers


def _fresh_row(**extra: object) -> dict:
    base = {
        "ticker": "005830",
        "name": "DB",
        "grade": "A",
        "executable_universe": True,
        "flow_data_stale": False,
        "flow_confidence": "HIGH",
        "flow_signal_state": "accumulation",
        "flow_score": 5.0,
        "pension_net_buy_20d": 1e9,
        "pension_streak_direction": "buy",
        "pension_streak_days": 5,
        "pension_foreign_co_buy": True,
        "value_trap_flag": False,
        "liquidity_flag": True,
    }
    base.update(extra)
    return base


def _stale_row(**extra: object) -> dict:
    return apply_stale_policy({
        "ticker": "005830",
        "name": "DB",
        "grade": "A",
        "flow_data_stale": True,
        "flow_signal_state": "stale",
        "flow_confidence": "LOW",
        "pension_net_buy_20d": -1e9,
        "pension_streak_direction": "sell",
        "pension_streak_days": 5,
        **extra,
    })


def test_stale_does_not_create_buy_watch() -> None:
    buy, trim, _ = build_flow_triggers(
        [_stale_row()],
        actual_buy_allowed=1,
        no_trade=False,
        execution_scope="FULL_WITH_ALPHA",
        held_tickers=set(),
    )
    assert buy == []


def test_stale_does_not_create_trim_watch() -> None:
    buy, trim, _ = build_flow_triggers(
        [_stale_row()],
        actual_buy_allowed=1,
        no_trade=False,
        execution_scope="FULL_WITH_ALPHA",
        held_tickers={"005830"},
        positions_meta={"005830": {"profit_return": 20.0, "loss_return": 0.0}},
    )
    assert trim == []


def test_v2_and_dashboard_stale_count_same_basis() -> None:
    rows = [_fresh_row(ticker="005830"), _stale_row(ticker="035720")]
    v2_counts = count_fresh_stale(rows)
    dash_rows = [{"flow_data_stale": r.get("flow_data_stale")} for r in rows]
    dash_counts = count_fresh_stale(dash_rows)
    assert v2_counts == dash_counts


def test_actual_buy_allowed_zero_forces_buy_permission_false() -> None:
    buy, _, _ = build_flow_triggers(
        [_fresh_row()],
        actual_buy_allowed=0,
        no_trade=False,
        execution_scope="ETF_ONLY",
    )
    assert len(buy) == 1
    assert buy[0]["buy_permission"] is False


def test_no_trade_review_only_true() -> None:
    buy, trim, _ = build_flow_triggers(
        [_fresh_row()],
        actual_buy_allowed=1,
        no_trade=True,
        execution_scope="NO_TRADE",
    )
    assert buy[0]["review_only"] is True
    assert trim == [] or trim[0]["review_only"] is True


def test_cache_miss_fail_soft() -> None:
    data = Path("/nonexistent/data")
    row, warnings = load_cache_fallback_row(data, "005830", "2026-07-03")
    assert row["flow_signal"] == "STALE"
    assert warnings


def test_pykrx_fail_uses_prior_cache_with_stale_warning(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    existing = {
        "date": "2026-07-01",
        "ticker": "005830",
        "source": "auto_pykrx",
        "flow_signal": "NEUTRAL",
        "staleness_days": 0,
        "foreign_5d_sum": 1.0,
    }
    row, warnings = load_cache_fallback_row(data, "005830", "2026-07-03", existing=existing)
    assert is_flow_record_stale(row)
    assert any("stale fallback" in w for w in warnings)


def test_apply_execution_gates_no_trade() -> None:
    out = apply_execution_gates({}, actual_buy_allowed=1, no_trade=True, execution_scope="NO_TRADE")
    assert out["review_only"] is True
    assert out["buy_permission"] is False


def test_build_flow_coverage_meta_from_scored(tmp_path: Path) -> None:
    from src.alpha_flow.flow_service import build_flow_coverage_meta

    meta = build_flow_coverage_meta(
        [{"flow_data_stale": True}, {"flow_data_stale": False, "source": "auto_pykrx"}],
        as_of="2026-07-03",
        data_dir=tmp_path,
    )
    assert meta["stale_flow_count"] == 1
    assert meta["fresh_flow_count"] == 1


def test_signal_board_uses_unified_read_path(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame([{
        "date": "2026-07-01", "ticker": "005830", "name": "DB",
        "flow_signal": "STALE", "flow_score": 0, "source": "template", "staleness_days": 999,
    }]).to_csv(data / "investor_flows.csv", index=False)
    from src.alpha.alpha_signal_board import get_flow_for_ticker

    flow = get_flow_for_ticker(data, "005830")
    assert is_flow_record_stale(flow)


def test_alpha_v2_output_names_unchanged(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    expected = [
        "alpha_v2_scored.csv",
        "alpha_v2_summary.json",
        "alpha_v2_flow_triggers.csv",
    ]
    for name in expected:
        (out / name).write_text("", encoding="utf-8")
    for name in expected:
        assert (out / name).exists()
