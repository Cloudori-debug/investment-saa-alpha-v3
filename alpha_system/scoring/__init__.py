"""Scoring package — 5-factor + CECS (T2-mapped exclusions) + reports."""

from __future__ import annotations

from alpha_system.scoring.cecs import (
    CatalystInputs,
    T2_MAPPED_FROM_CECS,
    calculate_cecs,
    t2_candidate_signals,
)
from alpha_system.scoring.correlation import (
    CorrelationReport,
    CorrPair,
    SectorFallbackRow,
    analyze_factor_correlation,
    compute_sector_fallback_flags,
    data_requirements,
    render_correlation_markdown,
    write_correlation_report,
)
from alpha_system.scoring.engine import (
    NameScore,
    require_eligibility_decided,
    score_frame,
    score_name,
    scores_to_frame,
)
from alpha_system.scoring.factors import (
    CECS_SUB_FACTORS,
    CECS_T2_MAPPED,
    FIVE_FACTORS,
    SEVEN_FACTORS,
    load_scoring_config,
)
from alpha_system.scoring.overlap import write_overlap_report
from alpha_system.scoring.rescore import RescoreDecision, evaluate_rescore_triggers

__all__ = [
    "CECS_SUB_FACTORS",
    "CECS_T2_MAPPED",
    "CatalystInputs",
    "CorrelationReport",
    "CorrPair",
    "SectorFallbackRow",
    "FIVE_FACTORS",
    "NameScore",
    "RescoreDecision",
    "SEVEN_FACTORS",
    "T2_MAPPED_FROM_CECS",
    "analyze_factor_correlation",
    "compute_sector_fallback_flags",
    "calculate_cecs",
    "data_requirements",
    "evaluate_rescore_triggers",
    "load_scoring_config",
    "render_correlation_markdown",
    "require_eligibility_decided",
    "score_frame",
    "score_name",
    "scores_to_frame",
    "t2_candidate_signals",
    "write_correlation_report",
    "write_overlap_report",
]
