"""Display format helpers for report phrase safety."""
from __future__ import annotations

from src.report.display_format import (
    fmt_pct,
    fmt_rate_pct,
    fmt_rate_pct_display,
    shadow_opportunity_action_label,
)


def test_fmt_pct_none() -> None:
    assert fmt_pct(None) == "N/A"
    assert fmt_pct("None") == "N/A"


def test_fmt_rate_insufficient_sample() -> None:
    assert fmt_rate_pct(None, closed_count=0) == "insufficient sample"
    assert fmt_rate_pct_display(None, closed_count=0) == "insufficient sample"
    assert fmt_rate_pct(62.5, closed_count=10) == "62.5"
    assert fmt_rate_pct_display(62.5, closed_count=10) == "62.5%"


def test_shadow_pilot_label() -> None:
    assert "shadow_pilot_candidate" in shadow_opportunity_action_label("pilot_entry_10")
    assert "execution prohibited" in shadow_opportunity_action_label("pilot_entry_10")
    assert "pilot_entry" not in shadow_opportunity_action_label("pilot_entry_10")
