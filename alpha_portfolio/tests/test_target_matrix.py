from __future__ import annotations

import pandas as pd
import pytest

from src.config_loader import load_yaml
from src.paths import get_paths
from src.target_matrix import build_target_draft, sleeve_to_portfolio


@pytest.fixture
def matrix_cfg():
    return load_yaml(get_paths()["config"] / "target_matrix.yaml")


def test_sleeve_to_portfolio():
    assert sleeve_to_portfolio(4.0, 31.0) == 1.24


def test_replace_pair(matrix_cfg):
    target = pd.DataFrame([
        {"ticker": "002380", "name": "KCC", "asset_group": "kr_alpha", "sector": "materials",
         "role": "cyclical_value", "target_weight": 3.0, "min_weight": 1.0, "max_weight": 5.0},
        {"ticker": "021240", "name": "코웨이", "asset_group": "kr_alpha", "sector": "consumer",
         "role": "quality_defensive", "target_weight": 4.0, "min_weight": 2.0, "max_weight": 6.0},
    ])
    scores = pd.DataFrame([
        {"ticker": "002380", "name": "KCC", "sector": "materials", "tier": "—", "grade": "Reject",
         "role_suggested": "value_quality", "portfolio_weight_suggested": 1.2, "sleeve_weight_suggested": 4.0, "is_held": True},
        {"ticker": "021240", "name": "코웨이", "sector": "consumer", "tier": "Core", "grade": "B",
         "role_suggested": "quality_defensive", "portfolio_weight_suggested": 1.24, "sleeve_weight_suggested": 4.0, "is_held": True},
        {"ticker": "006040", "name": "동원산업", "sector": "consumer", "tier": "Core", "grade": "B",
         "role_suggested": "dividend_value", "portfolio_weight_suggested": 1.3, "sleeve_weight_suggested": 4.0, "is_held": True},
    ])
    candidates = pd.DataFrame([
        {"ticker": "006040", "name": "동원산업", "sector": "consumer", "grade": "B", "rank": 1,
         "role_suggested": "dividend_value", "tier": "Core", "composite_score": 68,
         "portfolio_weight_suggested": 1.3, "sleeve_weight_suggested": 4.0},
    ])
    exit_review = pd.DataFrame([
        {"ticker": "002380", "action_suggested": "Replace", "exit_rule_id": "H05", "exit_reason": "reject_2w"},
    ])
    result = build_target_draft(target, scores, candidates, exit_review, matrix_cfg, kr_alpha_weight=31.0)
    assert "002380" not in result.draft["ticker"].values
    assert float(result.draft[result.draft["ticker"] == "006040"]["target_weight"].iloc[0]) > 0
    assert abs(result.draft["target_weight"].sum() - 31.0) < 1.0


def test_pipeline_produces_draft():
    from src.pipeline import run_pipeline

    result = run_pipeline(get_paths()["project"], kr_alpha_weight=31.0)
    assert result.target_draft is not None
    assert not result.target_draft.empty
    assert "target_weight" in result.target_draft.columns
