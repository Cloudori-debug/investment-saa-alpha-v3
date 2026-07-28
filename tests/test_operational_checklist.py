from pathlib import Path
import json

from src.operational_checklist import (
    build_real_investment_checklist,
    build_executable_brief,
    _load_authoritative_state,
)

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = Path(__file__).resolve().parents[1] / "outputs"


def test_checklist_returns_items():
    items = build_real_investment_checklist(DATA, OUT)
    assert len(items) >= 7
    assert any(i.id == "R4" for i in items)


def test_executable_brief_contains_scope():
    text = build_executable_brief(DATA, OUT)
    assert "Executable" in text
    assert "dry-run" in text.lower() or "dry-run" in text


def test_authoritative_state_prefers_final_over_stale_acceptance(tmp_path):
  final = {
      "system_status": "YELLOW",
      "execution_scope": "ETF_ONLY",
      "alpha_approval": "RESTRICTED",
      "alpha_position_action": "RISK_REDUCE_ONLY",
      "dry_run_days": 3,
      "data_gate": "YELLOW",
      "data_gate_detail": {
          "summary": "통합 data_gate=YELLOW (portfolio=YELLOW, alpha=GREEN, health=YELLOW, base=YELLOW)",
          "health_gate": "YELLOW",
      },
  }
  stale_ac = {
      "overall": "RED",
      "execution_scope": "NO_TRADE",
      "alpha_approval": "BLOCKED",
      "dry_run_days": 3,
  }
  (tmp_path / "final_execution_decision.json").write_text(
      json.dumps(final), encoding="utf-8"
  )
  (tmp_path / "acceptance_report.json").write_text(
      json.dumps(stale_ac), encoding="utf-8"
  )

  state = _load_authoritative_state(tmp_path)
  assert state["execution_scope"] == "ETF_ONLY"
  assert state["overall"] == "YELLOW"
  assert state["alpha_approval"] == "RESTRICTED"

  items = build_real_investment_checklist(DATA, tmp_path)
  r2 = next(i for i in items if i.id == "R2")
  r7 = next(i for i in items if i.id == "R7")
  assert "ETF_ONLY" in r2.detail
  assert "RISK_REDUCE_ONLY" in r2.detail
  assert "risk-reduce" in r2.label.lower() or "Trim" in r2.label
  assert r2.status == "pass"
  assert r7.status == "pass"
  assert "YELLOW" in r7.detail
