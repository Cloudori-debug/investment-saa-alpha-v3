"""Economy forest defense checklist — Review-only."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.economy_forest_checklist import stage_forest_checklist


def test_stage_forest_none() -> None:
    book = stage_forest_checklist(None)
    assert book.tone == "off"
    blob = " ".join(f"{c.label} {c.body}" for c in book.cards)
    assert "채권" in blob or "전체" in blob


def test_stage_forest_easy() -> None:
    book = stage_forest_checklist(1)
    assert book.tone == "ok"
    blob = " ".join(f"{c.label} {c.body}" for c in book.cards)
    assert "대기" in blob or "노른자" in blob or "편입하지 않음" in blob


def test_stage_forest_neutral() -> None:
    book = stage_forest_checklist(3)
    assert book.tone == "wait"
    assert len(book.cards) >= 4
    assert all(c.label and c.body for c in book.cards)
    blob = " ".join(book.bullets)
    assert "현금" in blob or "예금" in blob
    assert "금" in blob


def test_stage_forest_defensive() -> None:
    assert stage_forest_checklist(4).tone == "bad"
    assert stage_forest_checklist(5).tone == "bad"
    blob = " ".join(stage_forest_checklist(5).bullets)
    assert "추격" in blob or "유동성" in blob


def test_economy_page_wires_forest() -> None:
    page = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("alpha_system", "ui", "pages", "economy.py")
        .read_text(encoding="utf-8")
    )
    # 나침반 탭은 playbook·숲(SAA) 참고로 통합 · 구 _render_forest_checklist 제거
    assert "stage_playbook" in page
    assert "숲" in page or "sec_forest" in page or "forest" in page.lower()
