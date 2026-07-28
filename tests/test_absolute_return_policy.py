"""Absolute return mandate vs Core 14 ETF benchmark."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from src.alpha.target_portfolio_guard import TargetPortfolioWriteBlockedError
from src.exposure.absolute_return_policy import (
    aggregate_group_targets,
    build_absolute_return_target_rows,
    load_absolute_return_policy,
    write_absolute_return_target_portfolio,
)
from src.exposure.core_saa_reference import load_core_saa_reference

DATA = Path(__file__).resolve().parents[1] / "data"


def _policy_fixture_dir(tmp_path: Path) -> Path:
    for name in ("absolute_return_policy.yaml", "core_saa_reference.yaml", "core_etf_asset_group_map.yaml"):
        src = DATA / name
        if src.exists():
            shutil.copy(src, tmp_path / name)
    return tmp_path


def test_absolute_return_policy_loads() -> None:
    policy = load_absolute_return_policy(DATA)
    assert policy.get("primary_objective") == "beat_core_saa_benchmark_excess_return"


def test_target_portfolio_core_75_alpha_25() -> None:
    rows = build_absolute_return_target_rows(DATA)
    groups = aggregate_group_targets(rows)
    assert abs(sum(r["target_weight"] for r in rows) - 100.0) < 0.2
    assert abs(groups.get("kr_alpha", 0) - 24.25) < 0.1
    assert abs(groups.get("global_beta", 0) - 25.46) < 0.2
    assert groups.get("cash_short_bond", 0) >= 28.0
    tickers = {r["ticker"] for r in rows}
    assert "360750" in tickers
    assert "195930" in tickers
    assert "069500" not in tickers


def test_core_etfs_in_target_portfolio(tmp_path: Path) -> None:
    data = _policy_fixture_dir(tmp_path)
    write_absolute_return_target_portfolio(data, approve=True)
    text = (data / "target_portfolio.csv").read_text(encoding="utf-8-sig")
    assert "TIGER 미국S&P500" in text
    assert "KIWOOM 국고채10년" in text


def test_target_portfolio_requires_approval(tmp_path: Path) -> None:
    data = _policy_fixture_dir(tmp_path)
    with pytest.raises(TargetPortfolioWriteBlockedError):
        write_absolute_return_target_portfolio(data, approve=False)


def test_core_reference_primary_benchmark() -> None:
    ref = load_core_saa_reference(DATA)
    assert ref is not None
    assert ref["status"] == "primary_absolute_return_benchmark"
