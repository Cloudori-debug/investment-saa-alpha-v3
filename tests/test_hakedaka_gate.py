"""Hakedaka gate stubs (cleanup phase 1) — value_list may be archived."""

from __future__ import annotations

from pathlib import Path

from src.hakedaka_gate import (
    ENABLE_HAKEDAKA,
    eligible_for_proposal_row,
    hakedaka_enabled,
    load_integration_config,
    merge_hakedaka_into_universe,
    proposal_sort_score,
    resolve_hakedaka_registry,
    tie_breaker_sort_boost,
)


def test_hakedaka_disabled_by_default() -> None:
    assert ENABLE_HAKEDAKA is False
    assert hakedaka_enabled() is False


def test_stubs_preserve_pure_qvm_sort() -> None:
    cfg = load_integration_config(Path("data"))
    assert cfg.get("proposal_mode", "pure_qvm") == "pure_qvm" or cfg.get("enabled") is False
    assert proposal_sort_score({"total_score": 60, "qvm_pure_score": 55}, cfg) == 55.0
    assert tie_breaker_sort_boost({}, 100.0, cfg) == 0.0
    assert eligible_for_proposal_row(
        {"grade": "B", "eligible_action": "BUY_CANDIDATE", "liquidity_pass": True},
        cfg,
    )
    assert resolve_hakedaka_registry(Path("data")) == []
    assert merge_hakedaka_into_universe([], Path("data")) == []
