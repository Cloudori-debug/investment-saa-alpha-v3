from __future__ import annotations

from dataclasses import dataclass, field

from src.models import DataGate, PositionRow, TargetRow


@dataclass
class ValidationResult:
    is_valid: bool
    data_gate: DataGate
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_inputs(
    positions: list[PositionRow],
    targets: list[TargetRow],
    policy: dict,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not positions:
        errors.append("positions.csv is empty")
    if not targets:
        errors.append("target_portfolio.csv is empty")

    for pos in positions:
        if pos.current_value <= 0:
            errors.append(f"{pos.ticker}: current_value must be positive")
        if not pos.ticker.strip():
            errors.append("missing ticker in positions")
        if not pos.name.strip():
            errors.append(f"{pos.ticker}: missing name")

    target_sum = sum(t.target_weight for t in targets)
    if abs(target_sum - 100.0) > 0.01:
        errors.append(f"target weights must sum to 100, got {target_sum:.2f}")

    for tgt in targets:
        if tgt.min_weight > tgt.max_weight:
            errors.append(f"{tgt.ticker}: min_weight > max_weight")
        if not (tgt.min_weight <= tgt.target_weight <= tgt.max_weight):
            warnings.append(f"{tgt.ticker}: target outside min/max band")

    risk = policy.get("risk_limits", {})
    if not risk:
        errors.append("portfolio_policy.yaml missing risk_limits")

    if errors:
        return ValidationResult(is_valid=False, data_gate="RED", errors=errors, warnings=warnings)
    if warnings:
        return ValidationResult(is_valid=True, data_gate="YELLOW", warnings=warnings)
    return ValidationResult(is_valid=True, data_gate="GREEN")
