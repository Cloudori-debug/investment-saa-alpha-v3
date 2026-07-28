from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.target_draft_bridge import (
    enrich_target_changes_for_display,
    is_target_draft_pending,
    load_target_draft,
    merge_target_draft,
)
from src.models import TargetRow


def test_load_target_draft_filters_kr_alpha(tmp_path: Path):
    draft = tmp_path / "target_draft.csv"
    pd.DataFrame(
        [
            {"ticker": "005930", "name": "삼성전자", "asset_group": "kr_alpha", "target_weight": 3.0, "min_weight": 1, "max_weight": 5, "sector": "tech", "role": "value"},
            {"ticker": "069500", "name": "KODEX", "asset_group": "domestic_beta", "target_weight": 10.0, "min_weight": 0, "max_weight": 20, "sector": "", "role": ""},
            {"ticker": "000660", "name": "SK하이닉스", "asset_group": "kr_alpha", "target_weight": 0.0, "min_weight": 0, "max_weight": 0, "sector": "tech", "role": ""},
        ]
    ).to_csv(draft, index=False)
    df = load_target_draft(draft)
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "005930"


def test_merge_target_draft_replaces_kr_alpha_only():
    current = [
        TargetRow(ticker="005830", name="DB손해보험", asset_group="kr_alpha", sector="insurance", role="core", target_weight=10.0, min_weight=2, max_weight=20),
        TargetRow(ticker="069500", name="KODEX200", asset_group="domestic_beta", sector="", role="beta", target_weight=15.0, min_weight=10, max_weight=20),
    ]
    draft = pd.DataFrame(
        [
            {"ticker": "005930", "name": "삼성전자", "asset_group": "kr_alpha", "target_weight": 4.0, "min_weight": 2, "max_weight": 6, "sector": "tech", "role": "value"},
        ]
    )
    proposal = merge_target_draft(current, draft, kr_alpha_budget=31.0)
    tickers = {r.ticker: r for r in proposal.rows}
    assert "005830" not in tickers
    assert tickers["005930"].target_weight == 4.0
    assert tickers["069500"].target_weight == 15.0
    assert proposal.kr_alpha_sum == 4.0


def test_merge_target_draft_changes_use_draft_names_not_tickers():
    current = [
        TargetRow(ticker="005830", name="DB손해보험", asset_group="kr_alpha", sector="insurance", role="core", target_weight=4.82, min_weight=2, max_weight=20),
        TargetRow(ticker="192400", name="쿠쿠홀딩스", asset_group="kr_alpha", sector="consumer", role="value", target_weight=1.24, min_weight=0, max_weight=5),
    ]
    draft = pd.DataFrame(
        [
            {"ticker": "005830", "name": "DB손해보험", "asset_group": "kr_alpha", "target_weight": 5.0, "min_weight": 2, "max_weight": 20, "sector": "insurance", "role": "core"},
            {"ticker": "006040", "name": "동원산업", "asset_group": "kr_alpha", "target_weight": 1.24, "min_weight": 0, "max_weight": 5, "sector": "consumer", "role": "value"},
        ]
    )
    changes_df = pd.DataFrame(
        [
            {"ticker": "005830", "action": "trim", "old_weight": 4.82, "new_weight": 3.37, "reason": "grade_c_2w"},
            {"ticker": "192400", "action": "remove", "old_weight": 1.24, "new_weight": 0.0, "reason": "reject"},
            {"ticker": "006040", "action": "add", "old_weight": 0.0, "new_weight": 1.24, "reason": "replace"},
        ]
    )
    proposal = merge_target_draft(current, draft, changes_df=changes_df)
    by_ticker = {c.ticker: c for c in proposal.changes}
    assert by_ticker["005830"].name == "DB손해보험"
    assert by_ticker["192400"].name == "쿠쿠홀딩스"
    assert by_ticker["006040"].name == "동원산업"


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_is_target_draft_pending_when_kr_alpha_differs(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    draft_path = tmp_path / "target_draft.csv"
    (data_dir / "target_portfolio.csv").write_text(
        (FIXTURES / "target_portfolio_pending_base.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    draft_path.write_text(
        (FIXTURES / "target_draft_kr_alpha_differs.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert is_target_draft_pending(data_dir, draft_path)


def test_is_target_draft_pending_false_when_kr_alpha_matches(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    draft_path = tmp_path / "target_draft.csv"
    base = (FIXTURES / "target_portfolio_pending_base.csv").read_text(encoding="utf-8")
    (data_dir / "target_portfolio.csv").write_text(base, encoding="utf-8")
    # draft = current kr_alpha subset (005830, 021240) with same weights
    draft_path.write_text(
        "ticker,name,asset_group,sector,role,target_weight,min_weight,max_weight\n"
        "005830,DB손해보험,kr_alpha,insurance,shareholder_return,5.0,4.0,12.0\n"
        "021240,코웨이,kr_alpha,consumer,quality_defensive,5.0,4.0,12.0\n",
        encoding="utf-8",
    )
    assert not is_target_draft_pending(data_dir, draft_path)


def test_build_kr_alpha_target_comparison(tmp_path: Path):
    from src.alpha.target_draft_bridge import build_kr_alpha_target_comparison

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    draft_path = tmp_path / "target_draft.csv"
    (data_dir / "target_portfolio.csv").write_text(
        (FIXTURES / "target_portfolio_pending_base.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    draft_path.write_text(
        (FIXTURES / "target_draft_kr_alpha_differs.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    draft_df = load_target_draft(draft_path)
    cmp_df = build_kr_alpha_target_comparison(data_dir, draft_df, draft_path=draft_path)
    assert not cmp_df.empty
    assert "user_action" in cmp_df.columns
    assert "current_pct" in cmp_df.columns
    assert "draft_pct" in cmp_df.columns
    adds = cmp_df[cmp_df["user_action"].str.startswith("신규 편입", na=False)]
    assert not adds.empty
    assert "005930" in set(adds["ticker"])


def test_enrich_target_changes_adds_names():
    changes = pd.DataFrame([
        {"ticker": "000660", "action": "add", "old_weight": 0.0, "new_weight": 1.1,
         "reason": "replace 192400", "paired_with": "192400"},
    ])
    draft = pd.DataFrame([
        {"ticker": "000660", "name": "SK하이닉스", "target_weight": 1.1, "asset_group": "kr_alpha"},
    ])
    pairs = pd.DataFrame([
        {"exit_ticker": "192400", "exit_name": "쿠쿠홀딩스",
         "candidate_ticker": "000660", "candidate_name": "SK하이닉스", "rank": 1,
         "reason": "replace_in for 192400"},
    ])
    out = enrich_target_changes_for_display(changes, draft_df=draft, pairs_df=pairs)
    assert out.iloc[0]["name"] == "SK하이닉스"
    assert out.iloc[0]["paired_with_name"] == "쿠쿠홀딩스"


def test_is_target_draft_pending_false_without_file(tmp_path: Path):
    assert not is_target_draft_pending(tmp_path / "data", tmp_path / "missing.csv")
