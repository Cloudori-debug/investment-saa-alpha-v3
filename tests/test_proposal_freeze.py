"""Tests for weekly proposal freeze."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alpha_system.ui.services.proposal_freeze import (
    activate_freeze,
    assert_quant_refresh_allowed,
    freeze_feature_enabled,
    is_freeze_active,
    load_freeze,
    maybe_release_after_required_gates,
    pin_proposal_rows,
    release_freeze,
    set_freeze_feature_enabled,
)
from alpha_system.ui.services.refresh import run_quant_snapshot_refresh


def test_default_policy_keeps_quant_unlocked(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    assert freeze_feature_enabled(root) is False
    activate_freeze(
        root,
        report_id="WQR-TEST",
        as_of=date(2026, 7, 25),
        proposal_tickers=["138930"],
    )
    assert is_freeze_active(root) is False
    assert_quant_refresh_allowed(root)


def test_activate_and_block_refresh(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    set_freeze_feature_enabled(root, enabled=True)
    activate_freeze(
        root,
        report_id="WQR-TEST",
        as_of=date(2026, 7, 25),
        proposal_tickers=["138930", "030200"],
        proposal_names={"138930": "DB손보", "030200": "KT"},
    )
    assert is_freeze_active(root)
    fr = load_freeze(root)
    assert fr.tickers == ("138930", "030200")

    with pytest.raises(RuntimeError, match="고정"):
        assert_quant_refresh_allowed(root)

    result = run_quant_snapshot_refresh(root)
    assert result.ok is False
    assert "고정" in result.message
    assert result.detail.get("blocked_by") == "weekly_qual_proposal_freeze"


def test_pin_proposal_order(tmp_path: Path) -> None:
    class Row:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

    (tmp_path / "data").mkdir(exist_ok=True)
    set_freeze_feature_enabled(tmp_path, enabled=True)
    activate_freeze(
        tmp_path,
        report_id="WQR-TEST",
        as_of=date(2026, 7, 25),
        proposal_tickers=["030200", "138930"],
    )
    live = [Row("138930"), Row("021240"), Row("030200")]
    pinned = pin_proposal_rows(live, load_freeze(tmp_path))
    assert [r.ticker for r in pinned] == ["030200", "138930"]


def test_release_after_required_gates(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    set_freeze_feature_enabled(root, enabled=True)
    activate_freeze(
        root,
        report_id="WQR-TEST",
        as_of=date(2026, 7, 25),
        proposal_tickers=["138930"],
    )
    assert maybe_release_after_required_gates(
        root,
        {"approved": {"t2": True, "thesis": False, "targets": True, "cecs": False}},
    ) is False
    assert is_freeze_active(root)

    assert maybe_release_after_required_gates(
        root,
        {"approved": {"t2": True, "thesis": True, "targets": True, "cecs": False}},
    ) is True
    assert not is_freeze_active(root)
    fr = load_freeze(root)
    assert fr.active is False


def test_manual_release(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    set_freeze_feature_enabled(root, enabled=True)
    activate_freeze(
        root,
        report_id="WQR-TEST",
        as_of=date(2026, 7, 25),
        proposal_tickers=["138930"],
    )
    release_freeze(root, reason="manual test")
    assert not is_freeze_active(root)


def test_set_policy_false_releases_active_lock(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    set_freeze_feature_enabled(root, enabled=True)
    activate_freeze(
        root,
        report_id="WQR-TEST",
        as_of=date(2026, 7, 25),
        proposal_tickers=["138930"],
    )
    assert is_freeze_active(root)
    set_freeze_feature_enabled(root, enabled=False)
    assert freeze_feature_enabled(root) is False
    assert is_freeze_active(root) is False
