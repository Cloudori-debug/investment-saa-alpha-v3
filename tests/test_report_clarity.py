"""Extended report clarity tests."""
from __future__ import annotations

import json
from pathlib import Path

from src.compass.action_labels import group_action_display_label
from src.report.execution_metrics import (
    build_execution_authority_lines,
    count_executable_actions,
    validate_report_clarity,
)


def _final_etf_only() -> dict:
    return {
        "system_status": "YELLOW",
        "execution_scope": "ETF_ONLY",
        "dry_run_days": 6,
        "operating": {"dry_run_required": 10},
        "allowed_actions": [
            {"ticker": "005440", "action": "Trim", "allowed_size_pct": -1.8},
            {"ticker": "360750", "action": "Wait", "allowed_size_pct": 0.0},
        ],
        "final_trade_list": [
            {"ticker": "005440", "action": "Trim", "allowed_size_pct": -1.8},
        ],
        "execution_permissions": {
            "core_etf_permission": "RESTRICTED",
            "alpha_auto_buy_permission": "BLOCKED",
            "alpha_research_permission": "ALLOWED",
            "main_block_reason": "dry_run 6/10",
            "kr_alpha_new_buy": "BLOCKED",
            "kr_alpha_replace": "BLOCKED",
        },
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
    }


def test_actual_buy_allowed_zero_when_policy_cap_etf_only() -> None:
    metrics = count_executable_actions(_final_etf_only())
    assert metrics["actual_buy_allowed_count"] == 0
    assert metrics["executable_buy_count"] == 0
    assert metrics["risk_reduce_trim_count"] == 1


def test_trim_not_counted_as_buy() -> None:
    metrics = count_executable_actions(_final_etf_only())
    assert metrics["executable_action_count"] == 0
    assert metrics["risk_reduce_trim_count"] == 1


def test_report_top_block_consistency_with_final_execution_decision() -> None:
    final = _final_etf_only()
    lines = build_execution_authority_lines(final)
    text = "\n".join(lines)
    assert "**Actual Buy Allowed**: 0" in text
    assert "**Buy candidates today**: 0" in text
    assert "**Allowed risk-reduce candidates**: 1" in text
    assert "**Alpha auto-buy permission**: **BLOCKED**" in text
    assert "**Risk-reduce Trim Candidates**: 1" in text
    assert "Trim proceeds" in text
    assert "6/10" in text


def test_buy_and_trim_sections_separated(tmp_path: Path) -> None:
    from src.report.execution_metrics import build_action_summary_section_lines

    out = tmp_path / "outputs"
    out.mkdir()
    final = _final_etf_only()
    (out / "final_execution_decision.json").write_text(json.dumps(final), encoding="utf-8")
    sections = build_action_summary_section_lines(final)
    text = "\n".join(sections)
    assert "### Buy candidates today" in text
    assert "### Allowed non-buy risk-reduce candidates" in text
    assert "005440" in text
    assert "Trim" in text
    buy_sec = text.split("### Buy candidates today", 1)[1].split("### Allowed non-buy", 1)[0]
    assert "005440" not in buy_sec


def test_no_buy_word_in_theoretical_compass_label() -> None:
    label = group_action_display_label("Buy", gap=26.3)
    assert "Buy" not in label.split("/")[0]
    assert "Not executable today" in label


def test_opportunity_heuristic_block_when_closed_lt_30(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "opportunity_analytics.json").write_text(
        json.dumps({"closed_signals": 0, "statistics_validated": False}),
        encoding="utf-8",
    )
    (out / "daily_report.md").write_text(
        "### Opportunity Analytics\n> **Heuristic only · Not statistically validated",
        encoding="utf-8",
    )
    (out / "daily_brief.json").write_text(
        json.dumps({"execution": {"actual_buy_allowed_count": 0, "executable_action_count": 0}, "market": {}}),
        encoding="utf-8",
    )
    (out / "final_execution_decision.json").write_text(json.dumps(_final_etf_only()), encoding="utf-8")
    result = validate_report_clarity(out)
    assert "Opportunity section missing" not in str(result.get("failures"))


def test_validate_fails_on_none_percent_and_pilot_entry(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "daily_report.md").write_text(
        "## 최종 실행 권위\npilot_entry_10\nNone%\n",
        encoding="utf-8",
    )
    (out / "daily_brief.json").write_text(
        json.dumps({
            "execution": {
                "actual_buy_allowed_count": 0,
                "executable_action_count": 0,
                "executable_buy_count": 0,
                "allowed_risk_reduce_action_count": 1,
                "risk_reduce_trim_count": 1,
            },
            "market": {},
        }),
        encoding="utf-8",
    )
    (out / "final_execution_decision.json").write_text(json.dumps(_final_etf_only()), encoding="utf-8")
    result = validate_report_clarity(out)
    assert result["pass"] is False
    assert any("None%" in f for f in result["failures"])
