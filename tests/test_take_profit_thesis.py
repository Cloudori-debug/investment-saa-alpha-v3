"""Take-profit / thesis-break pure assessment tests (EXIT_TAKEPROFIT_THESIS_SPEC)."""

from __future__ import annotations

import ast
from pathlib import Path

from src.alpha.take_profit_thesis import (
    apply_momentum_counter_check,
    assess_take_profit,
    assess_thesis_break,
    compute_leg_proximity,
    default_bands,
    format_proximity_display,
    resolve_partial_frac_from_strength,
    trim_source_tag_tp,
)

MODULE = Path(__file__).resolve().parents[1] / "src" / "alpha" / "take_profit_thesis.py"


def test_resolve_partial_frac_stair_steps() -> None:
    bands = default_bands()
    assert resolve_partial_frac_from_strength(65, bands) == 0.0
    assert resolve_partial_frac_from_strength(70, bands) == 0.10
    assert resolve_partial_frac_from_strength(75, bands) == 0.10
    assert resolve_partial_frac_from_strength(79.9, bands) == 0.10
    assert resolve_partial_frac_from_strength(80, bands) == 0.20
    assert resolve_partial_frac_from_strength(85, bands) == 0.20
    assert resolve_partial_frac_from_strength(90, bands) == 0.30
    assert resolve_partial_frac_from_strength(95, bands) == 0.30
    assert resolve_partial_frac_from_strength(100, bands) == 0.30


def test_momentum_counter_check_val_steps_down() -> None:
    bands = default_bands()
    frac, applied = apply_momentum_counter_check(
        0.30, exit_leg="VAL", momentum_score=82, bands=bands, momentum_override_threshold=70,
    )
    assert applied is True
    assert frac == 0.20
    frac2, applied2 = apply_momentum_counter_check(0.10, exit_leg="VAL", momentum_score=82, bands=bands)
    assert applied2 is True
    assert frac2 == 0.0


def test_momentum_counter_check_skips_fund_and_none() -> None:
    bands = default_bands()
    frac, applied = apply_momentum_counter_check(0.30, exit_leg="FUND", momentum_score=82, bands=bands)
    assert applied is False
    assert frac == 0.30
    frac_n, applied_n = apply_momentum_counter_check(0.30, exit_leg="VAL", momentum_score=None, bands=bands)
    assert applied_n is False
    assert frac_n == 0.30


def test_tp_a_only_trim_fund() -> None:
    a = assess_take_profit(
        "021240",
        fundamentals={"roe": 18.0},
        prices={},
        targets={"fundamental": {"roe_min": 15.0}, "valuation": {}},
        momentum_score=80,
    )
    assert a.fund_hit is True
    assert a.val_hit is False
    assert a.exit_leg == "FUND"
    assert a.suggested_action == "Trim"
    assert a.momentum_override_applied is False
    assert a.partial_frac == 0.30
    assert "카운터체크" not in a.rationale
    assert trim_source_tag_tp(a) == "trim:TP-A"


def test_tp_b_only_trim_val_with_momentum_down() -> None:
    a = assess_take_profit(
        "005930",
        fundamentals={"pbr": 3.0},
        prices={"valuation_score": 88.0},
        targets={"valuation": {"pbr_max": 2.5}},
        momentum_score=82,
    )
    assert a.val_hit is True
    assert a.exit_leg == "VAL"
    assert a.suggested_action == "Trim"
    assert a.momentum_override_applied is True
    assert a.partial_frac == 0.10
    assert "카운터체크" in a.rationale
    assert trim_source_tag_tp(a) == "trim:TP-B"


def test_tp_both_exit_review_or_trim() -> None:
    a = assess_take_profit(
        "000660",
        fundamentals={"roe": 20.0, "pbr": 4.0},
        prices={"valuation_score": 95.0},
        targets={"fundamental": {"roe_min": 15.0}, "valuation": {"pbr_max": 2.0}},
        momentum_score=40,
    )
    assert a.exit_leg == "BOTH"
    assert a.suggested_action in {"Trim", "Exit-review"}
    assert a.fund_hit and a.val_hit
    assert trim_source_tag_tp(a) == "trim:TP-BOTH"


def test_targets_missing_hold() -> None:
    a = assess_take_profit("123456", fundamentals={}, prices={}, targets={})
    assert a.targets_missing is True
    assert a.exit_leg == "NONE"
    assert a.suggested_action == "Hold"
    assert trim_source_tag_tp(a) == "targets_missing"
    assert a.fund_proximity_pct is None and a.val_proximity_pct is None
    assert format_proximity_display(None, None, targets_missing=True, exit_leg="NONE") == "—"


def test_leg_proximity_kt_and_dongwon() -> None:
    # KT: pbr 0.72 / 0.86 ≈ 83.7% VAL
    f_kt, v_kt = compute_leg_proximity(
        {"pbr": 0.72, "roe": 9.72},
        {"valuation": {"pbr_max": 0.86}},
    )
    assert f_kt is None
    assert v_kt == 83.7
    # 동원: FUND 11/13.5≈81.5, VAL 0.41/0.53≈77.4
    f_dw, v_dw = compute_leg_proximity(
        {"roe": 11.0, "pbr": 0.41},
        {"fundamental": {"roe_min": 13.5}, "valuation": {"pbr_max": 0.53}},
    )
    assert f_dw == 81.5
    assert v_dw == 77.4
    label = format_proximity_display(f_dw, v_dw, targets_missing=False, exit_leg="NONE")
    assert "FUND 81.5% 근접" in label and "VAL 77.4% 근접" in label
    assert format_proximity_display(100.0, 100.0, targets_missing=False, exit_leg="VAL") == "도달"


def test_thesis_break_priority() -> None:
    tb = assess_thesis_break("005930", flags={"thesis_damage": True})
    assert tb.active and tb.rule_id == "TB-01" and tb.suggested_action == "Exit"
    pol = assess_thesis_break("005930", flags={"policy_retreat": True})
    assert pol.rule_id == "TB-02" and pol.suggested_action == "Demote-review"
    acc = assess_thesis_break("005930", flags={"accounting_issue": True})
    assert acc.rule_id == "TB-03"


def test_no_probability_wording_in_outputs() -> None:
    src = MODULE.read_text(encoding="utf-8")
    # Ban must be documented; outputs must not use forbidden audience terms.
    assert "신호강도" in src or "signal_strength" in src
    a = assess_take_profit(
        "021240",
        fundamentals={"roe": 18.0, "pbr": 3.0},
        prices={"valuation_score": 88.0},
        targets={"fundamental": {"roe_min": 15.0}, "valuation": {"pbr_max": 2.5}},
        momentum_score=82,
    )
    blob = " ".join([a.rationale, a.strength_components, a.suggested_action, a.exit_leg])
    for term in ("확률", "승률", "성공확률", "적중률", "도달확률", "예상확률"):
        assert term not in blob
    assert "proximity" in src or "근접도" in src
    assert "확률" not in format_proximity_display(83.7, None, targets_missing=False, exit_leg="NONE")
    assert "근접" in format_proximity_display(83.7, None, targets_missing=False, exit_leg="NONE")


def test_rationale_includes_counter_check_reason() -> None:
    a = assess_take_profit(
        "005930",
        fundamentals={"pbr": 5.0},
        prices={"valuation_score": 92.0},
        targets={"valuation": {"pbr_max": 2.0}},
        momentum_score=75,
    )
    assert a.momentum_override_applied is True
    assert "카운터체크" in a.rationale
