from __future__ import annotations

from pathlib import Path

from src.ui.action_center import collect_action_items

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"


def test_collect_action_items_pmi_when_gate_yellow():
    items = collect_action_items(DATA_DIR, OUTPUT_DIR)
    ids = {i.id for i in items}
    from src.data_refresh.kosis_tier2_manual import validate_pmi_kr_manual_ready
    from src.report.io_utils import read_output_json

    pmi = validate_pmi_kr_manual_ready(DATA_DIR)
    core = read_output_json(OUTPUT_DIR / "core_etf_permission_diagnostics.json") or {}
    reasons = core.get("restriction_reasons") or []
    if not pmi.get("ready") and "data_gate=YELLOW→core_etf_REVIEW_ONLY" in reasons:
        assert "pmi_kr_manual_confirm" in ids
        pmi_item = next(i for i in items if i.id == "pmi_kr_manual_confirm")
        assert pmi_item.nav_target == "PMI"
    else:
        assert "pmi_kr_manual_confirm" not in ids


def test_collect_action_items_no_false_target_when_no_draft():
    items = collect_action_items(DATA_DIR, OUTPUT_DIR)
    from src.alpha.target_draft_bridge import default_target_draft_path, is_target_draft_pending

    draft_path = default_target_draft_path()
    if not is_target_draft_pending(DATA_DIR, draft_path):
        assert all(i.id != "target_draft_pending" for i in items)


def test_collect_action_items_policy_cap_uses_output_json():
    items = collect_action_items(DATA_DIR, OUTPUT_DIR)
    from src.report.io_utils import read_output_json

    cap = (read_output_json(OUTPUT_DIR / "final_execution_decision.json") or {}).get("policy_cap") or {}
    days = cap.get("days_to_expiry")
    status = cap.get("expiry_status")
    policy_ids = {i.id for i in items if i.id.startswith("policy_cap_")}
    if status == "EXPIRED_REVIEW_REQUIRED":
        assert "policy_cap_expired" in policy_ids
    elif status == "ACTIVE" and days is not None and 0 <= int(days) <= 14:
        assert "policy_cap_expiring_soon" in policy_ids
    else:
        assert not policy_ids


def test_action_center_import():
    from src.ui import action_center

    assert callable(action_center.collect_action_items)
    assert callable(action_center.render_action_center)
