"""Journal action_kind → filter category."""

from __future__ import annotations

from alpha_system.journal.recorder import JournalRecord

FILTER_LABELS = {
    "전체": "전체",
    "집행·전이": "집행·전이",
    "경고": "경고",
    "차단": "차단",
    "재량": "재량",
    "데이터": "데이터",
    "입력": "입력",
}

_KIND_CATEGORY: dict[str, str] = {
    "EXECUTE": "집행·전이",
    "MARK_READY": "집행·전이",
    "TRANCHE_STATE_TRANSITION": "집행·전이",
    "TRIGGER_FIRED": "집행·전이",
    "TRIGGER_CLEARED": "집행·전이",
    "PARTIAL_EXECUTED": "집행·전이",
    "FREEZE": "집행·전이",
    "REFLUX_TO_SAA": "집행·전이",
    "GO_LIVE_DECLARE": "집행·전이",
    "SWAP_CANDIDATE": "집행·전이",
    "TRANCHE_EXEC_FILL": "집행·전이",
    "TRANCHE_EXEC_ACK": "집행·전이",
    "REDUCE_COMPLETE": "집행·전이",
    "WARN_BLOCKED": "차단",
    "HARD_RULE_BLOCK": "차단",
    "GO_LIVE_ATTEMPT_BLOCKED": "차단",
    "WARN_DISCRETIONARY": "재량",
    "exit_warn_discretionary": "재량",
    "WARN_TARGET_VALUATION_MODIFY": "경고",
    "CAP_WARN": "경고",
    "CAP_OVER": "경고",
    "LIQUIDATE": "경고",
    "REDUCE": "경고",
    "CHECKLIST_RECHECK": "경고",
    "CECS_SCORE_FINALIZED": "입력",
    "CECS_SCORE_APPROVED": "입력",
    "CECS_AI_RESEARCH_GENERATED": "데이터",
    "CECS_BATCH_IMPORT": "데이터",
    "CECS_FINAL_REOPEN": "입력",
    "SCORE_CUTOFF_CONFIRMED": "입력",
    "T3_HISTORY_REFRESH": "데이터",
    "DATA_REFRESH_OK": "데이터",
    "DATA_REFRESH_FAIL": "데이터",
    "AI_VERIFICATION_REPORT": "데이터",
    "QUANT_SNAPSHOT_OK": "데이터",
    "WEEKLY_QUAL_REPORT_GENERATED": "데이터",
    "WEEKLY_QUAL_IMPORT": "데이터",
    "WEEKLY_TARGETS_SUPPLEMENT_GENERATED": "데이터",
    "WEEKLY_TARGETS_SUPPLEMENT_IMPORT": "데이터",
    "WEEKLY_DOMAIN_APPROVED": "입력",
    "RESCORE_HOOK_EVAL": "데이터",
    "RESCORE_TRIGGER_FIRED": "재채점",
    "T2_EVENT_RECORD": "입력",
    "T2_EVENT_CANCEL": "입력",
    "THESIS_DAMAGE_FLAG": "입력",
    "THESIS_DAMAGE_CANCEL": "입력",
    "TARGET_VALUATION_MODIFY": "입력",
    "ENTRY_JOURNAL": "입력",
}


def categorize(kind: str) -> str:
    return _KIND_CATEGORY.get(kind, "경고")


def filter_entries(entries: list[JournalRecord], category: str) -> list[JournalRecord]:
    if category == "전체":
        return entries
    return [e for e in entries if categorize(e.action_kind) == category]
