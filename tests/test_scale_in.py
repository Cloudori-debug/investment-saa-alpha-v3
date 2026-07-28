"""Scale-in schedule + anti full-dump (SCALE_IN_OPS_RULE)."""

from __future__ import annotations

from datetime import date

from alpha_system.entry.scale_in import (
    build_scale_in_plan,
    reject_full_dump,
    render_plan_markdown,
)


def test_three_equal_legs() -> None:
    plan = build_scale_in_plan(date(2026, 7, 19), n_legs=3)
    assert plan.n_legs == 3
    assert abs(sum(leg.fraction for leg in plan.legs) - 1.0) < 1e-9
    assert plan.legs[0].earliest_as_of == date(2026, 7, 19)
    assert plan.legs[1].earliest_as_of > plan.legs[0].earliest_as_of
    assert plan.max_single_day_fraction == 1.0 / 3.0


def test_reject_full_dump() -> None:
    assert reject_full_dump(requested_fraction_of_name_budget=1.0) is not None
    assert reject_full_dump(requested_fraction_of_name_budget=0.34) is not None
    assert reject_full_dump(requested_fraction_of_name_budget=1.0 / 3.0) is None
    assert reject_full_dump(requested_fraction_of_name_budget=0.30) is None


def test_markdown_mentions_rule() -> None:
    md = render_plan_markdown(
        build_scale_in_plan(date(2026, 7, 19)),
        rows=[("271560", "오리온", 20.0)],
    )
    assert "SCALE_IN" in md
    assert "leg1" in md.lower() or "1회차" in md
