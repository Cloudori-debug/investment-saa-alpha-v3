"""Scoring config load + five-factor contract (post CECS-T2 overlap cleanup)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SCORING_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"

# Correlation / report axes after §7.3 prelude cleanup
FIVE_FACTORS: tuple[str, ...] = (
    "score_q",
    "score_v",
    "score_sr",
    "score_r",
    "cecs",
)

# Backward-compatible alias (tests/docs may still mention seven briefly)
SEVEN_FACTORS = FIVE_FACTORS

# CECS subs that still enter the score
CECS_SCORE_SUB_FACTORS: tuple[str, ...] = (
    "execution_continuity",
    "pension_flow_score",
    "investment_purpose_flag",
    "policy_dependency_flag",
)

# Remapped out of score → T2 candidates
CECS_T2_MAPPED: tuple[str, ...] = (
    "disclosure_status",
    "independent_catalyst_flag",
)

# All CECS-related fields (score + mapped)
CECS_SUB_FACTORS: tuple[str, ...] = CECS_SCORE_SUB_FACTORS + CECS_T2_MAPPED


def load_scoring_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or SCORING_CONFIG_PATH
    with cfg_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"scoring YAML root must be a mapping: {cfg_path}")
    return data
