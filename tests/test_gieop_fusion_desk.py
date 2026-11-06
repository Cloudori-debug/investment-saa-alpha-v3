"""기업해부 융합 데스크 — 정량 커버 + 초안 상태."""

from __future__ import annotations

import json
from pathlib import Path

from alpha_system.ui.services.gieop_alpha_seed import (
    SRC_SOFT,
    SRC_VALUE,
    AlphaGieopCandidate,
)
from alpha_system.ui.services.gieop_fusion_desk import (
    build_fusion_desk,
    build_quant_cover,
    fusion_status_html,
    refresh_quant_on_drafts,
    scan_draft_progress,
)


def test_scan_draft_idle_and_done(tmp_path: Path) -> None:
    d = tmp_path / "내조사"
    d.mkdir()
    (d / "a_111111.json").write_text(
        json.dumps(
            {
                "meta": {"ticker": "111111", "company": "A"},
                "tasks": [
                    {"id": "P01", "status": "NOT_STARTED"},
                    {"id": "P02", "status": "NOT_STARTED"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (d / "b_222222.json").write_text(
        json.dumps(
            {
                "meta": {"ticker": "222222", "company": "B"},
                "tasks": [
                    {"id": "P01", "status": "DONE"},
                    {"id": "P02", "status": "COMPLETED"},
                ],
            }
        ),
        encoding="utf-8",
    )
    prog = scan_draft_progress(d)
    assert prog["111111"].status_ko == "미착수"
    assert prog["222222"].status_ko == "완료"


def test_quant_cover_discriminates() -> None:
    class _V:
        per = 10.0
        pbr = 0.8
        roe = 12.0
        pass_absolute = True
        pass_sector_rel = False
        pass_quality = True
        crash_flag = False
        market_cap = 800_000_000_000.0
        evidence_ok = False

    hi = build_quant_cover(in_soft=True, pass_value=True, value_row=_V())
    lo = build_quant_cover(in_soft=False, pass_value=False, value_row=None)
    assert hi.n_ok >= 6
    assert lo.n_ok <= 2
    assert hi.label != lo.label


def test_fusion_status_shows_quant(tmp_path: Path, monkeypatch) -> None:
    from alpha_system.ui.services import gieop_fusion_desk as mod

    drafts = tmp_path / "내조사"
    drafts.mkdir()
    (drafts / "x_111111.json").write_text(
        json.dumps(
            {
                "meta": {"ticker": "111111", "company": "A"},
                "tasks": [{"id": "P01", "status": "NOT_STARTED"}] * 50,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mod,
        "resolve_gieop_paths",
        lambda root: type(
            "P",
            (),
            {
                "drafts_dir": drafts,
                "start_html": tmp_path / "x.html",
                "root": tmp_path,
                "start_ok": False,
                "drafts_ok": True,
            },
        )(),
    )
    monkeypatch.setattr(mod, "_load_value_by", lambda root, market: ({}, ""))
    board = build_fusion_desk(
        tmp_path,
        market="KOSPI",
        candidates=[
            AlphaGieopCandidate(
                "111111", "A", "", SRC_SOFT, "", True, False, True
            ),
            AlphaGieopCandidate(
                "222222", "B", "", SRC_VALUE, "", False, False, True
            ),
        ],
    )
    assert board.n_draft_idle >= 1
    html = fusion_status_html(board)
    assert "정량" in html
    assert "해부과제" in html
    assert "미니" not in html
    assert "111111" in html


def test_refresh_quant_writes_alpha_quant(tmp_path: Path, monkeypatch) -> None:
    from alpha_system.ui.services import gieop_fusion_desk as mod

    drafts = tmp_path / "내조사"
    drafts.mkdir()
    path = drafts / "알파_111111.json"
    path.write_text(
        json.dumps(
            {
                "meta": {"ticker": "111111", "company": "A"},
                "tasks": [{"id": "P01", "status": "NOT_STARTED"}],
                "notes": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mod,
        "resolve_gieop_paths",
        lambda root: type(
            "P",
            (),
            {
                "drafts_dir": drafts,
                "start_html": tmp_path / "x.html",
                "root": tmp_path,
                "start_ok": False,
                "drafts_ok": True,
            },
        )(),
    )
    monkeypatch.setattr(mod, "_load_value_by", lambda root, market: ({}, ""))
    cands = [
        AlphaGieopCandidate(
            "111111", "A", "", SRC_SOFT, "", True, False, True
        )
    ]
    res = refresh_quant_on_drafts(tmp_path, market="KOSPI", candidates=cands)
    assert "111111" in res["updated"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "alpha_quant" in raw
    assert raw["tasks"][0]["status"] == "NOT_STARTED"
    assert raw["alpha_quant"]["human_tasks_untouched"] is True
