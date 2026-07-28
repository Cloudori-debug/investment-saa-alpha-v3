"""P3c — shadow history semantic snapshot cache tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.runtime.shadow_history_cache import (
    MANIFEST_JSON,
    REQUIRED_HISTORY_OUTPUTS,
    compute_semantic_snapshot_key,
    compute_semantic_snapshot_payload,
    evaluate_shadow_history_cache,
    maybe_append_shadow_history,
    write_shadow_history_manifest,
)


def _seed_base(data_dir: Path, output_dir: Path, *, market_date: str = "2026-01-15") -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\n005930,kr_alpha,1.0\n", encoding="utf-8",
    )
    (data_dir / "portfolio_policy.yaml").write_text("execution_policy: {}\n", encoding="utf-8")
    (data_dir / "positions.csv").write_text("ticker,qty,asset_group\n", encoding="utf-8")
    (data_dir / "market_indicators.csv").write_text(f"date,regime\n{market_date},NEUTRAL\n", encoding="utf-8")
    (output_dir / "final_execution_decision.json").write_text(
        json.dumps(
            {
                "as_of": market_date,
                "data_gate": "YELLOW",
                "execution_scope": "ETF_ONLY",
                "executable_actions": [],
                "execution_permissions": {"alpha_auto_buy_permission": "BLOCKED"},
            },
        ),
        encoding="utf-8",
    )
    (output_dir / "alpha_v2_summary.json").write_text(
        json.dumps({"coverage": {"candidate_count": 10}, "execution_context": {"execution_scope": "ETF_ONLY"}}),
        encoding="utf-8",
    )
    (output_dir / "flow_dashboard_summary.json").write_text(
        json.dumps({"fresh_ratio": 0.8, "stale_count": 2, "ticker_count": 50}),
        encoding="utf-8",
    )
    (output_dir / "alpha_shortlist_summary.json").write_text(
        json.dumps({"shortlist_eligible": 0}),
        encoding="utf-8",
    )
    (output_dir / "alpha_gate_diagnostics.json").write_text(
        json.dumps({"alpha_gate_status": "GREEN"}),
        encoding="utf-8",
    )
    for rel in REQUIRED_HISTORY_OUTPUTS:
        p = output_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("run_id,run_date\n", encoding="utf-8")


def test_semantic_key_stable_when_only_run_id_changes(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    p1 = compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15")
    k1 = compute_semantic_snapshot_key(p1)
    doc = json.loads((output_dir / "alpha_v2_summary.json").read_text(encoding="utf-8"))
    doc["run_id"] = "new-run-id"
    (output_dir / "alpha_v2_summary.json").write_text(json.dumps(doc), encoding="utf-8")
    p2 = compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15")
    k2 = compute_semantic_snapshot_key(p2)
    assert k1 == k2


def test_alpha_v2_summary_change_changes_key(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    k1 = compute_semantic_snapshot_key(
        compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15"),
    )
    (output_dir / "alpha_v2_summary.json").write_text(
        json.dumps({"coverage": {"candidate_count": 99}}),
        encoding="utf-8",
    )
    k2 = compute_semantic_snapshot_key(
        compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15"),
    )
    assert k1 != k2


def test_flow_summary_change_changes_key(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    k1 = compute_semantic_snapshot_key(
        compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15"),
    )
    (output_dir / "flow_dashboard_summary.json").write_text(
        json.dumps({"fresh_ratio": 0.1, "stale_count": 40}),
        encoding="utf-8",
    )
    k2 = compute_semantic_snapshot_key(
        compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15"),
    )
    assert k1 != k2


def test_target_hash_change_changes_key(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    k1 = compute_semantic_snapshot_key(
        compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15"),
    )
    (data_dir / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\n000660,kr_alpha,2.0\n", encoding="utf-8",
    )
    k2 = compute_semantic_snapshot_key(
        compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15"),
    )
    assert k1 != k2


def test_cache_hit_when_snapshot_key_matches(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    payload = compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15")
    key = compute_semantic_snapshot_key(payload)
    write_shadow_history_manifest(
        output_dir,
        {"semantic_snapshot_key": key, "latest_semantic_snapshot_key": key, "elapsed_seconds": 36.0},
    )
    decision = evaluate_shadow_history_cache(
        data_dir, output_dir, market_date="2026-01-15", run_mode="standard",
    )
    assert decision["cache_hit"] is True
    assert decision["snapshot_key_match"] is True


def test_quick_mode_append_forbidden(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    result = maybe_append_shadow_history(
        data_dir,
        output_dir,
        run_id="r1",
        run_date="2026-01-15",
        run_mode="quick",
    )
    assert result.append_executed is False


def test_bundle_only_no_append(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    result = maybe_append_shadow_history(
        data_dir,
        output_dir,
        run_id="r1",
        run_date="2026-01-15",
        run_mode="bundle_only",
    )
    assert result.append_executed is False


def test_maybe_append_cache_hit_skips_append(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_base(data_dir, output_dir)
    payload = compute_semantic_snapshot_payload(data_dir, output_dir, market_date="2026-01-15")
    key = compute_semantic_snapshot_key(payload)
    write_shadow_history_manifest(
        output_dir,
        {
            "semantic_snapshot_key": key,
            "latest_semantic_snapshot_key": key,
            "elapsed_seconds": 36.0,
            "last_ledger_summary": {
                "alpha_v2_shadow_history_updated": True,
                "flow_dashboard_history_updated": True,
                "buy_watch_count": 1,
                "target_write_occurred": False,
            },
        },
    )
    result = maybe_append_shadow_history(
        data_dir,
        output_dir,
        run_id="new-run-different-id",
        run_date="2026-01-15",
        run_mode="standard",
    )
    assert result.cache_hit is True
    assert result.append_executed is False
    assert result.snapshot_key_match is True
    manifest = json.loads((output_dir / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert manifest["safety_check"]["actual_buy_allowed"] == 0


def test_manifest_written(tmp_path: Path) -> None:
    write_shadow_history_manifest(tmp_path, {"cache_hit": True})
    assert (tmp_path / MANIFEST_JSON).exists()
