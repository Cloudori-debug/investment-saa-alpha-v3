from pathlib import Path

import json


def test_macro_scenario_writes(tmp_path):
    from src.value_list.macro_scenarios import write_macro_scenario

    data = Path(__file__).resolve().parents[1] / "data"
    out = tmp_path / "outputs"
    out.mkdir(parents=True)
    (out / "acceptance_report.json").write_text(
        json.dumps({
            "overall": "YELLOW",
            "dry_run_days": 5,
            "execution_scope": "ETF_ONLY",
        }),
        encoding="utf-8",
    )
    path = write_macro_scenario(data, out)
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["scenario_id"] in {"reform_success", "reform_delay", "stress_failure"}
    assert "ops_hint" in payload


def test_research_checklist(tmp_path):
    from src.value_list.research_checklist import write_research_checklist

    data = Path(__file__).resolve().parents[1] / "data"
    out = tmp_path / "outputs"
    out.mkdir(parents=True)
    (out / "acceptance_report.json").write_text(
        json.dumps({
            "overall": "YELLOW",
            "dry_run_days": 3,
            "execution_scope": "ETF_ONLY",
            "alpha_approval": "RESTRICTED",
        }),
        encoding="utf-8",
    )
    path = write_research_checklist(data, out)
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["items"]) == 10
    assert payload["summary"]["pass"] + payload["summary"]["warn"] + payload["summary"]["fail"] == 10


def test_alignment_score():
    from src.value_list.value_up_alignment import compute_alignment_score

    s = compute_alignment_score(
        fund={"pbr": "0.4", "operating_cash_flow": "100", "dividend_yield": "4"},
        dart={"alignment_pts": 25, "cancel_disclosure": True, "signal": "strong"},
    )
    assert s >= 80

    w = compute_alignment_score(
        fund={"pbr": "2.5", "operating_cash_flow": "-10"},
        dart={"alignment_pts": -12, "signal": "weak"},
    )
    assert w < 50
