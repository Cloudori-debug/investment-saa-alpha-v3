"""역발상 Soft 보조지표 — Review-only · QVM/target 비가산.

게이트 PASS = 수익 신호가 아니라 Review 허가.
Fear Soft = CNN 원본이 아니라 가용 다리 근사.
해부·논리 = 사람 증빙 품질 Soft로 오탐 PASS를 드러냄.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from alpha_system.ui.services.account_ops_checklist import (
    GATE_FAIL,
    GATE_HOLD,
    GATE_PASS,
    ContrarianGateStep,
)

# 표시 밴드 (수익·순위 아님)
BAND_KO = {
    "strong": "증빙 충분(참고)",
    "ok": "보통",
    "thin": "얇음·주의",
    "empty": "미수집",
}


@dataclass(frozen=True)
class AuxMeter:
    key: str
    label_ko: str
    score: int | None  # 0–100 Soft · None=미수집
    band_ko: str
    detail_ko: str
    not_alpha: bool = True  # Soft 점수·target 합산 금지 명시


@dataclass(frozen=True)
class ContrarianSoftAux:
    """게이트와 직교하는 보조 판독."""

    gate_role_ko: str
    # 예: Review 허가(≠수익) / Review 보류 / Review 금지·파킹
    checklist_fill_pct: int  # 게이트 중 PASS 비율 · 채워짐이지 알파 아님
    fear_coverage_pct: int | None
    evidence_quality_pct: int | None
    human_risk: bool
    human_risk_ko: str
    meters: tuple[AuxMeter, ...]
    line_ko: str
    review_only: bool = True
    writes_target: bool = False
    mixes_qvm: bool = False


def gate_role_label(verdict: str) -> str:
    v = str(verdict or "").strip().lower()
    if v == GATE_PASS:
        return "Review 허가(≠수익·≠자동매수)"
    if v == GATE_FAIL:
        return "Review 금지 · 대기·파킹"
    return "Review 보류 · 매수 배지 없음"


def _band(score: int | None) -> str:
    if score is None:
        return BAND_KO["empty"]
    if score >= 75:
        return BAND_KO["strong"]
    if score >= 45:
        return BAND_KO["ok"]
    return BAND_KO["thin"]


def checklist_fill_pct(steps: Sequence[ContrarianGateStep]) -> int:
    if not steps:
        return 0
    n_pass = sum(1 for s in steps if s.status == GATE_PASS)
    return int(round(100.0 * n_pass / len(steps)))


def fear_coverage_pct(
    *,
    available_n: int | None = None,
    missing_n: int | None = None,
) -> int | None:
    """Fear Soft 다리 가용률 · CNN 원본 신뢰도와 별개."""
    if available_n is None and missing_n is None:
        return None
    a = int(available_n or 0)
    m = int(missing_n or 0)
    tot = a + m
    if tot <= 0:
        return None
    return int(round(100.0 * a / tot))


def evidence_quality_pct(
    *,
    gieop_gate: str | None = None,
    blocker_n: int | None = None,
    unknown_n: int | None = None,
    logic_ok: bool | None = None,
    pass_value: bool | None = None,
) -> int | None:
    """해부·논리 증빙 Soft · 사람 의존을 숫자로 드러냄 (QVM 아님)."""
    g = str(gieop_gate or "").strip().upper()
    if not g and logic_ok is None and pass_value is None:
        return None

    score = 50.0
    if g == "PASS":
        score = 82.0
    elif g == "HOLD":
        score = 45.0
    elif g == "FAIL":
        score = 10.0
    elif not g:
        score = 35.0

    b = int(blocker_n or 0)
    u = int(unknown_n or 0)
    score -= min(30.0, 6.0 * b)
    score -= min(25.0, 5.0 * u)

    if logic_ok is True or pass_value is True:
        score += 8.0
    if logic_ok is False or pass_value is False:
        score -= 20.0

    return int(max(0, min(100, round(score))))


def build_contrarian_soft_aux(
    *,
    gate_verdict: str,
    gate_steps: Sequence[ContrarianGateStep],
    fear_available_n: int | None = None,
    fear_missing_n: int | None = None,
    gieop_gate: str | None = None,
    blocker_n: int | None = None,
    unknown_n: int | None = None,
    logic_ok: bool | None = None,
    pass_value: bool | None = None,
) -> ContrarianSoftAux:
    fill = checklist_fill_pct(gate_steps)
    fear_cov = fear_coverage_pct(
        available_n=fear_available_n, missing_n=fear_missing_n
    )
    evid = evidence_quality_pct(
        gieop_gate=gieop_gate,
        blocker_n=blocker_n,
        unknown_n=unknown_n,
        logic_ok=logic_ok,
        pass_value=pass_value,
    )
    role = gate_role_label(gate_verdict)

    # 사람 의존 위험: 게이트가 pass처럼 보여도 증빙 얇음·HOLD·미수집
    human_risk = False
    reasons: list[str] = []
    g = str(gieop_gate or "").strip().upper()
    if gate_verdict == GATE_PASS and (evid is None or evid < 55):
        human_risk = True
        reasons.append("허가인데 증빙 Soft 얇음")
    if g in {"", "HOLD"} and gate_verdict != GATE_FAIL:
        human_risk = True
        reasons.append("해부 HOLD/없음 · 사람 재확인")
    if fear_cov is not None and fear_cov < 40:
        human_risk = True
        reasons.append(f"Fear 가용 {fear_cov}% · 근사만")
    if unknown_n and int(unknown_n) > 0:
        human_risk = True
        reasons.append(f"미확인(U) {int(unknown_n)}")

    risk_ko = (
        "사람 재확인 권고 · " + " · ".join(reasons[:3])
        if human_risk
        else "보조지표상 큰 사람위험 플래그 없음(여전히 Review)"
    )

    meters = (
        AuxMeter(
            "checklist_fill",
            "게이트 채워짐",
            fill,
            _band(fill),
            "AND 스텝 중 PASS 비율 · 알파·수익 아님",
        ),
        AuxMeter(
            "fear_coverage",
            "Fear 가용률",
            fear_cov,
            _band(fear_cov),
            "가용 다리/(가용+미수집) · CNN 원본 아님",
        ),
        AuxMeter(
            "evidence_quality",
            "증빙 품질 Soft",
            evid,
            _band(evid),
            "해부·논리·U/blocker Soft · QVM 비가산",
        ),
    )
    line = (
        f"{role} · 채워짐 {fill}%"
        + (f" · Fear가용 {fear_cov}%" if fear_cov is not None else " · Fear가용 미수집")
        + (f" · 증빙 {evid}" if evid is not None else " · 증빙 미수집")
        + (" · ⚠사람위험" if human_risk else "")
    )
    return ContrarianSoftAux(
        gate_role_ko=role,
        checklist_fill_pct=fill,
        fear_coverage_pct=fear_cov,
        evidence_quality_pct=evid,
        human_risk=human_risk,
        human_risk_ko=risk_ko,
        meters=meters,
        line_ko=line,
    )


def aux_meters_html(aux: ContrarianSoftAux) -> str:
    from html import escape

    cells = []
    for m in aux.meters:
        sc = "—" if m.score is None else f"{m.score}"
        cells.append(
            "<div class=\"pf-aux-meter\">"
            f"<div class=\"pf-aux-lab\">{escape(m.label_ko)}</div>"
            f"<div class=\"pf-aux-sc\">{escape(sc)}</div>"
            f"<div class=\"pf-aux-band\">{escape(m.band_ko)}</div>"
            f"<div class=\"pf-aux-det\">{escape(m.detail_ko)}</div>"
            "</div>"
        )
    risk_cls = "pf-aux-risk-on" if aux.human_risk else "pf-aux-risk-off"
    style = (
        "<style>"
        ".pf-aux-wrap{margin-top:0.45rem}"
        ".pf-aux-role{font-weight:700;margin-bottom:0.25rem}"
        ".pf-aux-row{display:flex;flex-wrap:wrap;gap:0.45rem}"
        ".pf-aux-meter{flex:1 1 7.5rem;min-width:7rem;padding:0.35rem 0.4rem;"
        "background:#eef2f7;border-radius:4px;border:1px solid #d0d7e2}"
        ".pf-aux-lab{font-size:0.8rem;color:#445}"
        ".pf-aux-sc{font-size:1.15rem;font-weight:700}"
        ".pf-aux-band{font-size:0.78rem;color:#356}"
        ".pf-aux-det{font-size:0.72rem;color:#667;margin-top:0.15rem}"
        ".pf-aux-risk-on{margin-top:0.35rem;color:#7a1f1f;font-weight:600}"
        ".pf-aux-risk-off{margin-top:0.35rem;color:#456;font-size:0.85rem}"
        ".pf-aux-note{font-size:0.78rem;color:#668;margin-top:0.25rem}"
        "</style>"
    )
    return (
        f'<div class="pf-aux-wrap">{style}'
        f'<div class="pf-aux-role">{escape(aux.gate_role_ko)}</div>'
        f'<div class="pf-aux-row">{"".join(cells)}</div>'
        f'<div class="{risk_cls}">{escape(aux.human_risk_ko)}</div>'
        '<div class="pf-aux-note">'
        "보조지표 · QVM·target·자동매수 비가산 · 학술 프리미엄 증명 아님"
        "</div></div>"
    )


__all__ = [
    "AuxMeter",
    "ContrarianSoftAux",
    "aux_meters_html",
    "build_contrarian_soft_aux",
    "checklist_fill_pct",
    "evidence_quality_pct",
    "fear_coverage_pct",
    "gate_role_label",
]
