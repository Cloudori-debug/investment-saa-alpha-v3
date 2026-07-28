"""Operator-facing Korean display for journal / queue English leftovers.

Storage stays English-capable; UI should show what to do in Korean.
"""

from __future__ import annotations

import re
from typing import Any

# Exact discretionary_reason / rationale phrases seen in fixtures & ops notes.
_REASON_KO: dict[str, str] = {
    "macro shock — cut risk before window rule fires": (
        "매크로 충격 - 창 규칙이 발동하기 전에 위험을 줄인 기록"
    ),
    "macro shock": "매크로(시장 전반) 충격",
    "liquidity event": "유동성 사건(거래·환금이 어려운 상황)",
    "test deviation": "테스트용 재량 이탈(실운용 무시 가능)",
    "시장 변동성 대기": "시장 변동성 대기",
}

_ACTION_KIND_KO: dict[str, str] = {
    "WARN_DISCRETIONARY": "재량 이탈 경고",
    "exit_warn_discretionary": "재량 청산 경고",
    "GO_LIVE_DECLARE": "가동 선언",
    "GO_LIVE_ATTEMPT_BLOCKED": "가동 선언 차단",
    "TRANCHE_STATE_TRANSITION": "트랜치 상태 변경",
    "TRANCHE_EXEC_ACK": "트랜치 집행 확인",
    "TRANCHE_EXEC_FILL": "트랜치 체결 기록",
    "REDUCE_COMPLETE": "감축 완료",
    "HARD_RULE_BLOCK": "하드 규칙 차단",
    "CAP_WARN": "비중 한도 주의",
    "CAP_OVER": "비중 한도 초과",
    "DATA_REFRESH_OK": "데이터 갱신 성공",
    "DATA_REFRESH_FAIL": "데이터 갱신 실패",
    "QUANT_SNAPSHOT_OK": "정량 스냅샷 완료",
    "T2_EVENT_RECORD": "T2 이벤트 기록",
    "T2_EVENT_CANCEL": "T2 이벤트 취소",
    "THESIS_DAMAGE_FLAG": "논지 훼손 표시",
    "THESIS_DAMAGE_CANCEL": "논지 훼손 취소",
    "TARGET_VALUATION_MODIFY": "목표가·밸류에이션 수정",
    "WARN_TARGET_VALUATION_MODIFY": "목표가 수정 경고",
    "CECS_SCORE_APPROVED": "CECS 점수 승인",
    "CECS_BATCH_IMPORT": "CECS 일괄 가져오기",
    "CECS_AI_RESEARCH_GENERATED": "CECS AI 조사 요청서 생성",
    "WEEKLY_QUAL_REPORT_GENERATED": "주간 정성 보고서 생성",
    "WEEKLY_QUAL_IMPORT": "주간 정성 가져오기",
    "WEEKLY_DOMAIN_APPROVED": "주간 도메인 승인",
    "WEEKLY_TARGETS_SUPPLEMENT_GENERATED": "주간 목표가 보충 생성",
    "WEEKLY_TARGETS_SUPPLEMENT_IMPORT": "주간 목표가 보충 가져오기",
    "RESCORE_TRIGGER_FIRED": "재채점 트리거 발화",
    "RESCORE_HOOK_EVAL": "재채점 훅 평가",
    "SCORE_CUTOFF_CONFIRMED": "점수 컷오프 확정",
    "PROPOSAL_FREEZE_RELEASED": "제안 고정 해제",
    "SWAP_CANDIDATE": "스왑 후보 관찰",
    "CHECKLIST_RECHECK": "체크리스트 재확인",
    "T3_HISTORY_REFRESH": "T3 PBR 이력 갱신",
    "ENTRY_JOURNAL": "편입 기록",
}

_SUBJECT_KO: dict[str, str] = {
    "E": "이벤트 E(매크로·창 관련)",
    "X": "테스트 대상 X",
    "system": "시스템",
    "batch": "일괄 처리",
}

_DISCRETION_HINT = (
    "당장 자동매매·강제 청산은 없습니다. "
    "같은 유형이 자주 쌓이면 「규칙이 현실과 안 맞다」는 신호이니 "
    "저널을 보고 규칙을 손볼지 사람만 판단하세요."
)


def reason_ko(raw: str | None) -> str:
    """Map known English reasons; keep unknown text as-is if already Korean-ish."""
    if not raw:
        return "사유 없음"
    s = str(raw).strip()
    if s in _REASON_KO:
        return _REASON_KO[s]
    low = s.lower()
    for eng, ko in _REASON_KO.items():
        if eng.lower() == low:
            return ko
    # Soft pattern matches
    if "macro shock" in low:
        return "매크로(시장 전반) 충격 관련: " + s
    if "liquidity" in low:
        return "유동성 관련: " + s
    if "test" in low and "deviation" in low:
        return "테스트용 이탈: " + s
    return s


def action_kind_ko(kind: str | None) -> str:
    k = str(kind or "").strip()
    if not k:
        return "기록"
    return _ACTION_KIND_KO.get(k, k)


def subject_ko(subject: str | None) -> str:
    s = str(subject or "").strip()
    if not s:
        return "대상 없음"
    if s in _SUBJECT_KO:
        return _SUBJECT_KO[s]
    if s.isdigit() and len(s) <= 6:
        return f"종목 {s.zfill(6)}"
    return s


def format_discretionary_warning(entry: Any) -> str:
    """Multi-line Korean blurb for journal / home."""
    day = str(getattr(entry, "recorded_at", "") or "")[:10]
    subj = subject_ko(getattr(entry, "subject", None))
    reason = reason_ko(
        getattr(entry, "discretionary_reason", None) or getattr(entry, "rationale", None)
    )
    return (
        f"{day} · {subj}\n"
        f"무엇: 규칙 밖에서 한 판단이 기록됨 (재량 이탈)\n"
        f"사유: {reason}\n"
        f"할 일: {_DISCRETION_HINT}"
    )


def format_journal_timeline_line(entry: Any) -> tuple[str, str]:
    """Return (title_md, body_text) for timeline rows."""
    day = str(getattr(entry, "recorded_at", "") or "")[:19]
    kind = action_kind_ko(getattr(entry, "action_kind", None))
    raw_kind = str(getattr(entry, "action_kind", "") or "")
    subj = subject_ko(getattr(entry, "subject", None))
    body = reason_ko(getattr(entry, "rationale", None) or "")
    if getattr(entry, "discretionary_reason", None):
        body = reason_ko(entry.discretionary_reason)
    title = f"**{day}** {kind}"
    if raw_kind and raw_kind != kind:
        title += f" `{raw_kind}`"
    title += f" · {subj}"
    return title, (body or "")[:400]


def severity_ko(level: str | None) -> str:
    return {"danger": "긴급", "warn": "주의", "info": "안내"}.get(
        str(level or "").lower(), "안내"
    )
