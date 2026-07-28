from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.alpha.approval_checklist import build_approval_checklist, checklist_blocking
from src.alpha.target_bridge import (
    apply_proposed_target,
    compute_full_diff,
    default_add_candidates,
    default_remove_candidates,
    default_trim_candidates,
    kr_alpha_target_sum,
    load_kr_alpha_budget,
    propose_target_changes,
    write_proposal_outputs,
)
from src.data_loader import load_target_portfolio


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"


def test_propose_trim_and_add(tmp_path):
    from src.models import TargetRow

    current = [
        TargetRow(ticker="005830", name="DB손해보험", asset_group="kr_alpha", sector="insurance", role="core", target_weight=10.0, min_weight=2.0, max_weight=20),
        TargetRow(ticker="006040", name="동원산업", asset_group="kr_alpha", sector="consumer", role="value", target_weight=8.0, min_weight=2.0, max_weight=15),
    ]
    candidates = [
        {"ticker": "035420", "name": "NAVER", "sector": "tech", "grade": "A", "eligible_action": "BUY_CANDIDATE"},
    ]
    proposal = propose_target_changes(
        current,
        add_candidates=candidates,
        trim_tickers={"006040"},
        remove_tickers=set(),
        kr_alpha_budget=30.0,
    )
    tickers = {r.ticker for r in proposal.rows}
    assert "035420" in tickers
    row_6040 = next(r for r in proposal.rows if r.ticker == "006040")
    orig = next(r for r in current if r.ticker == "006040")
    assert row_6040.target_weight <= orig.target_weight
    assert proposal.kr_alpha_sum <= 30.01


def test_propose_remove(tmp_path):
    from src.models import TargetRow

    current = [
        TargetRow(ticker="005830", name="DB손해보험", asset_group="kr_alpha", sector="insurance", role="core", target_weight=10.0, min_weight=0, max_weight=20),
        TargetRow(ticker="036530", name="SNT홀딩스", asset_group="kr_alpha", sector="holding", role="value", target_weight=5.0, min_weight=0, max_weight=10),
    ]
    proposal = propose_target_changes(
        current,
        add_candidates=[],
        trim_tickers=set(),
        remove_tickers={"036530"},
        kr_alpha_budget=None,
    )
    assert "036530" not in {r.ticker for r in proposal.rows}


def test_write_and_apply_with_backup(tmp_path):
    from src.models import TargetRow

    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    current = [
        TargetRow(ticker="005830", name="DB손해보험", asset_group="kr_alpha", sector="insurance", role="core", target_weight=90.0, min_weight=0, max_weight=20),
        TargetRow(ticker="453340", name="현대그린푸드", asset_group="kr_alpha", sector="consumer", role="value", target_weight=10.0, min_weight=1.0, max_weight=12),
    ]
    proposal = propose_target_changes(
        current,
        add_candidates=[],
        trim_tickers={"453340"},
        remove_tickers=set(),
        kr_alpha_budget=None,
    )
    target = data / "target_portfolio.csv"
    pd.DataFrame([t.model_dump() for t in current]).to_csv(target, index=False)
    backup_dir = data / "backups"
    apply_proposed_target(
        proposal, target, backup_dir=backup_dir, approved_by="test", data_dir=data, output_dir=out,
    )
    assert list(backup_dir.glob("target_portfolio.*.bak.csv"))
    updated = load_target_portfolio(target)
    new_453 = next(r for r in updated if r.ticker == "453340")
    assert new_453.target_weight <= next(r for r in current if r.ticker == "453340").target_weight


def test_approval_checklist_pass_warn():
    ctx = {
        "data_gate": "GREEN",
        "data_limitations": [],
        "action_constraints": ["사람 승인 후 실행"],
        "excluded_summary": {"preferred_stock": 1},
    }
    items = build_approval_checklist(
        ctx,
        candidate_count=25,
        kr_alpha_target_sum=29.5,
        kr_alpha_budget=30.0,
        replace_count=1,
        trim_count=0,
    )
    assert not checklist_blocking(items)
    assert any(i.id == "data_gate" and i.status == "pass" for i in items)


def test_approval_checklist_fail_on_red_gate():
    ctx = {"data_gate": "RED", "data_limitations": ["no data"], "excluded_summary": {}}
    items = build_approval_checklist(
        ctx,
        candidate_count=0,
        kr_alpha_target_sum=0,
        kr_alpha_budget=None,
        replace_count=5,
        trim_count=0,
    )
    assert checklist_blocking(items)


def test_default_selections():
    holdings = [
        {"ticker": "005830", "review_action": "KEEP"},
        {"ticker": "006040", "review_action": "TRIM"},
        {"ticker": "036530", "review_action": "REPLACE_CANDIDATE"},
    ]
    assert "006040" in default_trim_candidates(holdings)
    assert "036530" in default_remove_candidates(holdings)
    adds = default_add_candidates(
        [{"ticker": "A", "grade": "A", "eligible_action": "BUY_CANDIDATE"}],
        limit=1,
    )
    assert len(adds) == 1


def test_resolve_add_candidate_name_from_universe(tmp_path):
    from src.alpha.target_bridge import resolve_add_candidate

    uni = tmp_path / "universe.csv"
    uni.write_text(
        "ticker,name,market,security_type,sector\n008500,일정실업,KOSPI,common_stock,industrial\n",
        encoding="utf-8-sig",
    )
    row = resolve_add_candidate("8500", data_dir=tmp_path, pools=[{"ticker": "8500"}])
    assert row["ticker"] == "008500"
    assert row["name"] == "일정실업"


def test_propose_add_uses_resolved_name(tmp_path):
    from src.alpha.target_bridge import propose_target_changes, resolve_add_candidate
    from src.models import TargetRow

    uni = tmp_path / "universe.csv"
    uni.write_text(
        "ticker,name,market,security_type,sector\n008500,일정실업,KOSPI,common_stock,industrial\n",
        encoding="utf-8-sig",
    )
    current = [
        TargetRow(
            ticker="005830", name="DB손해보험", asset_group="kr_alpha", sector="insurance",
            role="core", target_weight=10.0, min_weight=2.0, max_weight=20.0,
        ),
    ]
    add = resolve_add_candidate("008500", data_dir=tmp_path, pools=[{"ticker": "008500"}])
    proposal = propose_target_changes(
        current,
        add_candidates=[add],
        trim_tickers=set(),
        remove_tickers=set(),
        data_dir=tmp_path,
    )
    added = next(c for c in proposal.changes if c.change_type == "add")
    assert added.name == "일정실업"


def test_compute_full_diff():
    current = load_target_portfolio(DATA_DIR / "target_portfolio.csv")
    proposal = propose_target_changes(
        current,
        add_candidates=[{"ticker": "035420", "name": "NAVER", "sector": "tech"}],
        trim_tickers=set(),
        remove_tickers=set(),
        kr_alpha_budget=None,
    )
    diffs = compute_full_diff(current, proposal.rows)
    assert any(d.change_type == "add" for d in diffs)


def test_propose_budget_scale_updates_minmax():
    from src.models import TargetRow

    current = [
        TargetRow(
            ticker="030200", name="KT", asset_group="kr_alpha", sector="telecom",
            role="quality_dividend", target_weight=7.0, min_weight=5.36, max_weight=16.05,
        ),
        TargetRow(
            ticker="021240", name="코웨이", asset_group="kr_alpha", sector="consumer",
            role="quality_defensive", target_weight=7.0, min_weight=5.36, max_weight=16.05,
        ),
    ]
    proposal = propose_target_changes(
        current,
        add_candidates=[],
        trim_tickers=set(),
        remove_tickers=set(),
        kr_alpha_budget=8.0,
    )
    assert proposal.kr_alpha_sum <= 8.01
    for row in proposal.rows:
        if row.asset_group != "kr_alpha":
            continue
        assert abs(row.min_weight / row.target_weight - 5.36 / 7.0) < 0.02
        assert row.min_weight <= row.target_weight <= row.max_weight


def test_default_add_candidates_excludes_watch():
    adds = default_add_candidates(
        [
            {"ticker": "071050", "grade": "B", "eligible_action": "WATCH"},
            {"ticker": "035420", "grade": "A", "eligible_action": "BUY_CANDIDATE"},
        ],
        limit=5,
    )
    assert all(str(a.get("ticker")) != "071050" for a in adds)
    assert any(str(a.get("ticker")) == "035420" for a in adds)


def test_resolve_add_candidate_uses_compute_bands_not_1_4():
    from src.alpha.target_bridge import resolve_add_candidate

    row = resolve_add_candidate(
        "071050",
        pools=[{"ticker": "071050", "name": "한국금융지주", "role": "satellite", "target_weight": 5.56}],
        kr_alpha_budget=21.85,
    )
    assert float(row["min_weight"]) != 1.0 or float(row["max_weight"]) != 4.0
    assert float(row["min_weight"]) <= float(row["target_weight"]) <= float(row["max_weight"])
