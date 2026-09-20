"""Observation-pool pack for paste into another AI."""

from __future__ import annotations

import json
from datetime import date

from alpha_system.ui.services.candidate_ai_export import build_candidate_ai_export
from alpha_system.ui.services.context import ScoreboardRow
from alpha_system.ui.services.rank_watchboard import WatchTableRow


def _watch(
    rank: int,
    ticker: str,
    name: str,
    score: float,
    *,
    tone: str = "관찰",
    eligible: bool = True,
    sector: str = "test",
) -> WatchTableRow:
    return WatchTableRow(
        rank=rank,
        ticker=ticker,
        name=name,
        total_score=score,
        sector=sector,
        is_held=False,
        in_proposal=tone == "제안",
        eligibility=eligible,
        tone=tone,
        per=10.0,
        pbr=1.2,
        roe=15.0,
        current_price=10000.0,
        target_price=15000.0,
    )


def _score(ticker: str, name: str, total: float, reason: str = "") -> ScoreboardRow:
    return ScoreboardRow(
        ticker=ticker,
        name=name,
        total_score=total,
        score_q=60.0,
        score_v=50.0,
        score_sr=40.0,
        score_r=20.0,
        cecs=None,
        eligibility=True,
        sector_peer_fallback=False,
        is_held=False,
        status="ok",
        sector="test",
        eligibility_reason=reason,
    )


def test_candidate_ai_export_markdown_and_json_are_pasteable() -> None:
    pack = build_candidate_ai_export(
        market="KOSPI",
        as_of=date(2026, 9, 6),
        cutoff=50.735,
        quality_min=55.0,
        target_n=6,
        table_rows=[
            _watch(1, "100840", "SNT에너지", 67.09, tone="제안", sector="industrials"),
            _watch(2, "006040", "동원산업", 55.96),
        ],
        scoreboard_rows=[
            _score("100840", "SNT에너지", 67.09),
            _score("006040", "동원산업", 55.96, "ok"),
        ],
    )
    assert pack.n_watch == 2
    assert pack.file_stem == "alpha_candidates_KOSPI_20260906"
    assert "SNT에너지" in pack.markdown
    assert "006040" in pack.markdown
    assert "target_portfolio.csv" in pack.markdown
    assert "50.735" in pack.markdown
    assert "```tsv" in pack.markdown
    payload = json.loads(pack.json_text)
    assert payload["market"] == "KOSPI"
    assert payload["watch"][0]["ticker"] == "100840"
    assert payload["watch"][0]["score_q"] == 60.0
    assert "finance.naver.com" in payload["watch"][0]["chart"]
    assert payload["momentum_in_total"] is False
    assert payload["hakedaka_in_total"] is False
    assert payload["watch"][0]["cyclical_theme"] is True


def test_candidate_ai_export_kosdaq_stem_and_watch_max() -> None:
    pack = build_candidate_ai_export(
        market="KOSDAQ",
        as_of="2026-09-06",
        cutoff=57.09,
        quality_min=55.0,
        target_n=3,
        table_rows=[_watch(1, "035900", "JYP Ent.", 70.0, tone="제안")],
        scoreboard_rows=[_score("035900", "JYP Ent.", 70.0)],
    )
    assert pack.file_stem.startswith("alpha_candidates_KOSDAQ_")
    assert "코스닥" in pack.markdown
    assert "관찰 풀 10종" in pack.markdown
    assert json.loads(pack.json_text)["watch_max"] == 10
