from __future__ import annotations

from src.models import DataGate

_GATE_RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def merge_data_gates(*gates: str | None) -> DataGate:
    """여러 gate 중 가장 보수적(RED > YELLOW > GREEN) 값."""
    best: DataGate = "GREEN"
    for g in gates:
        if not g:
            continue
        upper = str(g).upper()
        if upper not in _GATE_RANK:
            continue
        if _GATE_RANK[upper] > _GATE_RANK[best]:
            best = upper  # type: ignore[assignment]
    return best


def effective_data_gate(
    portfolio_gate: str,
    alpha_gate: str | None,
    *,
    merge_alpha: bool = True,
) -> DataGate:
    if not merge_alpha or not alpha_gate:
        return merge_data_gates(portfolio_gate)
    return merge_data_gates(portfolio_gate, alpha_gate)
