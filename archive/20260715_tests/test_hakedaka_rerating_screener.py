from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.value_list.rerating_screener import (
    RERATING_DISCLAIMER,
    SCORE_WEIGHTS,
    build_rerating_rows,
    write_hakedaka_rerating_outputs,
)

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = Path(__file__).resolve().parents[1] / "outputs"


def test_score_weights_sum_to_one() -> None:
    assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9


def test_build_rerating_rows_count() -> None:
    rows = build_rerating_rows(DATA, OUT, as_of="2026-06-26")
    assert len(rows) >= 45
    assert all(r.shadow_only for r in rows)
    assert all(r.execution_authority == "none" for r in rows)
    assert all(r.ifrs18_relevance_flag for r in rows)


def test_write_rerating_outputs(tmp_path: Path) -> None:
    summary = write_hakedaka_rerating_outputs(
        DATA, tmp_path, as_of="2026-06-26", run_id="test-4a",
    )
    assert summary["shadow_only"] is True
    assert summary["authority"] == "none"
    assert (tmp_path / "hakedaka_catalyst_scores.csv").exists()
    assert (tmp_path / "hakedaka_preliminary_hunt_list.csv").exists()
    assert (tmp_path / "hakedaka_primary_hunt_list.csv").exists()
    assert (tmp_path / "hakedaka_qvm_overlap.csv").exists()
    assert (tmp_path / "hakedaka_group_forward_return.csv").exists()
    assert (tmp_path / "hakedaka_rerating_shadow.json").exists()

    catalyst = pd.read_csv(tmp_path / "hakedaka_catalyst_scores.csv")
    required = {
        "ticker", "hakedaka_total_score", "valuation_asset_score",
        "shareholder_return_score", "governance_catalyst_score",
        "accounting_transparency_score", "market_rerating_score",
        "value_trap_safety_score", "data_quality_score", "hunt_tier",
        "overlap_status", "shadow_only",
    }
    assert required.issubset(set(catalyst.columns))

    prelim = pd.read_csv(tmp_path / "hakedaka_preliminary_hunt_list.csv")
    assert not prelim.empty
    primary = pd.read_csv(tmp_path / "hakedaka_primary_hunt_list.csv")
    if not primary.empty:
        assert (primary["data_quality_score"].astype(float) >= 60).all()


def test_disclaimer_mentions_shadow() -> None:
    assert "shadow" in RERATING_DISCLAIMER.lower()
    assert "trade_actions" in RERATING_DISCLAIMER


def test_qvm_not_modified_by_rerating(tmp_path: Path) -> None:
    """Phase 4a must not touch alpha ranking artifacts."""
    import shutil

    if not (OUT / "alpha_candidates.csv").exists():
        return
    shutil.copy(OUT / "alpha_candidates.csv", tmp_path / "alpha_candidates.csv")
    before = (tmp_path / "alpha_candidates.csv").read_text(encoding="utf-8")
    write_hakedaka_rerating_outputs(DATA, tmp_path, as_of="2026-06-26")
    after = (tmp_path / "alpha_candidates.csv").read_text(encoding="utf-8")
    assert before == after
