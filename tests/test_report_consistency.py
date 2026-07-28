from __future__ import annotations

from src.execution_scope import is_executable_kr_risk_trim
from src.models import GapRow, TradeAction
from src.report_writer import write_trigger_alerts
from pathlib import Path


def test_trigger_alerts_kr_risk_trim_not_labeled_theoretical(tmp_path):
    gaps = [
        GapRow(
            ticker="005440",
            name="현대지에프홀딩스",
            asset_group="kr_alpha",
            current_weight=6.0,
            target_weight=0.85,
            gap=-5.15,
            min_weight=0.92,
            max_weight=2.76,
            status="Overweight",
            in_target=True,
        ),
    ]
    actions = [
        TradeAction(
            ticker="005440",
            name="현대지에프홀딩스",
            action="Trim",
            reason="ETF_ONLY — kr_alpha 리스크 축소 Trim (사람 승인·1회 제한)",
            allowed_size_pct=-1.7,
            priority="High",
        ),
    ]
    review = [
        TradeAction(
            ticker="005440",
            name="현대지에프홀딩스",
            action="Trim",
            reason="kr_alpha 리스크 축소 Trim (ETF_ONLY·사람 승인 필요)",
            allowed_size_pct=-1.7,
            priority="High",
        ),
    ]
    policy = {"kr_alpha_risk_trim_under_etf_only": True}
    assert is_executable_kr_risk_trim(actions[0], policy)

    out = tmp_path / "trigger_alerts.md"
    write_trigger_alerts(
        out,
        [],
        actions,
        review_actions=review,
        execution_scope="ETF_ONLY",
        gap_rows=gaps,
        data_gate="YELLOW",
        alpha_position_action="RISK_REDUCE_ONLY",
        execution_policy=policy,
    )
    text = out.read_text(encoding="utf-8")
    assert "Executable — kr_alpha 리스크 축소 Trim" in text
    assert "005440" in text
    assert "theoretical Trim [매도금지]: 현대지에프홀딩스 (005440)" not in text
