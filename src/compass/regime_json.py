from __future__ import annotations

from typing import Any

from src.compass.models import (
    CompassResult,
    P0_LIMITATIONS,
    PortfolioAllocation,
    SCHEMA_VERSION,
    TargetMismatchWarning,
)
from src.compass.profile_aliases import canonical_profile_name


def build_regime_json_payload(
    compass: CompassResult,
    allocation: PortfolioAllocation,
    *,
    mismatch_warnings: list[TargetMismatchWarning] | None = None,
    generated_at: str,
    tier2_used: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": compass.date,
        "profile": canonical_profile_name(allocation.profile),
        "tier2_used": tier2_used,
        "computed_market_phase": compass.market_phase.value,
        "computed_regime": compass.computed_regime.value,
        "manual_regime": compass.manual_regime,
        "applied_regime": compass.applied_regime.value,
        "override": compass.override.model_dump(),
        "compass_direction": compass.compass_direction,
        "scores": {
            "growth": compass.growth_score,
            "inflation": compass.inflation_score,
            "liquidity": compass.liquidity_score,
            "risk_appetite": compass.risk_appetite_score,
        },
        "score_breakdown": [item.model_dump() for item in compass.score_breakdown],
        "data_gate": compass.data_gate,
        "execution_level": compass.execution_level,
        "limitations": P0_LIMITATIONS,
        "allocation": {
            "profile": allocation.profile,
            "market_phase": allocation.market_phase.value,
            "applied_regime": allocation.applied_regime.value,
            "groups": [g.model_dump() for g in allocation.groups],
            "total_weight": allocation.total_weight,
            "notes": allocation.notes,
        },
        "template_vs_generated_target_warnings": [w.model_dump() for w in (mismatch_warnings or [])],
        # deprecated alias — 수동 템플릿 vs 나침반 생성 target 차이 (실행 Gap 아님)
        "target_mismatch_warnings": [w.model_dump() for w in (mismatch_warnings or [])],
        "economic_phase": compass.market_phase.value,
        "effective_regime": compass.applied_regime.value,
        "generated_at": generated_at,
    }
