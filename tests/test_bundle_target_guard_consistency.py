"""Bundle target_portfolio_guard snapshot consistency."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.validation.bundle_consistency import (
    apply_target_guard_conflict_lock,
    detect_target_guard_conflict,
    finalize_health_snapshot,
    resync_guard_lock_after_bundle_write,
)
from src.validation.system_health import write_health_report


def _write_target(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _row(ticker: str, weight: float) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "asset_group": "kr_alpha",
        "sector": "tech",
        "role": "core",
        "target_weight": weight,
        "min_weight": 0,
        "max_weight": 20,
    }


def test_detect_target_guard_conflict_when_severity_differs(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    health = {
        "checks": [{
            "name": "target_portfolio_guard",
            "detail": {"severity": "FAIL", "current_hash": "aaa", "changed_rows": 5},
        }],
    }
    acceptance = {
        "items": [{
            "name": "target_portfolio_guard",
            "detail": {"severity": "PASS", "current_hash": "bbb", "changed_rows": 0},
        }],
    }
    final = {"execution_permissions": {"gates": {"target_portfolio_guard": "PASS"}}}
    (out / "system_health.json").write_text(json.dumps(health), encoding="utf-8")
    (out / "acceptance_report.json").write_text(json.dumps(acceptance), encoding="utf-8")
    (out / "final_execution_decision.json").write_text(json.dumps(final), encoding="utf-8")

    conflict = detect_target_guard_conflict(out)
    assert conflict["conflict_detected"] is True
    assert conflict["guard_fail"] is True


def test_apply_target_guard_conflict_lock_zeros_buys() -> None:
    final = {
        "allowed_actions": [
            {"ticker": "035420", "action": "Buy-allowed", "allowed_size_pct": 2.0},
            {"ticker": "005440", "action": "Trim", "allowed_size_pct": -2.0, "reason": "risk"},
        ],
        "final_trade_list": [{"ticker": "035420", "action": "Buy-allowed", "allowed_size_pct": 2.0}],
        "execution_permissions": {"gates": {}, "allowed_capabilities": ["ETF_REBALANCE"]},
    }
    locked = apply_target_guard_conflict_lock(final, {"conflict_detected": True, "guard_fail": True, "health_severity": "FAIL"})
    assert locked["target_guard_conflict_detected"] is True
    assert locked["execution_scope"] == "NO_TRADE"
    assert not any(a["action"] == "Buy-allowed" for a in locked["allowed_actions"])
    assert any(a["action"] == "Trim" for a in locked["allowed_actions"])


def test_apply_target_guard_conflict_lock_clears_sticky_flag() -> None:
    final = {
        "target_guard_conflict_detected": True,
        "execution_permissions": {
            "target_guard_conflict_detected": True,
            "main_block_reason": "target_guard_conflict_detected",
            "gates": {"target_portfolio_guard": "FAIL"},
            "trim_policy": {"target_guard_conflict": True},
        },
    }
    cleared = apply_target_guard_conflict_lock(
        final,
        {"conflict_detected": False, "guard_fail": False, "health_severity": "PASS"},
    )
    assert cleared["target_guard_conflict_detected"] is False
    perms = cleared["execution_permissions"]
    assert perms["target_guard_conflict_detected"] is False
    assert "main_block_reason" not in perms
    assert perms["gates"]["target_portfolio_guard"] == "PASS"
    assert perms["trim_policy"]["target_guard_conflict"] is False


def test_resync_guard_lock_clears_transient_bundle_mismatch(tmp_path: Path) -> None:
    """Pre-bundle snapshot mismatch lock must clear after bundle is aligned."""
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    snap = "aaaaaaaaaaaaaaaa"
    guard = {
        "severity": "PASS",
        "current_hash": "abc123",
        "changed_rows": 0,
        "system_proposal_leak_count": 0,
    }
    health_doc = {
        "meta": {"health_snapshot_id": snap},
        "health_snapshot_id": snap,
        "checks": [{"name": "target_portfolio_guard", "detail": guard}],
    }
    acceptance_doc = {
        "health_snapshot_id": snap,
        "target_hash": "abc123",
        "items": [{"name": "target_portfolio_guard", "detail": guard}],
        "overall": "YELLOW",
        "execution_scope": "ETF_ONLY",
    }
    final_doc = {
        "as_of": "2026-07-10",
        "execution_scope": "NO_TRADE",
        "system_status": "RED",
        "target_guard_conflict_detected": True,
        "execution_permissions": {
            "target_guard_conflict_detected": True,
            "main_block_reason": "target_guard_conflict_detected",
            "gates": {"target_portfolio_guard": "PASS"},
        },
        "allowed_actions": [],
        "final_trade_list": [],
    }
    stale_bundle = {
        "health_snapshot_id": "bbbbbbbbbbbbbbbb",
        "health_report": {"meta": {"health_snapshot_id": "bbbbbbbbbbbbbbbb"}},
        "target_hash": "abc123",
    }
    (out / "system_health.json").write_text(json.dumps(health_doc), encoding="utf-8")
    (out / "acceptance_report.json").write_text(json.dumps(acceptance_doc), encoding="utf-8")
    (out / "final_execution_decision.json").write_text(json.dumps(final_doc), encoding="utf-8")
    (out / "ai_export_bundle.json").write_text(json.dumps(stale_bundle), encoding="utf-8")
    (out / "daily_report.md").write_text("# Daily Portfolio Execution Report\n", encoding="utf-8")
    (out / "daily_brief.json").write_text(json.dumps({"system_status": {}}), encoding="utf-8")

    pre = detect_target_guard_conflict(out)
    assert pre["conflict_detected"] is True

    synced_final, _, _, post = resync_guard_lock_after_bundle_write(
        data,
        out,
        health_doc=health_doc,
        acceptance_doc=dict(acceptance_doc),
        final_doc=dict(final_doc),
        green={},
        saa_report={},
        as_of="2026-07-10",
        run_id="test-run",
        target_hash="abc123",
    )
    assert post["conflict_detected"] is False
    assert synced_final["target_guard_conflict_detected"] is False
    bundle = json.loads((out / "ai_export_bundle.json").read_text(encoding="utf-8"))
    assert bundle.get("health_snapshot_id") == snap


def test_finalize_health_snapshot_aligns_guard(tmp_path: Path) -> None:
    """Guard detail shape is comparable across health and acceptance artifacts."""
    detail = {
        "severity": "PASS",
        "current_hash": "abc123",
        "changed_rows": 0,
        "system_proposal_leak_count": 0,
    }
    health_doc = {"checks": [{"name": "target_portfolio_guard", "detail": detail}]}
    acc_doc = {"items": [{"name": "target_portfolio_guard", "detail": detail}]}
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "system_health.json").write_text(json.dumps(health_doc), encoding="utf-8")
    (out / "acceptance_report.json").write_text(json.dumps(acc_doc), encoding="utf-8")
    (out / "final_execution_decision.json").write_text(
        json.dumps({"execution_permissions": {"gates": {"target_portfolio_guard": "PASS"}}}),
        encoding="utf-8",
    )
    conflict = detect_target_guard_conflict(out)
    assert conflict["conflict_detected"] is False
    assert conflict["health_severity"] == "PASS"
    assert conflict["acceptance_severity"] == "PASS"
