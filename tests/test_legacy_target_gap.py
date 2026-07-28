"""Legacy holdings vs rule-violation target-gap labeling (P4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from alpha_system.journal import append_record, clear_entries
from alpha_system.loader import load_config
from alpha_system.ui.services.context import _build_portfolio
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


def test_portfolio_copy_distinguishes_legacy() -> None:
    load_ui_copy.cache_clear()
    assert "레거시 보유" in copy_get("portfolio", "target_missing_legacy")
    assert "편입 규칙 위반" in copy_get("portfolio", "target_missing_violation")


def test_cuckoo_and_hgf_are_legacy_pending_not_violation(tmp_path: Path) -> None:
    """192400·453340: positions에 있으나 exit_targets 미기입 + 편입 저널 없음 → legacy."""
    clear_entries()
    cfg = load_config()
    root = Path(__file__).resolve().parents[1]
    positions = pd.read_csv(root / "data" / "positions.csv")
    kr = positions[positions["asset_group"] == "kr_alpha"].copy()
    targets = pd.DataFrame(columns=["ticker", "target_weight"])
    prices = pd.DataFrame()
    funds = pd.DataFrame()
    exit_path = root / "data" / "kr_alpha_exit_targets.yaml"

    rows = _build_portfolio(cfg, kr, targets, prices, funds, [], exit_path)
    by_t = {r.ticker: r for r in rows}

    assert "192400" in by_t
    assert "453340" in by_t
    assert by_t["192400"].has_target is False
    assert by_t["453340"].has_target is False
    assert by_t["192400"].target_gap_kind == "legacy_pending"
    assert by_t["453340"].target_gap_kind == "legacy_pending"
    assert "레거시" in by_t["192400"].target_detail
    assert "위반" not in by_t["192400"].target_detail

    # yaml에 목표가 있는 종목은 gap 없음
    assert by_t["005440"].has_target is True
    assert by_t["005440"].target_gap_kind == "none"

    # 신규 편입 저널이 있으면 같은 미기입도 규칙 위반
    append_record(
        action_kind="ENTRY_JOURNAL",
        as_of=date.today(),
        subject="192400",
        rationale="formal entry without target",
    )
    rows2 = _build_portfolio(cfg, kr, targets, prices, funds, [], exit_path)
    cuckoo = next(r for r in rows2 if r.ticker == "192400")
    assert cuckoo.target_gap_kind == "rule_violation"
    assert "편입 규칙 위반" in cuckoo.target_detail
    clear_entries()


def test_exit_yaml_excludes_cuckoo_and_hgf() -> None:
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "data" / "kr_alpha_exit_targets.yaml").read_text(encoding="utf-8"))
    tickers = set((data.get("tickers") or {}).keys())
    assert "192400" not in tickers
    assert "453340" not in tickers
