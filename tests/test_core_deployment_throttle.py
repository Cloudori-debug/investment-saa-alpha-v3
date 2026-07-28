"""Phase AR-1 — Core deployment throttle and parity checks."""
from __future__ import annotations

import json
from pathlib import Path

from src.exposure.core_deployment_throttle import (
    apply_core_deployment_throttle,
    build_ar1_parity_check,
    load_core_benchmark_tickers,
    record_core_deployment_execution,
    sum_executed_deployment,
)
from src.models import GapRow, TradeAction

DATA = Path(__file__).resolve().parents[1] / "data"


def _gap(ticker: str, *, gap: float, group: str = "global_beta") -> GapRow:
    return GapRow(
        ticker=ticker,
        name=ticker,
        asset_group=group,
        current_weight=0.0,
        target_weight=gap,
        gap=gap,
        min_weight=0.0,
        max_weight=gap + 5,
        status="No position",
        in_target=True,
    )


def test_core_benchmark_tickers_include_sp500() -> None:
    tickers = load_core_benchmark_tickers(DATA)
    assert "360750" in tickers
    assert "069500" not in tickers


def test_throttle_blocks_yellow_gate() -> None:
    actions = [
        TradeAction(
            ticker="360750",
            name="S&P500",
            action="Buy-allowed",
            reason="test",
            allowed_size_pct=10.0,
            priority="Medium",
        )
    ]
    gaps = [_gap("360750", gap=12.0)]
    out, meta = apply_core_deployment_throttle(
        actions,
        gaps,
        data_dir=DATA,
        output_dir=DATA / ".." / "outputs",
        data_gate="YELLOW",
        dry_run_days=10,
        dry_run_required=10,
        as_of="2026-06-26",
    )
    assert out[0].action == "Wait"
    assert meta["gate_allowed"] is False


def test_throttle_caps_single_buy_at_3pct(tmp_path: Path) -> None:
    actions = [
        TradeAction(
            ticker="360750",
            name="S&P500",
            action="Buy-allowed",
            reason="test",
            allowed_size_pct=12.0,
            priority="Medium",
        )
    ]
    gaps = [_gap("360750", gap=12.0)]
    out, meta = apply_core_deployment_throttle(
        actions,
        gaps,
        data_dir=DATA,
        output_dir=tmp_path,
        data_gate="GREEN",
        dry_run_days=10,
        dry_run_required=10,
        as_of="2026-06-26",
    )
    assert out[0].action == "Buy-allowed"
    assert out[0].allowed_size_pct == 3.0
    assert meta["core_buy_throttled_count"] == 1


def test_weekly_ledger_limits_budget(tmp_path: Path) -> None:
    record_core_deployment_execution(
        tmp_path, date="2026-06-24", ticker="360750", deployed_pct=4.0,
    )
    assert sum_executed_deployment(tmp_path, as_of="2026-06-26", window_days=7) == 4.0

    actions = [
        TradeAction(
            ticker="360750",
            name="S&P500",
            action="Buy-allowed",
            reason="test",
            allowed_size_pct=3.0,
            priority="Medium",
        )
    ]
    gaps = [_gap("360750", gap=8.0)]
    out, meta = apply_core_deployment_throttle(
        actions,
        gaps,
        data_dir=DATA,
        output_dir=tmp_path,
        data_gate="GREEN",
        dry_run_days=10,
        dry_run_required=10,
        as_of="2026-06-26",
    )
    assert out[0].action == "Buy-allowed"
    assert out[0].allowed_size_pct == 1.0
    assert meta["usage"]["weekly_remaining_pct"] == 1.0


def test_ar1_parity_target_sum_100() -> None:
    parity = build_ar1_parity_check(
        DATA,
        DATA.parent / "outputs",
        data_gate="YELLOW",
        execution_scope="ETF_ONLY",
        dry_run_days=5,
    )
    assert parity["checks"]["target_sum_100"] is True
    assert parity["checks"]["core_sleeve_scaled"] is True
    assert parity["checks"]["cash_buffer_3"] is True
    assert abs(parity["core_sleeve_pct"] - 72.75) < 0.1
    assert abs(parity["alpha_sleeve_pct"] - 24.25) < 0.1
    assert parity["target_integrity"]["asset_group_target_sum_pct"] == 100.0


def test_ar1_parity_gate_red_uses_current_actions_not_stale_file(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "final_execution_decision.json").write_text(
        json.dumps({"final_trade_list": [{"ticker": "360750", "action": "Buy-allowed", "allowed_size_pct": 3.0}]}),
        encoding="utf-8",
    )
    parity = build_ar1_parity_check(
        DATA,
        out,
        actions=[],
        data_gate="RED",
        execution_scope="NO_TRADE",
        dry_run_days=6,
    )
    assert parity["checks"]["gate_red_final_trades_empty"] is True
    assert parity["final_trade_count"] == 0
    assert parity["executable_final_trade_count"] == 0
