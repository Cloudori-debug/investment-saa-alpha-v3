from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.alpha.schemas import ALPHA_SCHEMA_VERSION, AlphaPipelineResult
from src.field_normalize import normalize_sector_fields_in_records, sanitize_json_value


def build_gpt_context(
    result: AlphaPipelineResult,
    regime: dict[str, Any] | None = None,
    asset_group_targets: dict[str, Any] | None = None,
    action_constraints: list[str] | None = None,
    kr_alpha_meta: dict[str, Any] | None = None,
    constraint_warnings: list[str] | None = None,
    portfolio_proposal: list[dict[str, Any]] | None = None,
    shortlist_meta: dict[str, Any] | None = None,
    *,
    executable_gate: str | None = None,
    policy_gate: str | None = None,
    health_gate: str | None = None,
    execution_scope: str | None = None,
    alpha_trade_permission: str | None = None,
    alpha_position_action: str | None = None,
) -> dict[str, Any]:
    constraints = list(action_constraints or [
        "자동 주문 금지",
        "target_portfolio.csv 자동 덮어쓰기 금지",
        "사람 승인 후 실행",
    ])
    if constraint_warnings:
        constraints.extend(constraint_warnings)

    return {
        "schema_version": ALPHA_SCHEMA_VERSION,
        "as_of": result.as_of,
        "regime": regime or {},
        "asset_group_targets": asset_group_targets or {},
        "kr_alpha_meta": kr_alpha_meta or {},
        "top_candidates": [c.model_dump() for c in result.candidates[:20]],
        "portfolio_proposal": normalize_sector_fields_in_records(portfolio_proposal or []),
        "shortlist_meta": shortlist_meta or {},
        "holdings_review": [h.model_dump() for h in result.holdings_review],
        "excluded_summary": _excluded_summary(result.excluded),
        "action_constraints": constraints,
        "data_limitations": result.limitations,
        "alpha_data_gate": result.data_gate,
        "execution_data_gate": executable_gate or result.data_gate,
        "data_gate": executable_gate or result.data_gate,
        "policy_gate": policy_gate,
        "health_gate": health_gate,
        "execution_scope": execution_scope,
        "alpha_trade_permission": alpha_trade_permission,
        "alpha_position_action": alpha_position_action,
    }


def _excluded_summary(excluded: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in excluded:
        counts[e.failed_rule] = counts.get(e.failed_rule, 0) + 1
    return counts


def write_gpt_context(path: Path, context: dict[str, Any]) -> None:
    clean = sanitize_json_value(context)
    path.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
