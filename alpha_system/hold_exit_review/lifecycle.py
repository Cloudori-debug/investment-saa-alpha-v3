"""Hold lifecycle state machine — Review-only, no target writes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from alpha_system.hold_exit_review.config import HoldExitReviewConfig


LIFECYCLE_LABELS = {
    "buy_ok": "매수 검토",
    "hold": "보유",
    "just_dropped": "제안 이탈",
    "watch": "관찰",
    "rotate_review": "교체 검토",
    "thesis_review": "가설·즉시 검토",
    "cap_trim": "비중 초과",
}


@dataclass(frozen=True)
class LifecycleView:
    state: str
    label: str
    why: str
    weeks_out: int
    evidence: str
    rotate_gap_ok: bool
    quality_line: str


def _pnl_pct(avg: Optional[float], cur: Optional[float]) -> Optional[float]:
    if avg is None or cur is None or avg <= 0:
        return None
    return (float(cur) - float(avg)) / float(avg) * 100.0


def _quality_evidence(extra: Mapping[str, Any]) -> str:
    bits: list[str] = []
    if extra.get("hakedaka_hits") is not None:
        bits.append(f"하케다카 {extra.get('hakedaka_hits')}히트")
    if extra.get("quant_ok"):
        bits.append("정량 OK")
    qmin = extra.get("quality_gate")
    if qmin:
        bits.append(str(qmin))
    reason = str(extra.get("ineligible_reason") or "").strip()
    if reason:
        bits.append(f"편입: {reason}")
    gate = str(extra.get("gate_flags") or "").strip()
    if gate:
        bits.append(gate)
    return " · ".join(bits) if bits else ""


def evaluate_lifecycle(
    *,
    cfg: HoldExitReviewConfig,
    is_ops_row: bool,
    in_proposal: bool,
    weeks_out: int,
    ops_kind: str,
    cap_over: bool,
    weight_pct: float,
    avg_price: Optional[float],
    current_price: Optional[float],
    total_score: Optional[float],
    best_alternate_score: Optional[float],
    extra: Mapping[str, Any],
) -> LifecycleView:
    kind = (ops_kind or "").strip()
    pnl = _pnl_pct(avg_price, current_price)
    quality_line = _quality_evidence(extra)

    if kind == "exit_full" or (kind == "missing" and is_ops_row):
        return LifecycleView(
            state="thesis_review",
            label=LIFECYCLE_LABELS["thesis_review"],
            why="장부 익절 스텝(교체·전량·목표없음)입니다. 즉시 Review하세요.",
            weeks_out=weeks_out,
            evidence=quality_line,
            rotate_gap_ok=False,
            quality_line=quality_line,
        )

    if cap_over or weight_pct > cfg.management_cap_pct + 1e-6:
        return LifecycleView(
            state="cap_trim",
            label=LIFECYCLE_LABELS["cap_trim"],
            why=(
                f"비중 {weight_pct:.1f}%가 관리 상한 {cfg.management_cap_pct:.0f}%를 넘습니다. "
                "추격 매수 없이 축소만 Review."
            ),
            weeks_out=weeks_out,
            evidence=quality_line,
            rotate_gap_ok=False,
            quality_line=quality_line,
        )

    if pnl is not None and pnl <= -cfg.price_drawdown_thesis_pct:
        return LifecycleView(
            state="thesis_review",
            label=LIFECYCLE_LABELS["thesis_review"],
            why=(
                f"매입가 대비 {pnl:.1f}% 하락(−{cfg.price_drawdown_thesis_pct:.0f}% 기준). "
                "가격 % 손절은 하지 않고 가설·실적을 재심사합니다."
            ),
            weeks_out=weeks_out,
            evidence=quality_line,
            rotate_gap_ok=False,
            quality_line=quality_line,
        )

    if kind in {"trim", "cash_half"}:
        return LifecycleView(
            state="cap_trim" if kind == "trim" else "watch",
            label=LIFECYCLE_LABELS["cap_trim"] if kind == "trim" else LIFECYCLE_LABELS["watch"],
            why=f"익절 스텝「{kind}」— 목표가·근접 구간 Review.",
            weeks_out=weeks_out,
            evidence=quality_line,
            rotate_gap_ok=False,
            quality_line=quality_line,
        )

    gap_ok = False
    if total_score is not None and best_alternate_score is not None:
        gap_ok = float(best_alternate_score) - float(total_score) >= cfg.min_rotate_score_gap

    if not is_ops_row:
        if in_proposal and extra.get("proposal_eligible") is not False:
            return LifecycleView(
                state="buy_ok",
                label=LIFECYCLE_LABELS["buy_ok"],
                why="제안 편입 후보입니다. 월말 Review 전까지 신규·추매는 사람 판단.",
                weeks_out=0,
                evidence=quality_line,
                rotate_gap_ok=False,
                quality_line=quality_line,
            )
        return LifecycleView(
            state="hold",
            label="제안 밖",
            why="최종 제안에 없습니다.",
            weeks_out=0,
            evidence=quality_line,
            rotate_gap_ok=False,
            quality_line=quality_line,
        )

    if in_proposal:
        return LifecycleView(
            state="hold",
            label=LIFECYCLE_LABELS["hold"],
            why="실보유 + 최종 제안 일치. 저평가 해소·가설 유지 시 보유.",
            weeks_out=0,
            evidence=quality_line,
            rotate_gap_ok=False,
            quality_line=quality_line,
        )

    n = cfg.weeks_out_before_rotate
    wout = max(int(weeks_out or 0), 1)
    if wout <= 1:
        return LifecycleView(
            state="just_dropped",
            label=LIFECYCLE_LABELS["just_dropped"],
            why=(
                "이번 주 최종 제안에서 빠졌습니다. 지금 확인하세요. "
                "추가 매수 금지 · 전량 강제는 아님 · "
                f"{n}주 연속 이탈+점수 갭이면 교체 검토."
            ),
            weeks_out=wout,
            evidence=quality_line,
            rotate_gap_ok=gap_ok,
            quality_line=quality_line,
        )
    if wout < n:
        return LifecycleView(
            state="watch",
            label=LIFECYCLE_LABELS["watch"],
            why=(
                f"제안 밖 {wout}/{n}주 — 추가 매수 금지 · 관찰. "
                "+10% 익절 규칙은 사용하지 않습니다."
            ),
            weeks_out=wout,
            evidence=quality_line,
            rotate_gap_ok=gap_ok,
            quality_line=quality_line,
        )

    if gap_ok:
        return LifecycleView(
            state="rotate_review",
            label=LIFECYCLE_LABELS["rotate_review"],
            why=(
                f"제안 밖 {wout}주 연속 + 대체 후보 점수 차 {cfg.min_rotate_score_gap:.0f}점 이상. "
                "월말 교체 Review 후보."
            ),
            weeks_out=wout,
            evidence=quality_line,
            rotate_gap_ok=True,
            quality_line=quality_line,
        )

    return LifecycleView(
        state="watch",
        label=LIFECYCLE_LABELS["watch"],
        why=(
            f"제안 밖 {wout}주이나 대체 종목 점수 차가 {cfg.min_rotate_score_gap:.0f}점 미만 — "
            "교체 보류 · 관찰 유지."
        ),
        weeks_out=wout,
        evidence=quality_line,
        rotate_gap_ok=False,
        quality_line=quality_line,
    )
