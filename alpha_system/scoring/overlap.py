"""Identify CECS sub-factors that overlap entry T2 (event) triggers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OverlapItem:
    cecs_factor: str
    overlap_with: str
    severity: str  # high | medium | low
    rationale: str
    recommendation: str


# Static role analysis — no market data required
T2_CECS_OVERLAPS: tuple[OverlapItem, ...] = (
    OverlapItem(
        cecs_factor="disclosure_status",
        overlap_with="T2 event (주주환원·자사주 공시)",
        severity="high",
        rationale=(
            "CECS disclosure_status는 자사주 소각/매입 이사회 결의·집행을 점수화하고, "
            "T2는 동일 계열의 '확정 이벤트 공시'로 진입 시점을 연다. "
            "같은 공시가 스코어와 트리거에 이중 반영되면 '언제'와 '무엇을'이 섞인다."
        ),
        recommendation=(
            "공시 발생 자체는 T2(언제)에만 둔다. "
            "스코어에는 집행률·지속성 등 강도만 남기거나 disclosure를 eligibility에서 제외."
        ),
    ),
    OverlapItem(
        cecs_factor="execution_continuity",
        overlap_with="T2 event (환원 집행 지속 공시)",
        severity="medium",
        rationale=(
            "연속 분기 환원 실적은 '이미 일어난 이벤트 이력'에 가깝다. "
            "T2가 개별 공시 이벤트를 세면 연속성 점수와 시점 신호가 상관·이중계산될 수 있다."
        ),
        recommendation=(
            "T2는 정책·지수·단일 확정 이벤트 ID로 한정하고, "
            "execution_continuity는 weight_input(무엇을 얼마나)에만 사용."
        ),
    ),
    OverlapItem(
        cecs_factor="independent_catalyst_flag",
        overlap_with="T2 event (종목 자체 촉매 공시)",
        severity="high",
        rationale=(
            "자체 촉매(M&A·실적 이벤트 등) 플래그는 T2 이벤트 목록과 직접 대응 가능. "
            "이벤트 발생=진입 트리거인데 동시에 스코어를 올리면 트리거 충족 종목만 "
            "점수·비중이 부풀려질 수 있다."
        ),
        recommendation=(
            "종목 촉매의 '발생 여부'는 T2, '품질·지속 가능성'만 스코어. "
            "동일 이벤트 ID를 CECS 입력과 T2에 동시에 넣지 말 것."
        ),
    ),
    OverlapItem(
        cecs_factor="policy_dependency_flag",
        overlap_with="T2 event (상법·IFRS·지수 편입 등 매크로 이벤트) / 논지 훼손",
        severity="medium",
        rationale=(
            "정책 의존도는 테마 이벤트(T2)와 논지 훼손 동결과 같은 축을 공유한다. "
            "매크로 이벤트 실현이 점수와 진입을 동시에 움직이면 역할 경계가 흐려진다."
        ),
        recommendation=(
            "매크로 일정·공시는 T2/하드룰(논지 훼손)에 두고, "
            "policy_dependency는 상대적 취약도 감점(무엇을)으로만 유지."
        ),
    ),
    OverlapItem(
        cecs_factor="pension_flow_score",
        overlap_with="T2 event",
        severity="low",
        rationale=(
            "연기금 지분 추세는 통상 T2 '확정 이벤트' 목록과 직접 일치하지 않음. "
            "대량보유 공시를 T2 이벤트로 넣을 때만 겹침."
        ),
        recommendation=(
            "T2 event_ids에 대량보유 공시를 넣지 않는 한 스코어 전용 유지."
        ),
    ),
    OverlapItem(
        cecs_factor="investment_purpose_flag",
        overlap_with="T2 event",
        severity="low",
        rationale="투자목적 분류는 상태 변수에 가깝고 일회성 진입 트리거와 역할이 다름.",
        recommendation="스코어(무엇을) 전용 유지.",
    ),
)


def render_overlap_markdown(items: tuple[OverlapItem, ...] = T2_CECS_OVERLAPS) -> str:
    lines = [
        "# 알파 시스템 — CECS vs T2 트리거 역할 중복 점검",
        "",
        "원칙: **트리거(T2)=언제 사는가**, **스코어=무엇을 얼마나 사는가**.",
        "",
        "| CECS 하위지표 | 겹침 대상 | 심각도 | 권고 |",
        "|---|---|---|---|",
    ]
    for it in items:
        lines.append(
            f"| `{it.cecs_factor}` | {it.overlap_with} | {it.severity} | {it.recommendation} |"
        )
    lines.append("")
    lines.append("## 상세")
    lines.append("")
    for it in items:
        lines.append(f"### `{it.cecs_factor}` ({it.severity})")
        lines.append("")
        lines.append(it.rationale)
        lines.append("")
        lines.append(f"- 권고: {it.recommendation}")
        lines.append("")
    lines.append("## 요약 권고")
    lines.append("")
    lines.append(
        "- **high**: `disclosure_status`, `independent_catalyst_flag` — "
        "이벤트 발생 신호를 T2로 이관하고 스코어에서는 강도·품질만 남길 것."
    )
    lines.append(
        "- **medium**: `execution_continuity`, `policy_dependency_flag` — "
        "T2/하드룰과 ID·일정을 공유하지 않도록 config 경계를 명시."
    )
    lines.append(
        "- **low**: `pension_flow_score`, `investment_purpose_flag` — "
        "기본은 스코어 전용."
    )
    lines.append("")
    lines.append("## 적용 상태 (2026-07-16)")
    lines.append("")
    lines.append(
        "- **적용됨**: high 2항목은 CECS 가중에서 제외, "
        "`tranches.T2.event_candidate_sources`로 매핑. "
        "스코어 축은 5팩터로 재구성 "
        "(`docs/ALPHA_SYSTEM_FIVE_FACTOR_REWEIGHT.md`)."
    )
    lines.append("")
    return "\n".join(lines)


def write_overlap_report(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_overlap_markdown(), encoding="utf-8")
    return path
