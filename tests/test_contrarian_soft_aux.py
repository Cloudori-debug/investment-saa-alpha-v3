"""역발상 Soft 보조지표."""

from __future__ import annotations

from alpha_system.ui.services.account_ops_checklist import (
    ContrarianGateStep,
    build_contrarian_gate_steps,
)
from alpha_system.ui.services.contrarian_soft_aux import (
    aux_meters_html,
    build_contrarian_soft_aux,
    evidence_quality_pct,
    fear_coverage_pct,
    gate_role_label,
)


def test_gate_role_not_profit() -> None:
    assert "≠수익" in gate_role_label("pass")
    assert "금지" in gate_role_label("fail")
    assert "보류" in gate_role_label("hold")


def test_fear_coverage() -> None:
    assert fear_coverage_pct(available_n=2, missing_n=5) == 29
    assert fear_coverage_pct(available_n=None, missing_n=None) is None


def test_evidence_quality_and_human_risk() -> None:
    thin = evidence_quality_pct(gieop_gate="HOLD", blocker_n=2, unknown_n=3)
    assert thin is not None and thin < 55
    strong = evidence_quality_pct(
        gieop_gate="PASS", blocker_n=0, unknown_n=0, logic_ok=True
    )
    assert strong is not None and strong >= 75
    steps = build_contrarian_gate_steps(
        soft_equity_n=1,
        observe_deep_or_precise=True,
        logic_or_essence_ok=True,
        gieop_gate="PASS",
        fear_tone="ok",
        day_buy_pct=20.0,
    )
    # 강제 pass steps
    assert all(isinstance(s, ContrarianGateStep) for s in steps)
    aux = build_contrarian_soft_aux(
        gate_verdict="pass",
        gate_steps=steps,
        fear_available_n=1,
        fear_missing_n=6,
        gieop_gate="PASS",
        blocker_n=0,
        unknown_n=2,
        logic_ok=True,
    )
    assert aux.mixes_qvm is False
    assert aux.writes_target is False
    assert aux.human_risk is True  # Fear 희소 + U
    assert "사람" in aux.human_risk_ko
    html = aux_meters_html(aux)
    assert "Fear 가용률" in html
    assert "증빙 품질" in html
    assert "QVM" in html or "비가산" in html
