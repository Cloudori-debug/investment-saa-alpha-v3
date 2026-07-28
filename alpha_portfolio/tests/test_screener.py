from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline import run_pipeline


@pytest.fixture
def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_pipeline_runs(root: Path) -> None:
    result = run_pipeline(root, kr_alpha_weight=31.0)
    assert not result.scores.empty
    assert "composite_score" in result.scores.columns


def test_gate_passes_for_holdings(root: Path) -> None:
    result = run_pipeline(root, kr_alpha_weight=31.0)
    held = result.scores[result.scores["is_held"]]
    assert len(held) >= 8
    passed = int(held["gate_pass"].sum())
    assert passed >= max(1, len(held) // 2), f"gate pass {passed}/{len(held)}"


def test_exit_review_for_holdings(root: Path) -> None:
    result = run_pipeline(root, kr_alpha_weight=31.0)
    assert len(result.exit_review) == len(result.scores[result.scores["is_held"]])
    assert "action_suggested" in result.exit_review.columns


def test_candidates_sorted(root: Path) -> None:
    result = run_pipeline(root, kr_alpha_weight=31.0)
    if len(result.candidates) >= 2:
        scores = result.candidates["composite_score"].tolist()
        assert scores == sorted(scores, reverse=True)
