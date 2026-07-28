from __future__ import annotations

from pathlib import Path

import pytest

from src.decision.duration_diagnostic import build_duration_bond_status
from src.models import PositionRow


def test_duration_split_cash_only_portfolio(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "duration_sleeve_tags.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "data" / "duration_sleeve_tags.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (data_dir / "look_through_tags.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "data" / "look_through_tags.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    positions = [
        PositionRow(
            ticker="157450",
            name="TIGER 단기통안채",
            asset_group="cash_short_bond",
            sector="bond",
            style="short_duration",
            current_value=23_000_000,
        ),
        PositionRow(
            ticker="459580",
            name="KODEX CD금리액티브",
            asset_group="cash_short_bond",
            sector="bond",
            style="cash_like",
            current_value=9_000_000,
        ),
        PositionRow(
            ticker="CASH",
            name="예수금",
            asset_group="cash_short_bond",
            sector="cash",
            style="cash",
            current_value=18_000_000,
        ),
        PositionRow(
            ticker="005830",
            name="DB손해보험",
            asset_group="kr_alpha",
            sector="insurance",
            current_value=6_000_000,
        ),
    ]

    status = build_duration_bond_status(
        positions=positions,
        targets=[],
        gap_rows=[],
        allocation_groups=None,
        data_dir=data_dir,
    )

    assert status["kr_duration_bond_current_pct"] == 0.0
    assert status["cash_short_current_pct"] > 50.0
    assert status["kr_duration_gap"] == "absent"
    assert "중장기" in status["diagnosis"] or "부재" in status["diagnosis"]
    assert status["execution_impact"] == "none — v1.0.2 unchanged"
