"""Gap table exit-status enrich (display-only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ui.portfolio_panel import enrich_gap_with_exit_status, exit_status_label_for_gap

ALPHA_PANEL = Path(__file__).resolve().parents[1] / "src" / "ui" / "alpha_panel.py"
WORKFLOW = Path(__file__).resolve().parents[1] / "src" / "ui" / "target_draft_workflow.py"


def test_exit_status_labels() -> None:
    assert exit_status_label_for_gap(on_board=False, targets_missing=False, exit_leg=None) == "—"
    assert exit_status_label_for_gap(on_board=True, targets_missing=True, exit_leg="NONE") == "목표 미설정"
    assert exit_status_label_for_gap(on_board=True, targets_missing=False, exit_leg="NONE") == "미도달"
    assert (
        exit_status_label_for_gap(
            on_board=True,
            targets_missing=False,
            exit_leg="NONE",
            val_proximity_pct=83.7,
        )
        == "미도달 (VAL 83.7%)"
    )
    assert exit_status_label_for_gap(on_board=True, targets_missing=False, exit_leg="FUND") == "도달(FUND)"
    assert exit_status_label_for_gap(on_board=True, targets_missing=False, exit_leg="VAL") == "도달(VAL)"
    assert exit_status_label_for_gap(on_board=True, targets_missing=False, exit_leg="BOTH") == "도달(BOTH)"


def test_enrich_gap_preserves_weights_and_maps_exit() -> None:
    gap = pd.DataFrame(
        [
            {"ticker": "030200", "name": "KT", "current_weight": 3.1, "target_weight": 2.5, "gap": -0.6},
            {"ticker": "069500", "name": "KODEX200", "current_weight": 10.0, "target_weight": 12.0, "gap": 2.0},
            {"ticker": "005930", "name": "삼성전자", "current_weight": 1.0, "target_weight": 1.0, "gap": 0.0},
        ]
    )
    board = pd.DataFrame(
        [
            {
                "ticker": "030200",
                "exit_leg": "NONE",
                "targets_missing": True,
                "fund_proximity_pct": "",
                "val_proximity_pct": "",
            },
            {
                "ticker": "005930",
                "exit_leg": "VAL",
                "targets_missing": False,
                "fund_proximity_pct": "",
                "val_proximity_pct": "100",
            },
        ]
    )
    out = enrich_gap_with_exit_status(gap, board)
    assert list(out["current_weight"]) == [3.1, 10.0, 1.0]
    assert list(out["gap"]) == [-0.6, 2.0, 0.0]
    assert list(out.columns).index("익절상태") == list(out.columns).index("gap") + 1
    assert out.loc[out["ticker"] == "030200", "익절상태"].iloc[0] == "목표 미설정"
    assert out.loc[out["ticker"] == "069500", "익절상태"].iloc[0] == "—"
    assert out.loc[out["ticker"] == "005930", "익절상태"].iloc[0] == "도달(VAL)"


def test_enrich_gap_appends_proximity_when_not_reached() -> None:
    gap = pd.DataFrame([{"ticker": "030200", "gap": -0.5}])
    board = pd.DataFrame(
        [
            {
                "ticker": "030200",
                "exit_leg": "NONE",
                "targets_missing": False,
                "fund_proximity_pct": "",
                "val_proximity_pct": 83.7,
            }
        ]
    )
    out = enrich_gap_with_exit_status(gap, board)
    assert out.iloc[0]["익절상태"] == "미도달 (VAL 83.7%)"

def test_target_tabs_no_longer_embed_take_profit_board() -> None:
    alpha_src = ALPHA_PANEL.read_text(encoding="utf-8")
    assert 'widget_key="alpha_target_tab_take_profit"' not in alpha_src
    assert 'widget_key="alpha_take_profit_signals"' in alpha_src
    workflow_src = WORKFLOW.read_text(encoding="utf-8")
    assert "render_take_profit_signals" not in workflow_src
