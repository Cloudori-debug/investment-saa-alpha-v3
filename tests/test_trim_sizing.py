from src.trim_sizing import compute_trim_guidance, trim_config_from_rules


def test_trim_one_third_capped():
    g = compute_trim_guidance(-7.01, current_weight=23.67, step_fraction=1 / 3, max_step_ppt=2.0)
    assert g is not None
    assert g.suggested_step_ppt == 2.0
    assert g.overweight_ppt == 7.01


def test_trim_small_overweight():
    g = compute_trim_guidance(-3.1, current_weight=10.0, step_fraction=1 / 3, max_step_ppt=2.0)
    assert g is not None
    assert abs(g.suggested_step_ppt - 1.03) < 0.01


def test_trim_not_overweight():
    assert compute_trim_guidance(1.0, current_weight=5.0) is None


def test_config_from_rules():
    frac, mx = trim_config_from_rules({"position_triggers": {"trim_step_fraction": 0.25, "trim_max_single_step_ppt": 1.5}})
    assert frac == 0.25
    assert mx == 1.5
