"""CECS — post overlap cleanup: disclosure/independent_catalyst excluded from score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Accepted as inputs for T2 candidate mapping — NOT used in CECS weight sum
T2_MAPPED_FROM_CECS: tuple[str, ...] = (
    "disclosure_status",
    "independent_catalyst_flag",
)


@dataclass
class CatalystInputs:
    """CECS inputs. disclosure/independent are T2-mapped only (ignored in score)."""

    ticker: str
    name: str = ""
    factor_score_total: Optional[float] = None
    disclosure_status: float = 0.5  # T2 candidate source — not scored
    execution_continuity: float = 0.5
    pension_flow_score: float = 0.5
    investment_purpose_flag: float = 0.5
    independent_catalyst_flag: float = 0.5  # T2 candidate source — not scored
    policy_dependency_flag: float = 0.5


DEFAULT_CECS_WEIGHTS: dict[str, float] = {
    "execution_continuity": 0.40,
    "pension_flow_score": 0.30,
    "investment_purpose_flag": 0.30,
}


def calculate_cecs(
    profile: CatalystInputs,
    *,
    weights: dict[str, float] | None = None,
    policy_penalty_weight: float = 0.15,
) -> float:
    """
    CECS 0~100. Uses only non-overlapping subs (execution/pension/purpose).
    disclosure_status & independent_catalyst_flag are intentionally ignored.
    """
    raw = weights or DEFAULT_CECS_WEIGHTS
    clean = {
        k: float(v)
        for k, v in raw.items()
        if k not in T2_MAPPED_FROM_CECS
    }
    base_score = sum(getattr(profile, k) * wt for k, wt in clean.items())
    penalty = profile.policy_dependency_flag * policy_penalty_weight
    score = max(0.0, base_score - penalty)
    return round(score * 100, 2)


def t2_candidate_signals(profile: CatalystInputs) -> dict[str, float]:
    """Expose remapped CECS fields as T2 candidate source strengths (not triggers)."""
    return {
        "disclosure_status": profile.disclosure_status,
        "independent_catalyst_flag": profile.independent_catalyst_flag,
    }
