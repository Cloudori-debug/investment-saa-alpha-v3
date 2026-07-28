"""Alpha Signal Board — Replace-review / Exit-review / Trim separation."""
from __future__ import annotations

from src.alpha.alpha_signal_board import derive_action_state


def test_replace_candidate_does_not_become_exit_without_thesis_damage() -> None:
    state, missing, blockers = derive_action_state(
        grade="C",
        eligible_action="NO_NEW",
        review_action="REPLACE_CANDIDATE",
        current_weight=5.0,
        target_weight=0.0,
        axis_passes=2,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="STALE",
    )
    assert state == "Replace-review"
    assert state != "Exit"
    assert missing.get("executable_replace") == "false"
    assert "screen_fail_or_low_score" in blockers


def test_overweight_generates_trim_not_exit() -> None:
    state, _, blockers = derive_action_state(
        grade="B",
        eligible_action="NO_NEW",
        review_action="KEEP",
        current_weight=9.0,
        target_weight=1.0,
        axis_passes=3,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="STALE",
    )
    assert state == "Trim"
    assert "position_overweight" in blockers


def test_thesis_damage_with_overweight_is_exit_not_trim() -> None:
    state, _, blockers = derive_action_state(
        grade="C",
        eligible_action="NO_NEW",
        review_action="REPLACE_CANDIDATE",
        current_weight=9.0,
        target_weight=1.0,
        axis_passes=1,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="STALE",
        hard_exit_triggers={"thesis_damage"},
    )
    assert state == "Exit"
    assert state != "Trim"
    assert "thesis_damage" in blockers


def test_hard_breach_with_overweight_is_exit_review_not_trim() -> None:
    state, _, blockers = derive_action_state(
        grade="C",
        eligible_action="NO_NEW",
        review_action="KEEP",
        current_weight=9.0,
        target_weight=1.0,
        axis_passes=1,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="STALE",
        hard_exit_triggers={"liquidity_crisis"},
    )
    assert state == "Exit-review"
    assert state != "Trim"
    assert "liquidity_crisis" in blockers


def test_exit_requires_thesis_damage_or_hard_breach() -> None:
    state_thesis, _, blockers_t = derive_action_state(
        grade="C",
        eligible_action="NO_NEW",
        review_action="REPLACE_CANDIDATE",
        current_weight=3.0,
        target_weight=1.0,
        axis_passes=1,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="STALE",
        hard_exit_triggers={"thesis_damage"},
    )
    assert state_thesis == "Exit"
    assert "thesis_damage" in blockers_t

    state_review, _, blockers_r = derive_action_state(
        grade="C",
        eligible_action="NO_NEW",
        review_action="KEEP",
        current_weight=3.0,
        target_weight=3.0,
        axis_passes=1,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="STALE",
        hard_exit_triggers={"liquidity_crisis"},
    )
    assert state_review == "Exit-review"
    assert "liquidity_crisis" in blockers_r


def test_executable_replace_separated_from_theoretical_replace() -> None:
    theoretical, missing_t, _ = derive_action_state(
        grade="C",
        eligible_action="NO_NEW",
        review_action="REPLACE_CANDIDATE",
        current_weight=2.0,
        target_weight=0.0,
        axis_passes=1,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="NEUTRAL",
        executable_replace=False,
    )
    executable, missing_e, _ = derive_action_state(
        grade="C",
        eligible_action="NO_NEW",
        review_action="REPLACE_CANDIDATE",
        current_weight=2.0,
        target_weight=0.0,
        axis_passes=1,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=True,
        data_gate="GREEN",
        flow_signal="NEUTRAL",
        executable_replace=True,
    )
    assert theoretical == executable == "Replace-review"
    assert missing_t.get("executable_replace") == "false"
    assert missing_e.get("executable_replace") == "true"
