"""Tests for scripts/validate_flow_refresh_run.py target + flow validation."""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _load_validate_module():
    path = ROOT / "scripts" / "validate_flow_refresh_run.py"
    spec = importlib.util.spec_from_file_location("validate_flow_refresh_run", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_flow_refresh_run"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _write_target(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _base_row(ticker: str, weight: float) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "asset_group": "kr_alpha",
        "sector": "tech",
        "role": "core",
        "target_weight": weight,
        "min_weight": 0,
        "max_weight": 20,
    }


def _setup_dirs(tmp_path: Path) -> tuple[Path, Path]:
    from src.alpha.target_portfolio_guard import _content_hash, _read_csv_rows

    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    rows = [_base_row("005830", 10.0)]
    _write_target(data / "user_target_portfolio.csv", rows)
    _write_target(data / "target_portfolio.csv", rows)
    op_hash = _content_hash(_read_csv_rows(data / "target_portfolio.csv"))
    (data / "target_portfolio_write_guard.json").write_text(
        json.dumps({"operational_target_hash": op_hash}),
        encoding="utf-8",
    )
    return data, out


def _write_min_flow_outputs(data: Path, out: Path) -> None:
    pd.DataFrame([
        {
            "ticker": "005830",
            "name": "DB",
            "flow_signal": "NEUTRAL",
            "source": "auto_pykrx",
            "action_state": "Hold",
        },
    ]).to_csv(out / "alpha_signal_board.csv", index=False)
    pd.DataFrame([
        {
            "ticker": "005830",
            "date": "2026-07-03",
            "flow_signal": "NEUTRAL",
            "source": "auto_pykrx",
            "foreign_5d_sum": "1",
            "institution_5d_sum": "1",
        },
    ]).to_csv(data / "investor_flows.csv", index=False)
    for fname in (
        "flow_daily_timeseries.csv",
        "flow_streaks.csv",
        "flow_leaderboard_pension.csv",
        "flow_leaderboard_foreign.csv",
        "flow_leaderboard_cobuy.csv",
    ):
        (out / fname).write_text("ticker\n005830\n", encoding="utf-8")
    (out / "flow_dashboard_summary.json").write_text(
        json.dumps({
            "fresh_count": 1,
            "stale_count": 0,
            "fresh_ratio": 1.0,
            "pykrx_failed_tickers": [],
            "last_successful_flow_refresh": "2026-07-06T00:22:59+09:00",
        }),
        encoding="utf-8",
    )
    (out / "gpt_context.json").write_text(
        json.dumps({
            "kr_alpha_meta": {
                "flow_refresh": {
                    "flow_coverage_pct": 100.0,
                    "stale_signal_count": 0,
                    "failed_tickers": [],
                },
            },
        }),
        encoding="utf-8",
    )
    (out / "alpha_report.md").write_text(
        "## Investor Flow Refresh\nflow_coverage_pct: 100\nstale_signal_count: 0\n",
        encoding="utf-8",
    )
    (out / "alpha_v2_summary.json").write_text(
        json.dumps({"target_write_occurred": False}),
        encoding="utf-8",
    )


def test_target_hash_match_user_passes(tmp_path: Path) -> None:
    vfr = _load_validate_module()
    data, out = _setup_dirs(tmp_path)
    result = vfr.validate_target_integrity(data, out)
    assert result.ok
    assert result.info["target_hash"] == result.info["user_target_hash"]


def test_target_hash_mismatch_user_fails(tmp_path: Path) -> None:
    vfr = _load_validate_module()
    data, out = _setup_dirs(tmp_path)
    _write_target(data / "target_portfolio.csv", [_base_row("005830", 15.0)])
    result = vfr.validate_target_integrity(data, out)
    assert not result.ok
    assert any("target_hash != user_target_hash" in msg for msg in result.target_fails)


def test_expected_target_hash_optional_fail(tmp_path: Path) -> None:
    vfr = _load_validate_module()
    data, out = _setup_dirs(tmp_path)
    current = vfr.validate_target_integrity(data, out).info["target_hash"]
    ok = vfr.validate_target_integrity(data, out, expected_target_hash=current)
    assert ok.ok
    bad = vfr.validate_target_integrity(data, out, expected_target_hash="deadbeef" * 8)
    assert not bad.ok
    assert any("--expected-target-hash" in msg for msg in bad.target_fails)


def test_target_write_occurred_fails(tmp_path: Path) -> None:
    vfr = _load_validate_module()
    data, out = _setup_dirs(tmp_path)
    (out / "alpha_v2_summary.json").write_text(
        json.dumps({"target_write_occurred": True}),
        encoding="utf-8",
    )
    result = vfr.validate_target_integrity(data, out)
    assert not result.ok
    assert any("target_write_occurred" in msg for msg in result.target_fails)


def test_flow_validation_passes_with_outputs(tmp_path: Path) -> None:
    vfr = _load_validate_module()
    data, out = _setup_dirs(tmp_path)
    _write_min_flow_outputs(data, out)
    result = vfr.run_validation(data, out)
    assert result.ok
    assert result.flow_fails == []


def test_flow_and_target_failures_are_separated(tmp_path: Path) -> None:
    vfr = _load_validate_module()
    data, out = _setup_dirs(tmp_path)
    _write_target(data / "target_portfolio.csv", [_base_row("005830", 20.0)])
    result = vfr.run_validation(data, out)
    assert result.target_fails
    assert result.flow_fails
    assert all(msg.startswith("[target]") for msg in result.target_fails)
    assert all(msg.startswith("[flow]") for msg in result.flow_fails)
