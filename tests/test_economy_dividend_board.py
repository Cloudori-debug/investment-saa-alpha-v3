"""Economy page dividend sleeve — Review-only, no rank/target writes."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.economy_dividend_board import (
    dividend_sleeve_hint,
    load_dividend_candidates,
)


def test_sleeve_hint_by_stage() -> None:
    assert dividend_sleeve_hint(1).tone == "favor"
    assert dividend_sleeve_hint(3).tone == "neutral"
    assert dividend_sleeve_hint(5).tone == "caution"
    assert dividend_sleeve_hint(None).tone == "neutral"


def test_load_dividend_candidates_sorted(tmp_path: Path) -> None:
    alpha = tmp_path / "alpha_portfolio" / "data" / "output"
    alpha.mkdir(parents=True)
    (tmp_path / "data").mkdir(parents=True)
    # KOSPI alpha path uses alpha_portfolio under repo via alpha_data_dir —
    # for unit test, write where alpha_data_dir(KOSPI) points relative to tmp...
    # alpha_data_dir(root, KOSPI) = root / "alpha_portfolio" / "data"
    (alpha / "alpha_scores.csv").write_text(
        "ticker,name,sector,gate_pass,score_sr,composite_score\n"
        "000001,A,sec,true,90,80\n"
        "000002,B,sec,true,70,75\n"
        "000003,C,sec,false,99,99\n"
        "000004,D,sec,true,40,50\n",
        encoding="utf-8",
    )
    univ = tmp_path / "alpha_portfolio" / "data" / "input"
    univ.mkdir(parents=True)
    (univ / "screening_universe.csv").write_text(
        "ticker,dividend_yield\n000001,3.5\n000002,2.1\n",
        encoding="utf-8",
    )
    rows = load_dividend_candidates(tmp_path, market="KOSPI", limit=5, min_score_sr=55)
    # gate_pass preferred → 000003 excluded; 000004 below min_sr
    assert [r.ticker for r in rows] == ["000001", "000002"]
    assert rows[0].dividend_yield == 3.5
    assert rows[0].score_sr == 90.0
