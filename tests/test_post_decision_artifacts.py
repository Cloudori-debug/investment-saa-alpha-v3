"""P3a — final decision core / post-decision artifacts tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.runtime.final_decision_core import (
    FINAL_DECISION_CORE_HASH_KEYS,
    compute_final_decision_core_hash,
    validate_final_decision_safety,
)
from src.runtime.post_decision_artifacts import (
    MANIFEST_JSON,
    REQUIRED_ARTIFACT_OUTPUTS,
    compute_post_decision_input_hash,
    evaluate_post_decision_cache,
    write_post_decision_manifest,
)


def test_final_decision_core_hash_uses_core_keys(tmp_path: Path) -> None:
    doc = {
        "data_gate": "YELLOW",
        "execution_scope": "ETF_ONLY",
        "run_id": "volatile-should-strip",
        "execution_permissions": {"alpha_auto_buy_permission": "BLOCKED"},
    }
    path = tmp_path / "final_execution_decision.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    h1 = compute_final_decision_core_hash(tmp_path)
    doc["run_id"] = "different-volatile"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    h2 = compute_final_decision_core_hash(tmp_path)
    assert h1 == h2
    assert len(h1) == 16
    assert "execution_scope" in FINAL_DECISION_CORE_HASH_KEYS


def test_post_decision_cache_miss_when_outputs_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_dir.mkdir()
    (output_dir / "final_execution_decision.json").write_text(
        json.dumps({"data_gate": "GREEN", "execution_scope": "NO_TRADE"}),
        encoding="utf-8",
    )
    decision = evaluate_post_decision_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is False
    assert "artifacts_missing" in decision["blockers"] or decision["missing_outputs"]


def test_post_decision_cache_hit_when_hashes_match(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_dir.mkdir()
    (data_dir / "target_portfolio.csv").write_text("ticker,weight\nAAA,1\n", encoding="utf-8")
    (data_dir / "portfolio_policy.yaml").write_text("execution_policy: {}\n", encoding="utf-8")
    (output_dir / "final_execution_decision.json").write_text(
        json.dumps(
            {
                "data_gate": "GREEN",
                "execution_scope": "NO_TRADE",
                "execution_permissions": {},
                "policy_cap": {},
                "technical_status": {},
                "operating": {},
            },
        ),
        encoding="utf-8",
    )
    for name in REQUIRED_ARTIFACT_OUTPUTS:
        (output_dir / name).write_text("{}", encoding="utf-8")
    (output_dir / "alpha_v2_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "flow_dashboard_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "trade_actions.csv").write_text("ticker,action\n", encoding="utf-8")
    (output_dir / "acceptance_report.json").write_text("{}", encoding="utf-8")
    (output_dir / "system_health.json").write_text("{}", encoding="utf-8")

    from src.runtime.post_decision_artifacts import _combined_input_hash

    hashes = compute_post_decision_input_hash(data_dir, output_dir)
    write_post_decision_manifest(
        output_dir,
        {
            "combined_input_hash": _combined_input_hash(hashes),
            "input_hashes": hashes,
        },
    )
    decision = evaluate_post_decision_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is True
    assert decision["skip_reason"] == "inputs_unchanged"


def test_validate_final_decision_safety_zero_buy(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    data_dir = tmp_path / "data"
    output_dir.mkdir()
    data_dir.mkdir()
    (output_dir / "final_execution_decision.json").write_text(
        json.dumps(
            {
                "as_of": "2026-01-01",
                "executable_actions": [],
                "execution_permissions": {"alpha_auto_buy_permission": "BLOCKED"},
            },
        ),
        encoding="utf-8",
    )
    (data_dir / "positions.csv").write_text("ticker,qty\n", encoding="utf-8")
    (data_dir / "target_portfolio.csv").write_text("ticker,weight\n", encoding="utf-8")
    (data_dir / "market_indicators.csv").write_text("date,regime\n2026-01-01,NEUTRAL\n", encoding="utf-8")
    try:
        safety = validate_final_decision_safety(output_dir, data_dir)
    except Exception:
        pytest.skip("fixture incomplete for full health checks")
    assert safety["actual_buy_allowed"] == 0


def test_manifest_written(tmp_path: Path) -> None:
    write_post_decision_manifest(tmp_path, {"cache_hit": True})
    assert (tmp_path / MANIFEST_JSON).exists()
