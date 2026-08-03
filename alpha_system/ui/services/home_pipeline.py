"""Home pipeline stages — portfolio-ready progress with lock reasons + deep links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.data_freshness import SourceStatus
from alpha_system.ui.services.nav import (
    FOCUS_DATA_REFRESH,
    FOCUS_CUTOFF,
    FOCUS_GO_LIVE,
    FOCUS_SCORES,
    FOCUS_T3_DETAIL,
    PAGE_APPROVAL,
    PAGE_PORTFOLIO,
)
from alpha_system.ui.services.weekly_qual_report import (
    WEEKLY_DOMAIN_KEYS,
    load_weekly_suggestions,
)


@dataclass(frozen=True)
class PipelineStage:
    key: str
    step: int
    title: str
    status: str  # ok | warn | locked
    reason: str
    cta_label: str
    page: str
    focus: Optional[str] = None
    prefill: Optional[dict[str, Any]] = None
    blocks_next: bool = False


@dataclass(frozen=True)
class PreparationItem:
    key: str
    title: str
    status: str  # ok | warn | missing
    summary: str


@dataclass(frozen=True)
class HomeOverview:
    preparation: tuple[PreparationItem, ...]
    next_action: Optional[PipelineStage]
    pending_approvals: int
    proposal_count: int


def build_home_overview(ctx: DashboardContext) -> HomeOverview:
    """Collapse the workflow into preparation, one action, and proposal result."""
    sources = {s.key: s for s in (ctx.source_status or [])}
    scores_src = sources.get("alpha_scores")
    quant_missing = scores_src is None or not scores_src.exists
    quant_stale = bool(scores_src and scores_src.stale)
    if quant_missing:
        quant = PreparationItem(
            key="quant",
            title="정량",
            status="missing",
            summary="스냅샷 없음",
        )
    elif quant_stale:
        quant = PreparationItem(
            key="quant",
            title="정량",
            status="warn",
            summary=f"갱신 필요 · as_of {scores_src.as_of or '—'}",
        )
    else:
        quant = PreparationItem(
            key="quant",
            title="정량",
            status="ok",
            summary=f"준비됨 · as_of {scores_src.as_of or '파일 기준'}",
        )

    weekly = load_weekly_suggestions(ctx.root)
    approved = dict(weekly.get("approved") or {}) if weekly else {}
    statuses = dict(weekly.get("domain_status") or {}) if weekly else {}
    # QUAL_PUBLIC_OVERLAY: weekly domains are optional brakes, not home blockers.
    pending = [
        key
        for key in WEEKLY_DOMAIN_KEYS
        if statuses.get(key) == "ai_suggested" and not approved.get(key, False)
    ]
    failed = [
        key
        for key in WEEKLY_DOMAIN_KEYS
        if statuses.get(key) in {"failed", "empty", "missing"}
        and not approved.get(key, False)
    ]
    qualitative = PreparationItem(
        key="qualitative",
        title="공적 브레이크",
        status="ok",
        summary=(
            f"선택 · 미승인 {len(pending)}영역"
            if pending
            else (
                f"선택 · as_of {weekly.get('as_of') or '—'}"
                if weekly
                else "선택 · 증권사 SoT 금지"
            )
        ),
    )
    if failed and not pending:
        qualitative = PreparationItem(
            key="qualitative",
            title="공적 브레이크",
            status="warn",
            summary=f"선택 보완 · {', '.join(failed)}",
        )

    next_action: Optional[PipelineStage]
    if quant_missing or quant_stale:
        next_action = PipelineStage(
            key="quant",
            step=1,
            title="정량 스냅샷 갱신",
            status="warn" if quant_stale else "locked",
            reason=(
                "alpha_scores가 오래되었습니다. 정량 데이터와 점수를 한 번에 갱신하세요."
                if quant_stale
                else "alpha_scores가 없습니다. 정량 데이터와 점수를 먼저 수집하세요."
            ),
            cta_label="정량 전체 갱신",
            page=PAGE_APPROVAL,
            focus=FOCUS_DATA_REFRESH,
            blocks_next=True,
        )
    else:
        next_action = first_blocker(build_pipeline_stages(ctx))

    proposal_n = int(
        getattr(ctx, "proposal_count", None) or len(ctx.portfolio_rows or [])
    )
    return HomeOverview(
        preparation=(quant, qualitative),
        next_action=next_action,
        pending_approvals=len(pending),
        proposal_count=proposal_n,
    )


def build_pipeline_stages(ctx: DashboardContext) -> list[PipelineStage]:
    """Ordered stages from quant → proposal → go-live → ops."""
    sources = {s.key: s for s in (ctx.source_status or [])}
    scores_src = sources.get("alpha_scores")
    eligible_n = sum(1 for r in ctx.scoreboard_rows if r.eligibility is True)
    proposal_n = int(getattr(ctx, "proposal_count", None) or len(ctx.portfolio_rows or []))
    cutoff = ctx.cfg.scoring.score_cutoff
    checklist = ctx.checklist

    stages: list[PipelineStage] = []

    # 1) Quant snapshot / alpha_scores
    if scores_src is None or not scores_src.exists:
        stages.append(
            PipelineStage(
                key="quant",
                step=1,
                title="정량 스냅샷",
                status="locked",
                reason="alpha_scores.csv가 없습니다. 정량 스냅샷을 먼저 돌리세요.",
                cta_label="데이터 갱신으로",
                page=PAGE_APPROVAL,
                focus=FOCUS_DATA_REFRESH,
                blocks_next=True,
            )
        )
    elif scores_src.stale:
        stages.append(
            PipelineStage(
                key="quant",
                step=1,
                title="정량 스냅샷",
                status="warn",
                reason=(
                    f"alpha_scores 갱신 필요 (as_of {scores_src.as_of or '—'}). "
                    "제안 북이 옛 점수일 수 있습니다."
                ),
                cta_label="데이터 상태·갱신",
                page=PAGE_APPROVAL,
                focus=FOCUS_DATA_REFRESH,
                blocks_next=False,
            )
        )
    else:
        stages.append(
            PipelineStage(
                key="quant",
                step=1,
                title="정량 스냅샷",
                status="ok",
                reason=f"alpha_scores 정상 (as_of {scores_src.as_of or '파일 기준'})",
                cta_label="스코어 보기",
                page=PAGE_APPROVAL,
                focus=FOCUS_SCORES,
                blocks_next=False,
            )
        )

    # CECS stage removed — REAL_INVEST_SCOPE_CHECKLIST (스킵 기본 · 순위 무관)

    # 2) Cutoff + eligibility alignment
    if cutoff is None:
        stages.append(
            PipelineStage(
                key="cutoff",
                step=2,
                title="컷오프 확정",
                status="locked",
                reason="score_cutoff이 비어 있어 eligibility를 판정할 수 없습니다.",
                cta_label="컷오프 확정",
                page=PAGE_PORTFOLIO,
                focus=FOCUS_CUTOFF,
                blocks_next=True,
            )
        )
    elif eligible_n == 0:
        stages.append(
            PipelineStage(
                key="cutoff",
                step=2,
                title="컷오프 정합",
                status="warn",
                reason=(
                    f"cutoff={cutoff:g} 인데 적격 0종입니다. "
                    "alpha_scores 총점대와 맞지 않으면 포트폴리오에서 재확정하세요."
                ),
                cta_label="컷오프 재확정",
                page=PAGE_PORTFOLIO,
                focus=FOCUS_CUTOFF,
                blocks_next=True,
            )
        )
    else:
        stages.append(
            PipelineStage(
                key="cutoff",
                step=2,
                title="컷오프 정합",
                status="ok",
                reason=f"cutoff={cutoff:g} · 적격 {eligible_n}종",
                cta_label="스코어 확인",
                page=PAGE_APPROVAL,
                focus=FOCUS_SCORES,
                blocks_next=False,
            )
        )

    # 4) Proposal book
    if proposal_n <= 0:
        prior_block = next((s for s in stages if s.blocks_next), None)
        stages.append(
            PipelineStage(
                key="proposal",
                step=3,
                title="제안 북",
                status="locked",
                reason=(
                    "스크린 제안 종목이 0입니다. "
                    + (
                        f"선행 과제: {prior_block.title}."
                        if prior_block
                        else "eligibility·sizing을 확인하세요."
                    )
                ),
                cta_label=(
                    prior_block.cta_label if prior_block else "스코어로"
                ),
                page=prior_block.page if prior_block else PAGE_APPROVAL,
                focus=prior_block.focus if prior_block else None,
                prefill=prior_block.prefill if prior_block else None,
                blocks_next=True,
            )
        )
    else:
        target_n = int(ctx.cfg.sizing.target_names)
        stages.append(
            PipelineStage(
                key="proposal",
                step=3,
                title="제안 북",
                status="ok" if proposal_n >= target_n else "warn",
                reason=f"proposal_book {proposal_n}종 (목표 {target_n})",
                cta_label="제안 북 보기",
                page=PAGE_PORTFOLIO,
                blocks_next=False,
            )
        )

    # 4) Go-live / checklist
    if ctx.pre_launch:
        blocking = list(checklist.blocking) if checklist is not None else []
        if blocking:
            first = blocking[0]
            page, focus = _checklist_nav(first.key)
            stages.append(
                PipelineStage(
                    key="golive",
                    step=4,
                    title="가동 선언",
                    status="locked",
                    reason=f"{first.title} — {first.why} (할 일: {first.todo})",
                    cta_label="이 항목 해결",
                    page=page,
                    focus=focus,
                    blocks_next=True,
                )
            )
        else:
            stages.append(
                PipelineStage(
                    key="golive",
                    step=4,
                    title="가동 선언",
                    status="warn",
                    reason="체크리스트는 충족. go-live를 선언하면 트랜치가 열립니다.",
                    cta_label="가동 선언으로",
                    page=PAGE_APPROVAL,
                    focus=FOCUS_GO_LIVE,
                    blocks_next=True,
                )
            )
    else:
        stages.append(
            PipelineStage(
                key="golive",
                step=4,
                title="가동 선언",
                status="ok",
                reason=f"가동 중 (go_live={ctx.effective_go_live})",
                cta_label="이벤트",
                page=PAGE_APPROVAL,
                focus=FOCUS_GO_LIVE,
                blocks_next=False,
            )
        )

    # 5) Proposal book ready (ops_book UI removed — exit cues live on proposal)
    prop_n = int(getattr(ctx, "proposal_count", 0) or 0)
    if prop_n <= 0:
        stages.append(
            PipelineStage(
                key="proposal_ops",
                step=5,
                title="제안 북",
                status="locked",
                reason="제안 북이 비어 있습니다. 컷오프·스코어를 확인하세요.",
                cta_label="포트폴리오",
                page=PAGE_PORTFOLIO,
                blocks_next=False,
            )
        )
    else:
        stages.append(
            PipelineStage(
                key="proposal_ops",
                step=5,
                title="제안 북",
                status="ok",
                reason=f"proposal_book {prop_n}종 · 익절 신호 표시 · target 자동변경 없음",
                cta_label="제안 북 보기",
                page=PAGE_PORTFOLIO,
                blocks_next=False,
            )
        )

    return stages


def first_blocker(stages: Sequence[PipelineStage]) -> Optional[PipelineStage]:
    for stage in stages:
        if stage.status in {"locked", "warn"} and stage.blocks_next:
            return stage
    for stage in stages:
        if stage.status in {"locked", "warn"}:
            return stage
    return None


def stale_sources_summary(sources: Sequence[SourceStatus]) -> list[SourceStatus]:
    return [s for s in sources if s.stale]


def _checklist_nav(key: str) -> tuple[str, Optional[str]]:
    if key == "score_cutoff":
        return PAGE_PORTFOLIO, FOCUS_CUTOFF
    if key == "t3_history":
        return PAGE_APPROVAL, FOCUS_T3_DETAIL
    return PAGE_APPROVAL, FOCUS_GO_LIVE
