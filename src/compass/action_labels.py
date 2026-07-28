"""Compass group action display labels — target-gap theory, not execution authority."""
from __future__ import annotations

COMPASS_ACTION_FOOTNOTE = (
    "> **Action = target-gap theory only** — not today's execution permission. "
    "Authoritative source: `final_execution_decision.json`."
)

_DEMAND_ACTIONS = frozenset({"Buy", "BuyCandidate", "WaitTrigger"})


def group_action_display_label(action: str, *, gap: float | None = None) -> str:
    if action in _DEMAND_ACTIONS:
        label = "Target Gap Demand"
        if gap is not None and gap >= 0.5:
            label += f" +{gap:.1f}%p"
        return f"{label} / Not executable today"
    if action == "Trim":
        return "Risk Demand"
    if action in {"Park", "Hold", "Wait"}:
        return "Target Gap"
    if action == "NoTrade":
        return "No Trade"
    return action
