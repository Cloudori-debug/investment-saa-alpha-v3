from __future__ import annotations

from pathlib import Path

import pytest

from src.data_loader import load_positions, load_target_portfolio
from src.exposure.look_through import (
    build_exposure_lookthrough,
    format_exposure_markdown,
    load_asset_group_labels,
)


@pytest.fixture
def data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


def test_asset_group_labels_loaded(data_dir: Path) -> None:
    labels = load_asset_group_labels(data_dir)
    assert labels["global_beta"]["alias"] == "us_equity_proxy"
    assert labels["cash_short_bond"]["label"] == "현금·한국 단기채"


def test_exposure_rollup_us_equity(data_dir: Path) -> None:
    positions = load_positions(data_dir / "positions.csv")
    targets = load_target_portfolio(data_dir / "target_portfolio.csv")
    report = build_exposure_lookthrough(positions, targets, data_dir, as_of="2026-06-25")

    region_cur = report["by_dimension"]["region"]["current_pct"]
    assert region_cur.get("KR", 0) > region_cur.get("US", 0)

    ag = report["by_asset_group"]["current_pct"]
    assert "kr_alpha" in ag
    assert "cash_short_bond" in ag
    assert round(sum(ag.values()), 1) == pytest.approx(100.0, abs=0.5)

    tgt_sum = report["totals"]["target_weight_sum"]
    assert tgt_sum == pytest.approx(100.0, abs=1.0)


def test_global_beta_tagged_us(data_dir: Path) -> None:
    positions = load_positions(data_dir / "positions.csv")
    targets = load_target_portfolio(data_dir / "target_portfolio.csv")
    report = build_exposure_lookthrough(positions, targets, data_dir)
    sp = next(i for i in report["instruments"] if i["ticker"] == "360750")
    assert sp["look_through"]["region"] == "US"
    assert sp["look_through"]["asset_class"] == "equity"


def test_format_exposure_markdown_contains_region(data_dir: Path) -> None:
    report = build_exposure_lookthrough(
        load_positions(data_dir / "positions.csv"),
        load_target_portfolio(data_dir / "target_portfolio.csv"),
        data_dir,
    )
    md = format_exposure_markdown(report)
    assert "region" in md
    assert "진단 전용" in md


def test_summarize_exposure_concentration(data_dir: Path) -> None:
    from src.exposure.look_through import summarize_exposure_concentration

    report = build_exposure_lookthrough(
        load_positions(data_dir / "positions.csv"),
        load_target_portfolio(data_dir / "target_portfolio.csv"),
        data_dir,
    )
    line = summarize_exposure_concentration(report)
    assert "KR" in line
    assert "목표" in line
