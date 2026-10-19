"""Quasi-ops four-cell card: Data Gate / thesis / allowed / trigger.

Review-only. Missing data is not a sell signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from alpha_system.hold_exit_review.config import HoldExitReviewConfig
from alpha_system.hold_exit_review.lifecycle import LifecycleView


@dataclass(frozen=True)
class OpsCard:
    data_gate: str
    data_gate_detail: str
    thesis: str
    thesis_detail: str
    allowed: str
    trigger: str


def _price_missing(extra: Mapping[str, Any], current_price: Optional[float]) -> bool:
    if current_price is None:
        return True
    kind = str(extra.get("target_gap_kind") or "")
    return kind in {"price_missing", "price_missing_signal_invalid"}


def classify_data_gate(
    *,
    extra: Mapping[str, Any],
    current_price: Optional[float],
    ops_kind: str,
    total_score: Optional[float],
) -> tuple[str, str]:
    """정상 / 일부 누락 / 판단 중단 — never treat errors as 매도."""
    reason = str(extra.get("ineligible_reason") or "").strip()
    eligible = extra.get("proposal_eligible")
    kind = (ops_kind or "").strip()
    score_missing = total_score is None and extra.get("book") in {"ops", "proposal", None}

    if kind == "invalid" or extra.get("quant_ok") is False:
        return "판단 중단", "데이터 오류 — 신규·교체 제안만 멈춤. 매도 신호로 쓰지 않음."
    if eligible is False and reason:
        return "일부 누락", f"편입 게이트: {reason}"
    if _price_missing(extra, current_price):
        return "일부 누락", "현재가 없음 — 가격 손익·급락 판단 보류."
    if score_missing:
        return "일부 누락", "점수 없음 — 순위 탈락 판단 보류."
    if kind == "missing":
        return "일부 누락", "익절 목표가 없음 — 목표가 익절만 보류."
    return "정상", "시세·점수 기준으로 Review 가능."


def classify_thesis(view: LifecycleView, *, in_proposal: bool) -> tuple[str, str]:
    """유지 / 약화 / 훼손."""
    st = view.state
    if st == "thesis_review":
        return "훼손", view.why
    if st in {"watch", "rotate_review", "just_dropped"}:
        return "약화", view.why
    if st == "cap_trim" and not in_proposal:
        return "약화", view.why
    if st == "buy_ok":
        return "유지", "제안 편입 논리(저평가·게이트)가 살아 있습니다."
    if in_proposal or st == "hold":
        return "유지", view.why
    return "약화", view.why


def classify_allowed(
    *,
    data_gate: str,
    thesis: str,
    state: str,
    is_ops: bool,
) -> str:
    if data_gate == "판단 중단":
        return "보유 · 신규·교체 제안 중단"
    if state == "thesis_review" or thesis == "훼손":
        return "매도 검토"
    if state == "cap_trim":
        return "축소"
    if state == "rotate_review":
        return "교체 검토"
    if state in {"watch", "just_dropped"}:
        return "보유 · 추가매수 금지"
    if state == "buy_ok" and not is_ops:
        return "편입 Review · 추가매수는 월말"
    return "보유"


def classify_trigger(
    *,
    cfg: HoldExitReviewConfig,
    view: LifecycleView,
    data_gate: str,
    thesis: str,
    state: str,
) -> str:
    n = cfg.weeks_out_before_rotate
    gap = cfg.min_rotate_score_gap
    dd = cfg.price_drawdown_thesis_pct
    if data_gate == "판단 중단":
        return "데이터 복구 후에만 신규·교체 Review"
    if data_gate == "일부 누락" and state not in {"thesis_review", "cap_trim"}:
        return "빠진 항목이 채워지면 재평가"
    if state == "thesis_review":
        return f"즉시 Review · 가격 −{dd:.0f}%는 손절이 아니라 가설 재심사"
    if state == "cap_trim":
        return f"비중을 관리 상한 {cfg.management_cap_pct:.0f}% 안으로 줄인 뒤 유지 여부 판단"
    if state == "rotate_review":
        return f"월말 Review · 제안 밖 {n}주 + 대체 점수 +{gap:.0f}점"
    if state == "just_dropped":
        return (
            "이번 주 제안에서 빠짐 — 지금 알림. "
            f"교체 후보는 {n}주 연속+점수갭 {gap:.0f}점"
        )
    if state == "watch":
        left = max(n - int(view.weeks_out or 0), 0)
        return f"제안 밖 {view.weeks_out}/{n}주 · {left}주 더 빠지면 교체 검토"
    if state == "buy_ok":
        return "월말 편입 Review · 매일 매수 아님"
    return "저평가 해소·가설 훼손·비중 상한에서만 다음 행동"


def build_ops_card(
    *,
    cfg: HoldExitReviewConfig,
    view: LifecycleView,
    extra: Mapping[str, Any],
    current_price: Optional[float],
    ops_kind: str,
    total_score: Optional[float],
    in_proposal: bool,
    is_ops: bool,
) -> OpsCard:
    gate, gate_d = classify_data_gate(
        extra=extra,
        current_price=current_price,
        ops_kind=ops_kind,
        total_score=total_score,
    )
    thesis, thesis_d = classify_thesis(view, in_proposal=in_proposal)
    allowed = classify_allowed(
        data_gate=gate,
        thesis=thesis,
        state=view.state,
        is_ops=is_ops,
    )
    trigger = classify_trigger(
        cfg=cfg,
        view=view,
        data_gate=gate,
        thesis=thesis,
        state=view.state,
    )
    return OpsCard(
        data_gate=gate,
        data_gate_detail=gate_d,
        thesis=thesis,
        thesis_detail=thesis_d,
        allowed=allowed,
        trigger=trigger,
    )
