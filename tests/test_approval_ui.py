"""Confirmation (approval) tabs — copy, retired T3 surface, readable boards."""

from __future__ import annotations

import inspect

from alpha_system.ui.pages import events, scores
from alpha_system.ui.services import action_panels
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


def test_approval_copy_tabs_and_lead() -> None:
    load_ui_copy.cache_clear()
    assert "숫자" in copy_get("approval", "lead")
    assert copy_get("approval", "tab_quant") == "① 숫자"
    assert copy_get("approval", "tab_weekly") == "② 이번 주"
    assert copy_get("approval", "tab_live") == "③ 가동"
    assert copy_get("approval", "tab_monthly") == ""
    assert "이번 달" not in copy_get("approval", "lead")
    assert "정량 전체 갱신" in copy_get("approval", "quant_empty")
    assert "마지막 갱신" in copy_get("approval", "quant_refresh_as_of")
    src = inspect.getsource(events._render_data_refresh)
    assert "quant_refresh_when" in src
    assert "quant_refresh_as_of" in src


def test_t3_pbr_surface_removed_from_events() -> None:
    src = inspect.getsource(events)
    assert "_render_t3_detail" not in src
    assert "T3 이력 CSV" not in src
    assert "T3 PBR" not in src
    assert "ap_freshness_table" in src


def test_scores_empty_and_held_copy_are_current() -> None:
    src = inspect.getsource(scores.render_scores)
    assert "cecs_manual_scoring_template.csv" not in src
    assert "exit 연동" not in src
    assert "quant_empty" in src
    assert "quant_below_held" in src


def test_thesis_note_does_not_mention_tranches() -> None:
    load_ui_copy.cache_clear()
    note = copy_get("approval", "thesis_freeze_note")
    assert "트랜치" not in note
    assert "신규 편입" in note
    assert "자동매매" in note


def test_rules_yaml_dump_removed_from_live_tab() -> None:
    from alpha_system.ui.pages import approval

    src = inspect.getsource(approval)
    assert "render_rules" not in src
    assert "classify_config" not in src
    events_src = inspect.getsource(events._render_go_live)
    assert "chip_cecs_note" not in events_src
    assert "체크리스트" not in events_src
    load_ui_copy.cache_clear()
    assert copy_get("approval", "live_yaml_title") == ""


def test_weekly_monthly_live_dead_copy_removed() -> None:
    src = inspect.getsource(events)
    assert "사용 순서" not in src
    assert "프롬프트 미리보기" not in src
    assert "pending_n" not in src
    assert '<div class="ap-tab-label">진행</div>' not in src
    from alpha_system.ui.pages import approval

    appr = inspect.getsource(approval)
    assert "live_rules_expand" not in appr
    load_ui_copy.cache_clear()
    assert copy_get("approval", "chip_cutoff_ok") == "합격선 확정"
    assert "ai_suggested" not in copy_get("approval", "status_wait")
    src = inspect.getsource(action_panels)
    assert "FOCUS_T3_DETAIL" not in src
    assert "FOCUS_DATA_REFRESH" in src


def test_weekly_qual_reads_t2_ids_from_qual_gates_not_retired_tranches() -> None:
    """Capital T1–T4 are empty; weekly C uses qual_gates.t2_event_ids."""
    src = inspect.getsource(events._render_weekly_qual)
    assert 'tranches["T2"]' not in src
    assert "t2_event_ids()" in src
    from alpha_system.loader import load_config

    cfg = load_config()
    assert cfg.tranches == {}
    ids = cfg.t2_event_ids()
    assert "commercial_code_enforcement_decrees" in ids
    assert "msci_dm_index_inclusion_confirmed" in ids


def test_monthly_tab_removed() -> None:
    from alpha_system.ui.pages import approval

    src = inspect.getsource(events)
    assert "_render_monthly_cecs" not in src
    assert "btn_monthly_cecs_gen" not in src
    assert "monthly_go_proposal" not in src
    appr = inspect.getsource(approval)
    assert "_panel_monthly" not in appr
    assert "tab_monthly" not in appr
    assert "PAGE_PORTFOLIO" in appr
    assert "FOCUS_MONTHLY_CECS" in appr
    load_ui_copy.cache_clear()
    assert copy_get("approval", "tab_live") == "③ 가동"
    assert copy_get("approval", "live_kicker") == "3 · 가동"


def test_weekly_claude_request_ui_removed() -> None:
    src = inspect.getsource(events)
    assert "write_weekly_qual_report" not in src
    assert "btn_weekly_qual_gen" not in src
    assert "persist_targets_supplement" not in src
    assert "waiting_target_subjects" not in src
    assert "_WQ_TABS" not in src
    assert "write_targets_supplement_report" not in src
    assert "persist_killswitch_draft" not in src
    assert "btn_weekly_killswitch_save" not in src
    assert "weekly_watch_fill" not in src
    assert "_render_killswitch_watch" in src
    assert "refresh_killswitch_watch" in src
    load_ui_copy.cache_clear()
    assert copy_get("approval", "weekly_watch_title") == "공식 출처 탐색"
    assert "RSS" in copy_get("approval", "weekly_desc")
    assert copy_get("approval", "weekly_step_targets") == ""
    assert copy_get("approval", "weekly_targets_desc") == ""
    assert copy_get("approval", "prompt_b_caption") == ""
    assert copy_get("approval", "prompt_a_caption") == ""
    from alpha_system.ui.services import v2_chrome

    chrome = inspect.getsource(v2_chrome)
    assert "render_ops_strip" not in chrome
    assert "_count_waiting_targets" not in chrome


def test_ops_freshness_table_excludes_retired_sources() -> None:
    from pathlib import Path

    from alpha_system.ui.services.data_freshness import load_dashboard_config

    cfg = load_dashboard_config(
        Path(__file__).resolve().parents[1]
        / "alpha_system"
        / "config"
        / "dashboard.yaml"
    )
    keys = set((cfg.get("data_sources") or {}).keys())
    assert keys == {
        "fundamentals",
        "sector_mapping",
        "prices",
        "t2_events",
        "alpha_scores",
        "qual_rank_overlay",
    }
