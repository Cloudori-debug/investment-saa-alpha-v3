"""Screen book portfolio replaces purchase-weight holdings in UI."""

from __future__ import annotations

from alpha_system.loader import load_config
from alpha_system.ui.services.context import (
    ScoreboardRow,
    _build_screen_portfolio,
)


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


def test_screen_portfolio_takes_top_eligible_not_purchase_book(tmp_path) -> None:
    cfg = load_config()
    cfg = cfg.model_copy(
        update={
            "scoring": cfg.scoring.model_copy(update={"score_cutoff": 80.0}),
            "sizing": cfg.sizing.model_copy(update={"target_names": 3}),
        }
    )
    board = _board(
        ("000001", "A", 90.0, True),
        ("000002", "B", 88.0, True),
        ("000003", "C", 85.0, True),
        ("000004", "D", 84.0, True),
        ("000005", "E", 70.0, False),
    )
    rows = _build_screen_portfolio(
        cfg,
        board,
        prices_df=__import__("pandas").DataFrame(),
        fundamentals_df=__import__("pandas").DataFrame(),
        exit_targets_path=tmp_path / "missing.yaml",
        overlay_path=tmp_path / "qual_rank_overlay.json",
    )

    assert [row.ticker for row in rows] == ["000001", "000002", "000003"]
    assert all(row.avg_price is None for row in rows)
    assert all(row.extra.get("book") == "proposal" for row in rows)
    assert sum(row.weight_pct for row in rows) > 0
    # equal-weight equity sleeve (90% / 3) — not initial_weight_cap
    assert [round(row.weight_pct, 2) for row in rows] == [30.0, 30.0, 30.0]
    assert all(row.target_gap_kind == "screen_pending" for row in rows)


def test_screen_portfolio_applies_qual_gate(tmp_path) -> None:
    cfg = load_config()
    cfg = cfg.model_copy(
        update={
            "scoring": cfg.scoring.model_copy(update={"score_cutoff": 80.0}),
            "sizing": cfg.sizing.model_copy(update={"target_names": 3}),
        }
    )
    overlay = tmp_path / "qual_rank_overlay.json"
    overlay.write_text(
        '{"version":"1","max_swap_slots":2,"gates":[{"ticker":"000001",'
        '"reason":"downgrade","source_url":"https://example.test/r",'
        '"note":"","as_of":"2026-08-30","active":true}],"swaps":[]}\n',
        encoding="utf-8",
    )
    board = _board(
        ("000001", "A", 90.0, True),
        ("000002", "B", 88.0, True),
        ("000003", "C", 85.0, True),
        ("000004", "D", 84.0, True),
        ("000005", "E", 70.0, False),
    )
    rows = _build_screen_portfolio(
        cfg,
        board,
        prices_df=__import__("pandas").DataFrame(),
        fundamentals_df=__import__("pandas").DataFrame(),
        exit_targets_path=tmp_path / "missing.yaml",
        overlay_path=overlay,
    )
    assert [row.ticker for row in rows] == ["000002", "000003", "000004"]


def test_screen_portfolio_drops_name_above_justified_target(tmp_path) -> None:
    import pandas as pd
    import yaml

    cfg = load_config()
    cfg = cfg.model_copy(
        update={
            "scoring": cfg.scoring.model_copy(update={"score_cutoff": 80.0}),
            "sizing": cfg.sizing.model_copy(update={"target_names": 3}),
        }
    )
    exit_path = tmp_path / "kr_alpha_exit_targets.yaml"
    exit_path.write_text(
        yaml.safe_dump(
            {
                "tickers": {
                    "000001": {
                        "target_price": 10_000,
                        "valuation": {"pbr_max": 1.0},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    board = _board(
        ("000001", "A", 90.0, True),
        ("000002", "B", 88.0, True),
        ("000003", "C", 85.0, True),
        ("000004", "D", 84.0, True),
        ("000005", "E", 70.0, False),
    )
    prices = pd.DataFrame(
        [
            {"ticker": "000001", "close": 50_000},
            {"ticker": "000002", "close": 10_000},
            {"ticker": "000003", "close": 10_000},
            {"ticker": "000004", "close": 10_000},
        ]
    )
    funds = pd.DataFrame(
        [
            {"ticker": "000001", "pbr": 3.0, "roe": 12.0},
            {"ticker": "000002", "pbr": 0.5, "roe": 12.0},
            {"ticker": "000003", "pbr": 0.5, "roe": 12.0},
            {"ticker": "000004", "pbr": 0.5, "roe": 12.0},
        ]
    )
    rows = _build_screen_portfolio(
        cfg,
        board,
        prices_df=prices,
        fundamentals_df=funds,
        exit_targets_path=exit_path,
        overlay_path=tmp_path / "qual_rank_overlay.json",
    )
    assert [row.ticker for row in rows] == ["000002", "000003", "000004"]
    assert "000001" not in {row.ticker for row in rows}


def test_cutoff_passed_ineligible_keeps_high_score_quality_fails() -> None:
    from alpha_system.ui.services.context import cutoff_passed_ineligible

    board = _board(
        ("000001", "A", 90.0, True),
        ("000002", "B", 88.0, False),
        ("000003", "C", 70.0, False),
    )
    board[1].eligibility_reason = "품질 하한 미달: score_q=50.83 < 55"
    board[1].score_q = 50.83
    blocked = cutoff_passed_ineligible(board, cutoff=80.0)
    assert [row.ticker for row in blocked] == ["000002"]


def test_blocked_proposal_rows_show_reason_and_zero_weight(tmp_path) -> None:
    from alpha_system.ui.services.context import (
        _blocked_proposal_rows,
        cutoff_passed_ineligible,
    )
    from alpha_system.ui.services.ko_display import format_ineligibility_reason
    from alpha_system.ui.services.portfolio_widgets import _header_cue, _row_main_html

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
    cue, tone = _header_cue(row)
    assert "품질 하한" in cue
    assert tone == "danger"
    html = _row_main_html(row)
    assert "부적격" in html
    assert "KG스틸" in html
    assert "pf-chart-name" not in html
    assert "<strong>KG스틸</strong>" in html
    assert "finance.naver.com/item/fchart.naver?code=016380" in html
    assert ">차트</a>" in html
    assert format_ineligibility_reason(
        board[0].eligibility_reason, score_q=50.83, min_q=55
    ) == "품질 하한 미달 (Q 50.8 < 55)"
