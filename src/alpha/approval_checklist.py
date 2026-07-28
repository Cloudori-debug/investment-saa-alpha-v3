from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CheckStatus = Literal["pass", "warn", "fail"]


@dataclass
class ChecklistItem:
    id: str
    label: str
    status: CheckStatus
    detail: str


def build_approval_checklist(
    gpt_context: dict[str, Any],
    *,
    candidate_count: int,
    kr_alpha_target_sum: float,
    kr_alpha_budget: float | None,
    replace_count: int,
    trim_count: int,
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    gate = str(gpt_context.get("data_gate", "UNKNOWN")).upper()
    if gate == "GREEN":
        items.append(ChecklistItem("data_gate", "데이터 게이트", "pass", f"상태: {gate}"))
    elif gate == "YELLOW":
        items.append(ChecklistItem("data_gate", "데이터 게이트", "warn", f"상태: {gate} — 재무 지연/결측 확인"))
    else:
        items.append(ChecklistItem("data_gate", "데이터 게이트", "fail", f"상태: {gate} — 후보 의사결정 보류 권장"))

    min_c, max_c = 20, 30
    if min_c <= candidate_count <= max_c:
        items.append(ChecklistItem("candidate_count", "후보 수 (GPT 검증)", "pass", f"{candidate_count}개"))
    elif candidate_count == 0:
        items.append(ChecklistItem("candidate_count", "후보 수 (GPT 검증)", "fail", "후보 없음"))
    else:
        items.append(
            ChecklistItem(
                "candidate_count",
                "후보 수 (GPT 검증)",
                "warn",
                f"{candidate_count}개 (권장 {min_c}~{max_c})",
            )
        )

    if kr_alpha_budget is not None:
        gap = round(kr_alpha_target_sum - kr_alpha_budget, 2)
        if abs(gap) <= 1.0:
            items.append(
                ChecklistItem(
                    "kr_alpha_budget",
                    "kr_alpha 목표비중 정합",
                    "pass",
                    f"현재 target 합 {kr_alpha_target_sum:.1f}% / Compass {kr_alpha_budget:.1f}%",
                )
            )
        elif kr_alpha_target_sum > kr_alpha_budget:
            items.append(
                ChecklistItem(
                    "kr_alpha_budget",
                    "kr_alpha 목표비중 정합",
                    "warn",
                    f"초과 {gap:.1f}%p — TRIM/교체 후 재조정 필요",
                )
            )
        else:
            items.append(
                ChecklistItem(
                    "kr_alpha_budget",
                    "kr_alpha 목표비중 정합",
                    "warn",
                    f"여유 {-gap:.1f}%p — 신규 후보 추가 여지",
                )
            )
    else:
        items.append(
            ChecklistItem("kr_alpha_budget", "kr_alpha 목표비중 정합", "warn", "Compass 배분 데이터 없음")
        )

    if replace_count == 0:
        items.append(ChecklistItem("replace", "교체 후보", "pass", "REPLACE_CANDIDATE 없음"))
    elif replace_count <= 2:
        items.append(ChecklistItem("replace", "교체 후보", "warn", f"REPLACE {replace_count}건 — 교체 계획 확인"))
    else:
        items.append(
            ChecklistItem("replace", "교체 후보", "fail", f"REPLACE {replace_count}건 — 과도한 교체 압력")
        )

    if trim_count == 0:
        items.append(ChecklistItem("trim", "비중 축소", "pass", "TRIM 없음"))
    else:
        items.append(ChecklistItem("trim", "비중 축소", "warn", f"TRIM {trim_count}건"))

    limitations = gpt_context.get("data_limitations") or []
    if not limitations:
        items.append(ChecklistItem("limitations", "데이터 한계", "pass", "특이사항 없음"))
    else:
        items.append(
            ChecklistItem(
                "limitations",
                "데이터 한계",
                "warn",
                "; ".join(str(x) for x in limitations),
            )
        )

    constraints = gpt_context.get("action_constraints") or []
    items.append(
        ChecklistItem(
            "human_approval",
            "사람 승인 원칙",
            "pass" if constraints else "warn",
            " · ".join(constraints) if constraints else "action_constraints 없음",
        )
    )

    excluded = gpt_context.get("excluded_summary") or {}
    if excluded:
        top = sorted(excluded.items(), key=lambda x: -x[1])[:3]
        detail = ", ".join(f"{k}:{v}" for k, v in top)
        items.append(ChecklistItem("excluded", "제외 요약", "pass", detail))
    else:
        items.append(ChecklistItem("excluded", "제외 요약", "warn", "제외 데이터 없음"))

    return items


def checklist_blocking(items: list[ChecklistItem]) -> bool:
    return any(i.status == "fail" for i in items)


def checklist_summary(items: list[ChecklistItem]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for item in items:
        counts[item.status] += 1
    return counts
