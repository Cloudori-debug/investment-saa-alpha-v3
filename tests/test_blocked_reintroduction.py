"""Blocked reintroduction after manual unintended removal."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.alpha.target_bridge import apply_proposed_target, propose_target_changes
from src.alpha.target_portfolio_guard import (
    TargetPortfolioWriteBlockedError,
    get_blocked_reintroductions,
    record_blocked_reintroduction,
)
from src.alpha.target_write_audit import write_operational_target
from src.models import TargetRow


def _write_target(path: Path, rows: list[dict]) -> None:
    import csv

    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _row(ticker: str, weight: float) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "asset_group": "kr_alpha",
        "sector": "tech",
        "role": "core",
        "target_weight": weight,
        "min_weight": 0,
        "max_weight": 20,
    }


def test_manual_unintended_removal_records_block(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0), _row("030190", 0.8)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0), _row("030190", 0.8)])

    result = write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 10.0))],
        source="manual_admin_override",
        reason="remove_unintended_030190_reintroduced_by_approval_bridge",
        approved_by_user=True,
        output_dir=out,
    )
    assert result.success
    assert "030190" in get_blocked_reintroductions(data)


def test_approval_bridge_blocked_without_override(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    record_blocked_reintroduction(
        data,
        "030190",
        reason="remove_unintended_030190",
        source="manual_admin_override",
    )
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])

    result = write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 10.0)), TargetRow.model_validate(_row("030190", 0.8))],
        source="approval_bridge",
        reason="alpha_proposal_approved_by=human",
        approved_by_user=True,
        output_dir=out,
    )
    assert result.blocked
    assert "030190" not in (data / "target_portfolio.csv").read_text(encoding="utf-8")


def test_approval_bridge_allowed_with_override(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    record_blocked_reintroduction(
        data,
        "030190",
        reason="remove_unintended_030190",
        source="manual_admin_override",
    )
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])

    result = write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 10.0)), TargetRow.model_validate(_row("030190", 0.8))],
        source="approval_bridge",
        reason="alpha_proposal_approved_by=human",
        approved_by_user=True,
        output_dir=out,
        override_previous_removal=frozenset({"030190"}),
    )
    assert result.success
    assert "030190" not in get_blocked_reintroductions(data)


def test_propose_excludes_blocked_from_baseline(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    record_blocked_reintroduction(
        data,
        "030190",
        reason="remove_unintended_030190",
        source="manual_admin_override",
    )
    current = [TargetRow.model_validate(_row("005830", 10.0)), TargetRow.model_validate(_row("030190", 0.8))]
    proposal = propose_target_changes(
        current,
        add_candidates=[],
        trim_tickers=set(),
        remove_tickers=set(),
        data_dir=data,
    )
    tickers = {r.ticker for r in proposal.rows if r.target_weight > 0}
    assert "030190" not in tickers


def test_merge_target_draft_excludes_blocked(tmp_path: Path) -> None:
    import pandas as pd

    from src.alpha.target_draft_bridge import merge_target_draft

    data = tmp_path / "data"
    data.mkdir()
    record_blocked_reintroduction(
        data,
        "030190",
        reason="remove_unintended_030190",
        source="manual_admin_override",
    )
    current = [
        TargetRow.model_validate(_row("005830", 10.0)),
        TargetRow.model_validate(_row("069500", 15.0)),
    ]
    current[1].asset_group = "domestic_beta"
    draft = pd.DataFrame(
        [
            _row("005830", 9.0),
            _row("030190", 1.0),
        ]
    )
    proposal = merge_target_draft(current, draft, data_dir=data)
    tickers = {r.ticker for r in proposal.rows if r.target_weight > 0}
    assert "030190" not in tickers
    assert any("030190" in w for w in proposal.warnings)


def test_apply_proposed_target_strips_blocked(tmp_path: Path) -> None:
    from src.alpha.target_bridge import TargetProposal, apply_proposed_target

    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    record_blocked_reintroduction(
        data,
        "030190",
        reason="remove_unintended_030190",
        source="manual_admin_override",
    )
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])

    proposal = TargetProposal(
        rows=[
            TargetRow.model_validate(_row("005830", 10.0)),
            TargetRow.model_validate(_row("030190", 0.8)),
        ],
        changes=[],
    )
    apply_proposed_target(
        proposal,
        data / "target_portfolio.csv",
        data_dir=data,
        output_dir=out,
    )
    text = (data / "target_portfolio.csv").read_text(encoding="utf-8")
    assert "030190" not in text
    assert "005830" in text
