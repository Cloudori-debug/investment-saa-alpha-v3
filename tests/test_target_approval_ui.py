"""P1: Streamlit target approval UI — dashboard Step ⑥ + 알파 탭."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_target_apply_lives_in_shared_module() -> None:
    src = _read("src/ui/target_approval_actions.py")
    assert "apply_proposed_target" in src
    assert "승인 반영" in src
    assert "전체 분석 자동 실행" in src
    assert 'writer_module="ui.target_approval_actions"' in src
    assert "disabled=not bool(approver)" in src
    assert 'approver or "human"' not in src
    assert "write_material_change_count" in src


def test_post_target_approval_analysis_helper() -> None:
    src = _read("src/ui/pipeline_actions.py")
    assert "def run_post_target_approval_analysis" in src
    assert "refresh_market=False" in src
    assert "RunMode.STANDARD" in src


def test_dashboard_target_apply_button_exists() -> None:
    src = _read("src/ui/target_draft_workflow.py")
    assert "render_target_approval_actions" in src
    assert "승인 반영" in src
    assert "비교 전용" not in src


def test_alpha_target_approval_uses_shared_module() -> None:
    src = _read("src/ui/alpha_panel.py")
    assert "render_target_approval_actions" in src
    assert "apply_proposed_target" not in src


def test_streamlit_target_apply_single_implementation() -> None:
    ui_dir = ROOT / "src" / "ui"
    apply_sites = sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in ui_dir.rglob("*.py")
        if "apply_proposed_target(" in p.read_text(encoding="utf-8")
    )
    assert apply_sites == ["src/ui/target_approval_actions.py"]


def test_dashboard_step6_inline_approval_wording() -> None:
    src = _read("src/ui/target_draft_workflow.py")
    assert "이 화면에서 바로 승인 반영" in src


def test_apply_target_draft_cli_uses_bridge() -> None:
    src = _read("scripts/apply_target_draft.py")
    assert "apply_proposed_target" in src
    assert "고급/관리자" in src or "관리자" in src
    assert 'writer_module="scripts.apply_target_draft"' in src


def test_apply_proposed_target_still_uses_write_audit() -> None:
    src = _read("src/alpha/target_bridge.py")
    assert "write_operational_target" in src
    assert "def apply_proposed_target" in src
