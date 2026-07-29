"""Basel theme timeline board — soft dates + Ph4 anchor."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_system.ui.services.basel_theme_board import (
    build_basel_auto_cues,
    build_basel_theme_board,
    load_ph4_anchor,
    save_ph4_anchor,
    _add_months,
)


def test_add_months() -> None:
    assert _add_months(date(2028, 1, 1), -6) == date(2027, 7, 1)
    assert _add_months(date(2027, 7, 1), 12) == date(2028, 7, 1)


def test_board_loads_yaml(tmp_path: Path) -> None:
    root = tmp_path
    data = root / "data"
    data.mkdir()
    (data / "basel_theme_phases.yaml").write_text(
        """
updated: "2026-07-29"
early_entry: { months_before_t0: 6 }
themes: { BX_FLOOR_FINAL: { primary: [banks] } }
phases:
  - id: Ph6
    stage: S4b
    t0: "2028-01-01"
    error_months: 6
    theme: BX_FLOOR_FINAL
    status: target
    early_entry_from: "2027-07-01"
""",
        encoding="utf-8",
    )
    board = build_basel_theme_board(root, as_of=date(2027, 8, 1))
    assert len(board.rows) == 1
    r = board.rows[0]
    assert r.id == "Ph6"
    assert r.window == "선진입·관찰 열림"
    assert "BX_FLOOR" in r.theme or "최종" in r.theme_ko


def test_ph4_anchor_gate(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data" / "local").mkdir(parents=True)
    save_ph4_anchor(
        root,
        checks={"fss_fsc_notice": True, "no_media_only": False},
        t0=date(2026, 7, 1),
        k_pct=65.0,
        evidence_note="x",
    )
    st = load_ph4_anchor(root)
    assert st.anchored is False
    save_ph4_anchor(
        root,
        checks={
            "fss_fsc_notice": True,
            "supervisory_rule": False,
            "bank_disclosure_k": False,
            "bis_footnote": False,
            "no_media_only": True,
            "s5_overlay_note": False,
        },
        t0=date(2026, 7, 1),
        k_pct=65.0,
        evidence_note="FSC notice",
    )
    st2 = load_ph4_anchor(root)
    assert st2.anchored is True


def test_ph4_opens_early_window(tmp_path: Path) -> None:
    root = tmp_path
    data = root / "data"
    data.mkdir()
    (data / "basel_theme_phases.yaml").write_text(
        """
early_entry: { months_before_t0: 6 }
themes: { BX_FLOOR_UP: {} }
phases:
  - id: Ph4
    stage: S4a
    t0: null
    error_months: 12
    theme: BX_FLOOR_UP
    status: active_soft
  - id: Ph5
    stage: S4a
    t0_offset_months_from: Ph4
    t0_offset_months: 12
    error_months: 12
    theme: BX_FLOOR_UP
    status: pending_ph4_anchor
""",
        encoding="utf-8",
    )
    save_ph4_anchor(
        root,
        checks={
            "fss_fsc_notice": True,
            "no_media_only": True,
            "supervisory_rule": False,
            "bank_disclosure_k": False,
            "bis_footnote": False,
            "s5_overlay_note": False,
        },
        t0=date(2026, 12, 1),
        k_pct=65.0,
        evidence_note="test",
    )
    board = build_basel_theme_board(root, as_of=date(2026, 7, 1))
    by_id = {r.id: r for r in board.rows}
    assert by_id["Ph4"].t0 == date(2026, 12, 1)
    assert by_id["Ph4"].early_from == date(2026, 6, 1)
    assert by_id["Ph4"].window == "선진입·관찰 열림"
    assert by_id["Ph5"].t0 == date(2027, 12, 1)


def test_basel_auto_cues_ph4_and_log(tmp_path: Path) -> None:
    root = tmp_path
    data = root / "data"
    data.mkdir()
    (data / "basel_theme_phases.yaml").write_text(
        """
early_entry: { months_before_t0: 6 }
themes: { BX_FLOOR_UP: {}, BX_FLOOR_FINAL: {} }
phases:
  - id: Ph4
    stage: S4a
    t0: null
    error_months: 12
    theme: BX_FLOOR_UP
    status: active_soft
  - id: Ph6
    stage: S4b
    t0: "2028-01-01"
    error_months: 6
    theme: BX_FLOOR_FINAL
    status: target
    early_entry_from: "2027-07-01"
""",
        encoding="utf-8",
    )
    _, cues = build_basel_auto_cues(root, as_of=date(2026, 7, 29), persist_log=True)
    keys = {c.key for c in cues}
    assert "basel_ph4_anchor" in keys
    log = root / "data" / "local" / "basel_theme_timeline_log.jsonl"
    assert log.exists()
