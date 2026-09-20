"""Cutoff-pass names blocked by the quality floor still appear as 부적격."""

from __future__ import annotations

from alpha_system.loader import load_config
from alpha_system.ui.services.context import (
    ScoreboardRow,
    _blocked_proposal_rows,
    cutoff_passed_ineligible,
    proposal_band_scores,
)
from alpha_system.ui.services.ko_display import format_ineligibility_reason


def _board(*rows: tuple[str, str, float, bool]) -> list[ScoreboardRow]:
    out: list[ScoreboardRow] = []
    for ticker, name, score, eligible in rows:
        out.append(
            ScoreboardRow(
                ticker=ticker,
                name=name,
                total_score=score,
                score_q=score,
                score_v=score,
                score_sr=score,
                score_r=score,
                cecs=score,
                eligibility=eligible,
                sector_peer_fallback=False,
                is_held=False,
                status="final",
            )
        )
    return out


def test_proposal_band_keeps_top_n_even_if_ineligible() -> None:
    board = _board(
        ("000001", "A", 90.0, True),
        ("000002", "B", 88.0, False),
        ("000003", "C", 70.0, False),
        ("000004", "D", 60.0, False),
    )
    board[1].eligibility_reason = "품질 하한 미달: score_q=50.83 < 55"
    band = proposal_band_scores(board, target_n=3)
    assert [row.ticker for row in band] == ["000001", "000002", "000003"]


def test_cutoff_passed_ineligible_keeps_high_score_quality_fails() -> None:
    board = _board(
        ("000001", "A", 90.0, True),
        ("000002", "B", 88.0, False),
        ("000003", "C", 70.0, False),
    )
    board[1].eligibility_reason = "품질 하한 미달: score_q=50.83 < 55"
    board[1].score_q = 50.83
    blocked = cutoff_passed_ineligible(board, cutoff=80.0)
    assert [row.ticker for row in blocked] == ["000002"]


def test_proposal_band_includes_below_cutoff_ineligible(tmp_path) -> None:
    board = _board(
        ("138930", "BNK금융지주", 63.0, False),
        ("016380", "KG스틸", 61.0, False),
        ("000001", "하위", 40.0, False),
    )
    board[0].eligibility_reason = "ineligible: total_score=63.0 < cutoff=66.921"
    board[0].score_q = 50.83
    band = proposal_band_scores(board, target_n=2)
    assert [row.ticker for row in band] == ["138930", "016380"]
    rows = _blocked_proposal_rows(
        band,
        cfg=load_config(),
        prices_df=__import__("pandas").DataFrame(),
        fundamentals_df=__import__("pandas").DataFrame(),
        root=tmp_path,
    )
    assert [row.ticker for row in rows] == ["138930", "016380"]
    assert all(row.weight_pct == 0.0 for row in rows)
    assert all(row.extra.get("proposal_eligible") is False for row in rows)


def test_blocked_proposal_rows_carry_reason_and_zero_weight(tmp_path) -> None:
    cfg = load_config()
    cfg = cfg.model_copy(
        update={
            "scoring": cfg.scoring.model_copy(
                update={"score_cutoff": 80.0, "quality_min_score": 55}
            )
        }
    )
    board = _board(("016380", "KG스틸", 88.0, False))
    board[0].eligibility_reason = "품질 하한 미달: score_q=50.83 < 55"
    board[0].score_q = 50.83
    blocked = cutoff_passed_ineligible(board, cutoff=80.0)
    rows = _blocked_proposal_rows(
        blocked,
        cfg=cfg,
        prices_df=__import__("pandas").DataFrame(),
        fundamentals_df=__import__("pandas").DataFrame(),
        root=tmp_path,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.ticker == "016380"
    assert row.weight_pct == 0.0
    assert row.extra.get("proposal_eligible") is False
    assert "품질 하한" in str(row.extra.get("ineligible_reason"))
    assert format_ineligibility_reason(
        board[0].eligibility_reason, score_q=50.83, min_q=55
    ) == "품질 하한 미달 (Q 50.8 < 55)"


def test_blocked_proposal_rows_above_target_reason(tmp_path) -> None:
    cfg = load_config()
    board = _board(("000001", "목표가도달", 90.0, True))
    rows = _blocked_proposal_rows(
        board,
        cfg=cfg,
        prices_df=__import__("pandas").DataFrame(),
        fundamentals_df=__import__("pandas").DataFrame(),
        root=tmp_path,
        above_target={"000001"},
    )
    assert len(rows) == 1
    assert rows[0].extra.get("proposal_eligible") is False
    assert rows[0].extra.get("ineligible_reason") == "현재가 ≥ 혼합 목표가"
