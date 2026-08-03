"""이벤트/갱신 렌더 헬퍼 — 화면 진입점은 approval.render_approval."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from alpha_system.journal import append_record
from alpha_system.ui.services.auto_journal import journal_data_refresh, journal_go_live_blocked
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.go_live_gate import block_go_live_reasons
from alpha_system.ui.services.refresh import run_quant_snapshot_refresh
from alpha_system.ui.services.runtime_state import RuntimeState
from alpha_system.ui.services.ui_copy import copy_get


def _render_weekly_qual(
    ctx: DashboardContext,
    *,
    focused: bool = False,
    prefer_approve: bool = False,
) -> None:
    """One collection surface and one compact domain approval board."""
    from datetime import date as _date

    import pandas as pd

    from alpha_system.ui.services.weekly_domain_gates import (
        approve_domain,
        mark_sources_reviewed,
    )
    from alpha_system.ui.services.weekly_qual_report import (
        SUGGESTIONS_LANE_WEEKLY,
        WEEKLY_DOMAIN_KEYS,
        load_cde_copy_prompt,
        load_exit_target_entries,
        load_weekly_suggestions,
        parse_weekly_qual_markdown,
        persist_targets_supplement,
        persist_weekly_suggestions,
        subjects_from_cecs_df,
        subjects_from_portfolio_rows,
        waiting_target_subjects,
        write_targets_supplement_report,
        write_weekly_qual_report,
    )

    st.subheader("공적 브레이크 · T2·논지·목표가 (선택)")
    st.caption(
        "선택 오버레이: T2 · 논지 · 목표가(E·실측 앵커만). "
        "홈「다음 할 일」을 잠그지 않습니다. 증권사 목표가 SoT 승인 거부. "
        "월간 CECS는 접힌 원장(스킵 기본 · 순위 무관). "
        "요청서 생성만으로 kr_alpha_exit_targets.yaml은 삭제되지 않습니다. "
        "target_portfolio.csv 자동 변경 없음."
    )
    if focused:
        st.info("홈의 「지금 할 일」에서 연결되었습니다.")

    cecs_path = ctx.root / "data" / "cecs_manual_scoring_template.csv"
    cecs_df = pd.read_csv(cecs_path, dtype=str) if cecs_path.exists() else pd.DataFrame()
    summary = subjects_from_cecs_df(cecs_df, limit=30)
    # B/E = full current proposal_book (final selection 5~8). Do not truncate
    # to target_names — that drops names and causes 목표가 승인 거부.
    deep = subjects_from_portfolio_rows(ctx.portfolio_rows)
    proposal_tickers = [s.ticker for s in deep if s.ticker]
    waiting = waiting_target_subjects(ctx.portfolio_rows, root=ctx.root)

    payload = load_weekly_suggestions(ctx.root, SUGGESTIONS_LANE_WEEKLY)
    approved_map = dict((payload or {}).get("approved") or {})
    domain_statuses = dict((payload or {}).get("domain_status") or {})
    required_domains = WEEKLY_DOMAIN_KEYS
    required_pending = sum(
        1
        for key in required_domains
        if domain_statuses.get(key) == "ai_suggested"
        and not approved_map.get(key, False)
    )
    board_on_top = bool(prefer_approve and payload and required_pending > 0)

    def _render_approval_board() -> None:
        if not payload:
            return
        st.markdown("#### 공적 브레이크 승인판 (선택)")
        st.caption(
            "T2·논지·목표가(실측) · CECS 스킵 · 증권사 SoT 거부 · "
            "영역별 단독 승인 · target_portfolio.csv 불변"
        )
        approver = st.text_input(
            "공통 승인자",
            value="operator",
            key="weekly_approver",
        )
        st.markdown("##### 선택 영역")
        st.caption(f"승인 남음 {required_pending}영역 · T2 · 논지 · 목표가(E)")
        if required_pending == 0 and any(approved_map.get(k) for k in required_domains):
            st.success(
                "선택 영역 승인 완료. 펼치면 승인 당시 보고서를 다시 볼 수 있습니다."
            )
        for domain in required_domains:
            _render_domain_approval_card(
                ctx,
                payload,
                domain=domain,
                approved_map=approved_map,
                pending_n=required_pending,
                approver=approver,
            )

    if board_on_top:
        _render_approval_board()
        st.divider()

    _WQ_COLLECT = "요청서 생성·다운로드"
    _WQ_UPLOAD = "완성본 업로드"
    _WQ_SUPP = "목표가 대기 보충"
    _WQ_TABS = (_WQ_COLLECT, _WQ_UPLOAD, _WQ_SUPP)
    _WQ_KEY = "weekly_qual_workflow_tab"

    st.markdown(
        '<div class="ap-tab-label">정성 워크플로</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get(_WQ_KEY) not in _WQ_TABS:
        st.session_state[_WQ_KEY] = _WQ_COLLECT
    wq_step = st.segmented_control(
        "정성 워크플로",
        list(_WQ_TABS),
        selection_mode="single",
        required=True,
        label_visibility="collapsed",
        key=_WQ_KEY,
        width="stretch",
    )
    if wq_step is None:
        wq_step = _WQ_COLLECT

    if wq_step == _WQ_COLLECT:
        st.markdown(
            """
<div class="ap-panel">
  <div class="ap-panel-kicker">Step 1</div>
          <div class="ap-panel-title">요청서 생성·다운로드</div>
  <p class="ap-panel-desc">C T2 · D 논지 · E 목표가 (+B 심층). CECS는 스킵 기본(접힌 원장). 요청서 생성만으로 기존 PBR/목표가 YAML은 지워지지 않습니다.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        can_gen = bool(deep)
        if not can_gen:
            st.error(
                "proposal_book(최종 선정)이 비어 B/E를 만들 수 없습니다. "
                "정량·컷오프·eligibility·섹터 캡을 먼저 확인하세요."
            )
        if st.button(
            "이번 주 요청서 생성",
            type="primary",
            key="btn_weekly_qual_gen",
            use_container_width=True,
            disabled=not can_gen,
        ):
            report = write_weekly_qual_report(
                summary_subjects=summary,
                deep_subjects=deep,
                t2_event_ids=list(ctx.cfg.tranches["T2"].event_ids),
                docs_dir=ctx.root / "docs",
                as_of=ctx.as_of,
                input_paths=[
                    ctx.root
                    / "alpha_portfolio"
                    / "data"
                    / "output"
                    / "alpha_scores.csv",
                    cecs_path,
                    ctx.root / "data" / "fundamentals.csv",
                ],
                existing_exit=load_exit_target_entries(ctx.root),
            )
            quant_run_id = None
            scores_sha = None
            prov_path = ctx.root / "data" / "alpha_quant_snapshot_provenance.json"
            if prov_path.exists():
                try:
                    import json

                    prov = json.loads(prov_path.read_text(encoding="utf-8"))
                    quant_run_id = prov.get("run_id")
                    scores_sha = prov.get("scores_sha256")
                except (OSError, ValueError, TypeError):
                    pass
            from alpha_system.ui.services.proposal_freeze import (
                activate_freeze,
                freeze_feature_enabled,
            )

            fr = activate_freeze(
                ctx.root,
                report_id=report.report_id,
                as_of=ctx.as_of,
                proposal_tickers=[s.ticker for s in deep],
                proposal_names={s.ticker: s.name for s in deep},
                quant_run_id=quant_run_id,
                scores_sha256=scores_sha,
            )
            st.session_state["weekly_qual_md"] = report.markdown
            st.session_state["weekly_qual_path"] = str(report.path)
            st.session_state["weekly_qual_deep_tickers"] = list(proposal_tickers)
            if freeze_feature_enabled(ctx.root) and fr.active:
                st.success(
                    f"생성됨: {report.path.name} · 제안 스냅샷 고정 "
                    f"({len(deep)}종 · 선택 브레이크 승인 시 해제)"
                )
            else:
                st.success(
                    f"생성됨: {report.path.name} · 정량 잠금 없음 "
                    f"(정책 off · {len(deep)}종 기록만)"
                )

        md = st.session_state.get("weekly_qual_md")
        path = st.session_state.get("weekly_qual_path")
        if md:
            st.download_button(
                "요청서 다운로드",
                data=md,
                file_name=Path(path).name if path else "weekly_qual_report.md",
                mime="text/markdown",
                key="weekly_qual_dl",
                use_container_width=True,
            )
        _render_claude_prompt_panel(
            ctx.root,
            which="A",
            title="클로드용 프롬프트 A (주간 C·D·E · 클릭해 복사)",
            caption=(
                "「프롬프트 A 텍스트 복사」를 누른 뒤 클로드에 붙여넣고, "
                "이어서 주간 요청서 Markdown을 붙이세요."
            ),
            key_prefix="weekly_qual_prompt_a",
            expanded=bool(md),
        )

    elif wq_step == _WQ_UPLOAD:
        st.markdown(
            """
<div class="ap-panel">
  <div class="ap-panel-kicker">Step 2</div>
  <div class="ap-panel-title">완성본 업로드</div>
  <p class="ap-panel-desc">AI 작성 Markdown을 올리면 영역별로 분리·검수 대기 상태가 됩니다.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "AI 작성 완료 Markdown",
            type=["md", "markdown", "txt"],
            key="weekly_qual_upload",
        )
        if uploaded is not None and st.button(
            "업로드·영역 분리",
            type="primary",
            key="weekly_qual_parse",
            use_container_width=True,
        ):
            text = uploaded.getvalue().decode("utf-8-sig")
            parsed = parse_weekly_qual_markdown(text)
            locked = st.session_state.get("weekly_qual_deep_tickers") or proposal_tickers
            out = persist_weekly_suggestions(
                root=ctx.root,
                parsed=parsed,
                report_name=uploaded.name,
                as_of=ctx.as_of or _date.today(),
                locked_deep_tickers=list(locked) if locked else None,
                lane=SUGGESTIONS_LANE_WEEKLY,
            )
            st.success(
                "업로드 완료(주간 C/D/E): "
                + ", ".join(
                    f"{k}={parsed.domain_status.get(k)}" for k in WEEKLY_DOMAIN_KEYS
                )
                + f" → `{out.name}`"
            )
            for domain, failures in parsed.domain_failures.items():
                if failures:
                    st.warning(f"{domain}: " + "; ".join(failures[:5]))
            st.rerun()

    else:
        st.markdown(
            """
<div class="ap-panel">
  <div class="ap-panel-kicker">Step 3</div>
  <div class="ap-panel-title">목표가 대기 보충</div>
  <p class="ap-panel-desc">제안 북 중 목표가 없는 종목만 E 전용. 실측 앵커(BPS·trailing PBR·52주) 우선 · 증권사 목표가는 참고만 · 이미 YAML에 있는 값은 유지 · target_portfolio.csv 불변.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if not proposal_tickers:
            st.error("proposal_book이 비어 대기 보충을 만들 수 없습니다.")
        elif not waiting:
            st.success("대기 후보 없음 — 제안 북 전 종목에 목표가 승인값이 있습니다.")
        else:
            st.info(
                "대기 "
                + str(len(waiting))
                + "종: "
                + ", ".join(f"{s.ticker} {s.name}" for s in waiting)
            )
            if st.button(
                "목표가 대기 보충 요청서 생성",
                type="primary",
                key="btn_targets_supp_gen",
                use_container_width=True,
            ):
                report = write_targets_supplement_report(
                    waiting_subjects=waiting,
                    proposal_tickers=proposal_tickers,
                    docs_dir=ctx.root / "docs",
                    as_of=ctx.as_of,
                )
                st.session_state["targets_supp_md"] = report.markdown
                st.session_state["targets_supp_path"] = str(report.path)
                st.session_state["targets_supp_waiting"] = [s.ticker for s in waiting]
                st.session_state["weekly_qual_deep_tickers"] = list(proposal_tickers)
                st.success(f"생성됨: {report.path.name}")

            supp_md = st.session_state.get("targets_supp_md")
            supp_path = st.session_state.get("targets_supp_path")
            if supp_md:
                st.download_button(
                    "보충 요청서 다운로드",
                    data=supp_md,
                    file_name=(
                        Path(supp_path).name
                        if supp_path
                        else "weekly_qual_targets_supplement.md"
                    ),
                    mime="text/markdown",
                    key="targets_supp_dl",
                    use_container_width=True,
                )

            prompt_b = load_cde_copy_prompt(ctx.root, which="B")
            _render_claude_prompt_panel(
                ctx.root,
                which="B",
                title="클로드용 프롬프트 B (목표가 보충 · 클릭해 복사)",
                caption=(
                    "「프롬프트 B 텍스트 복사」를 누른 뒤 클로드에 붙여넣고, "
                    "이어서 보충 요청서 Markdown을 붙이세요."
                ),
                key_prefix="targets_supp_prompt_b",
                expanded=True,
                prompt_text=prompt_b,
            )
            with st.expander("사용 순서", expanded=False):
                st.markdown(
                    "1. **보충 요청서 생성** → 다운로드  \n"
                    "2. **프롬프트 B 텍스트 복사** (원클릭)  \n"
                    "3. 클로드에 프롬프트 붙여넣기 → 요청서 전체 이어서 붙이기  \n"
                    "4. 완성 Markdown을 받아 아래 **업로드·목표가만 병합**  \n"
                    "5. 승인판에서 **targets** 출처 확인·승인"
                )

            supp_up = st.file_uploader(
                "목표가 보충 완성본 Markdown",
                type=["md", "markdown", "txt"],
                key="targets_supp_upload",
            )
            if supp_up is not None and st.button(
                "업로드·목표가만 병합",
                type="primary",
                key="targets_supp_parse",
                use_container_width=True,
            ):
                text = supp_up.getvalue().decode("utf-8-sig")
                parsed = parse_weekly_qual_markdown(text)
                wait_keys = st.session_state.get("targets_supp_waiting") or [
                    s.ticker for s in waiting
                ]
                try:
                    out = persist_targets_supplement(
                        root=ctx.root,
                        parsed=parsed,
                        report_name=supp_up.name,
                        as_of=ctx.as_of or _date.today(),
                        proposal_tickers=proposal_tickers,
                        waiting_tickers=wait_keys,
                    )
                    st.success(
                        f"목표가 보충 병합 완료 → `{out.name}` · "
                        f"targets={parsed.domain_status.get('targets')}"
                    )
                    for failure in (parsed.domain_failures or {}).get("targets") or []:
                        st.warning(failure)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if payload and not board_on_top:
        _render_approval_board()


def _render_monthly_cecs(
    ctx: DashboardContext,
    *,
    focused: bool = False,
) -> None:
    """월간 CECS 전용 수집·승인 — weekly C/D/E JSON을 덮어쓰지 않음."""
    from datetime import date as _date

    import pandas as pd

    from alpha_system.ui.services.weekly_qual_report import (
        MONTHLY_DOMAIN_KEYS,
        SUGGESTIONS_LANE_MONTHLY,
        load_weekly_suggestions,
        parse_weekly_qual_markdown,
        persist_weekly_suggestions,
        subjects_from_cecs_df,
        write_monthly_cecs_report,
    )

    st.subheader("월간 CECS 수집·승인 (선택 원장)")
    st.caption(
        "저장: monthly_cecs_suggestions.json · 주간 C/D/E와 분리 · "
        "**순위·편입 미반영(Ops A)** · 원장 기록만 · 환원 순위는 score_sr SR4 · "
        "AI는 execution만 · target_portfolio 불변"
    )
    if focused:
        st.info(
            "월간 CECS 원장(스킵 기본)입니다. "
            "승인해도 제안 종목·순위는 바뀌지 않습니다."
        )

    cecs_path = ctx.root / "data" / "cecs_manual_scoring_template.csv"
    cecs_df = pd.read_csv(cecs_path, dtype=str) if cecs_path.exists() else pd.DataFrame()
    summary = subjects_from_cecs_df(cecs_df, limit=30)

    _MQ_COLLECT = "요청서 생성"
    _MQ_UPLOAD = "완성본 업로드"
    _MQ_TABS = (_MQ_COLLECT, _MQ_UPLOAD)
    _MQ_KEY = "monthly_cecs_workflow_tab"
    if st.session_state.get(_MQ_KEY) not in _MQ_TABS:
        st.session_state[_MQ_KEY] = _MQ_COLLECT
    mq_step = st.segmented_control(
        "월간 CECS 워크플로",
        list(_MQ_TABS),
        selection_mode="single",
        required=True,
        label_visibility="collapsed",
        key=_MQ_KEY,
        width="stretch",
    )
    if mq_step is None:
        mq_step = _MQ_COLLECT

    if mq_step == _MQ_COLLECT:
        if not summary:
            st.warning("cecs_manual_scoring_template.csv가 비어 있습니다.")
        if st.button(
            "월간 CECS 요청서 생성",
            type="primary",
            key="btn_monthly_cecs_gen",
            use_container_width=True,
            disabled=not summary,
        ):
            report = write_monthly_cecs_report(
                summary_subjects=summary,
                docs_dir=ctx.root / "docs",
                as_of=ctx.as_of,
                input_paths=[
                    ctx.root
                    / "alpha_portfolio"
                    / "data"
                    / "output"
                    / "alpha_scores.csv",
                    cecs_path,
                ],
            )
            st.session_state["monthly_cecs_md"] = report.markdown
            st.session_state["monthly_cecs_path"] = str(report.path)
            st.success(f"생성됨: {report.path.name} (execution만 · 순위 무관)")
        md = st.session_state.get("monthly_cecs_md")
        path = st.session_state.get("monthly_cecs_path")
        if md:
            st.download_button(
                "월간 요청서 다운로드",
                data=md,
                file_name=Path(path).name if path else "monthly_cecs_report.md",
                mime="text/markdown",
                key="monthly_cecs_dl",
                use_container_width=True,
            )
        _render_claude_prompt_panel(
            ctx.root,
            which="C",
            title="클로드용 프롬프트 C (월간 CECS 원장 · execution만)",
            caption=(
                "「프롬프트 C 텍스트 복사」후 클로드에 붙여넣고 월간 요청서를 붙이세요. "
                "execution만 채움 · pension/purpose 유지 · 순위·편입 무관."
            ),
            key_prefix="monthly_cecs_prompt_c",
            expanded=bool(md),
        )
    else:
        uploaded = st.file_uploader(
            "월간 CECS Markdown",
            type=["md", "markdown", "txt"],
            key="monthly_cecs_upload",
        )
        if uploaded is not None and st.button(
            "업로드·CECS 분리",
            type="primary",
            key="monthly_cecs_parse",
            use_container_width=True,
        ):
            text = uploaded.getvalue().decode("utf-8-sig")
            parsed = parse_weekly_qual_markdown(text)
            out = persist_weekly_suggestions(
                root=ctx.root,
                parsed=parsed,
                report_name=uploaded.name,
                as_of=ctx.as_of or _date.today(),
                lane=SUGGESTIONS_LANE_MONTHLY,
            )
            st.success(
                f"월간 업로드 완료: cecs={parsed.domain_status.get('cecs')} → `{out.name}`"
            )
            for failure in (parsed.domain_failures or {}).get("cecs") or []:
                st.warning(failure)
            st.rerun()

    payload = load_weekly_suggestions(ctx.root, SUGGESTIONS_LANE_MONTHLY)
    if not payload:
        return

    approved_map = dict(payload.get("approved") or {})
    domain_statuses = dict(payload.get("domain_status") or {})
    pending = sum(
        1
        for key in MONTHLY_DOMAIN_KEYS
        if domain_statuses.get(key) == "ai_suggested"
        and not approved_map.get(key, False)
    )
    st.markdown("#### 월간 CECS 승인판")
    st.caption(f"남은 제안 {pending} · 순위 미반영 · 주간 파일 불변")
    approver = st.text_input(
        "월간 승인자",
        value="operator",
        key="monthly_cecs_approver",
    )
    for domain in MONTHLY_DOMAIN_KEYS:
        _render_domain_approval_card(
            ctx,
            payload,
            domain=domain,
            approved_map=approved_map,
            pending_n=pending,
            approver=approver,
            optional=True,
        )


def _clipboard_copy_button(text: str, *, label: str, key: str) -> None:
    """Browser clipboard copy — paste into Claude in one click."""
    import html
    import json

    import streamlit.components.v1 as components

    safe_label = html.escape(label)
    payload = json.dumps(text, ensure_ascii=False)
    btn_id = f"copy_btn_{html.escape(key, quote=True)}"
    components.html(
        f"""
<div style="width:100%;">
  <button id="{btn_id}" style="
    width:100%;
    padding:0.55rem 0.75rem;
    border:1px solid #4a5568;
    border-radius:0.4rem;
    background:#1a2332;
    color:#e8eef7;
    font-size:0.95rem;
    cursor:pointer;
  ">{safe_label}</button>
</div>
<script>
(() => {{
  const btn = document.getElementById("{btn_id}");
  if (!btn) return;
  const text = {payload};
  const original = btn.innerText;
  btn.addEventListener("click", async () => {{
    try {{
      await navigator.clipboard.writeText(text);
      btn.innerText = "복사됨 — 클로드에 붙여넣으세요";
      setTimeout(() => {{ btn.innerText = original; }}, 2000);
    }} catch (err) {{
      btn.innerText = "복사 실패 — 미리보기에서 직접 복사";
      setTimeout(() => {{ btn.innerText = original; }}, 2500);
    }}
  }});
}})();
</script>
""",
        height=52,
    )


def _render_claude_prompt_panel(
    root,
    *,
    which: str,
    title: str,
    caption: str,
    key_prefix: str,
    expanded: bool = False,
    prompt_text: str | None = None,
) -> None:
    """Shared one-click Claude prompt copy UI (A / B / C)."""
    from alpha_system.ui.services.weekly_qual_report import load_cde_copy_prompt

    letter = str(which or "A").strip().upper()
    text = prompt_text if prompt_text is not None else load_cde_copy_prompt(root, which=letter)
    if not text:
        return
    with st.expander(title, expanded=expanded):
        st.caption(caption)
        _clipboard_copy_button(
            text,
            label=f"프롬프트 {letter} 텍스트 복사",
            key=f"{key_prefix}_copy",
        )
        st.download_button(
            f"프롬프트 {letter} 텍스트 다운로드",
            data=text,
            file_name=f"weekly_qual_prompt_{letter}.txt",
            mime="text/plain",
            key=f"{key_prefix}_dl",
            use_container_width=True,
        )
        with st.expander("프롬프트 미리보기", expanded=False):
            st.code(text, language="text")


def _render_domain_approval_card(
    ctx: DashboardContext,
    payload: dict,
    *,
    domain: str,
    approved_map: dict,
    pending_n: int,
    approver: str,
    optional: bool = False,
) -> None:
    from datetime import date as _date

    from alpha_system.ui.services.weekly_domain_gates import (
        approve_domain,
        mark_sources_reviewed,
    )

    status = (payload.get("domain_status") or {}).get(domain, "—")
    approved = bool(approved_map.get(domain))
    domain_label = {
        "cecs": "CECS (선택)",
        "t2": "T2 이벤트",
        "thesis": "논지",
        "targets": "목표가",
    }.get(domain, domain)
    if optional and not approved:
        suffix = f" — {status} · 순위 미반영"
    else:
        suffix = " — 승인 완료 · 펼치면 보고서 재확인" if approved else f" — {status}"
    with st.expander(
        f"{domain_label}{suffix}",
        expanded=(not approved and not optional and pending_n <= 2),
    ):
        if optional:
            st.info(
                "Ops A: CECS는 **선택 원장**입니다. 승인해도 proposal 순위·편입이 바뀌지 않습니다. "
                "환원 연속성 순위는 정량 score_sr(SR4). pension/purpose 잠정 50은 순위 무관."
            )
        if approved:
            meta = (payload.get("approved_meta") or {}).get(domain) or {}
            by = meta.get("approved_by") or "—"
            as_of_meta = meta.get("as_of") or payload.get("as_of") or "—"
            skipped = bool((meta.get("applied") or {}).get("skipped")) if isinstance(meta.get("applied"), dict) else False
            if skipped or status == "not_applicable":
                st.success(
                    f"목표가 게이트 충족(대기 없음) · system · as_of {as_of_meta} — "
                    "제안 북 YAML 승인값 유지 · target_portfolio 불변"
                )
            else:
                st.success(f"승인·적용 완료 · 승인자 `{by}` · as_of {as_of_meta}")
            st.caption("아래는 승인 당시 보고서입니다. 조회만 가능하며 재승인 버튼은 없습니다.")
            _render_domain_report(payload, domain)
            return
        if status == "not_applicable":
            st.success(
                "대기 목표가 없습니다. 제안 북 전 종목이 이미 YAML에 승인되어 "
                "이번 주 목표가 게이트는 자동 충족입니다."
            )
            return
        if status != "ai_suggested":
            notes = (payload.get("domain_notes") or {}).get(domain) or []
            if domain == "targets" and status == "empty" and not (
                (payload.get("domain_failures") or {}).get(domain) or []
            ):
                st.success(
                    "대기 목표가 없습니다(이미 YAML 승인). "
                    "페이지를 새로고침하거나 완성본을 다시 업로드하면 게이트가 자동 충족됩니다."
                )
                if notes:
                    for note in notes:
                        st.caption(f"• {note}")
                return
            st.warning(
                "이 영역은 승인 가능한 제안이 없습니다. "
                "파싱 실패 내용을 보완해 완성본을 다시 업로드하세요."
            )
            failures = (payload.get("domain_failures") or {}).get(domain) or []
            if failures:
                with st.expander(f"파싱 실패 {len(failures)}건", expanded=False):
                    for failure in failures:
                        st.caption(f"• {failure}")
            if notes:
                with st.expander("참고", expanded=False):
                    for note in notes:
                        st.caption(f"• {note}")
            return
        keys = _domain_review_keys(payload, domain)
        _render_domain_report(payload, domain)
        source_confirmed = st.checkbox(
            f"위 {domain_label} 보고서 내용과 출처 원문을 모두 확인했습니다",
            key=f"weekly_source_confirm_{domain}",
        )
        confirm = 0
        if domain == "t2":
            st.warning("승인하면 T2 이벤트 기록이 생성됩니다.")
            c1 = st.checkbox("이벤트 기록 영향을 이해했습니다", key="weekly_t2_c1")
            c2 = st.checkbox("T2 적용을 최종 확인합니다", key="weekly_t2_c2")
            confirm = int(c1) + int(c2)
        elif domain == "thesis":
            st.error("damage=true 승인 시 미집행 트랜치 동결 판단에 반영됩니다.")
            c1 = st.checkbox("동결 가능성을 이해했습니다", key="weekly_th_c1")
            c2 = st.checkbox("논지 근거를 재확인했습니다", key="weekly_th_c2")
            c3 = st.checkbox("논지 적용을 최종 확인합니다", key="weekly_th_c3")
            confirm = int(c1) + int(c2) + int(c3)
        elif domain == "targets":
            st.info(
                "승인해도 target_portfolio.csv는 변경하지 않습니다. "
                "익절 장부(YAML)만 갱신 · 실측 앵커 우선(증권사 목표가≠자동 SoT)."
            )

        if st.button(
            f"{domain_label}만 승인",
            key=f"weekly_approve_{domain}",
            disabled=not source_confirmed,
            use_container_width=True,
        ):
            try:
                mark_sources_reviewed(root=ctx.root, domain=domain, keys=keys)
                approve_domain(
                    root=ctx.root,
                    domain=domain,
                    approved_by=approver,
                    as_of=ctx.as_of or _date.today(),
                    reviewed_keys=keys,
                    confirm_steps=confirm,
                )
                st.success(f"{domain_label} 승인 완료")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_domain_report(payload: dict, domain: str) -> None:
    """Render parsed judgments and sources as a continuous approval report."""
    st.markdown("#### 결재 검토 보고서")
    st.caption(
        f"보고서 `{payload.get('report_name') or '—'}` · "
        f"기준일 {payload.get('as_of') or '—'} · "
        f"report_id `{payload.get('report_id') or '—'}`"
    )

    if domain == "cecs":
        items = payload.get("cecs") or []
        st.info(
            f"CECS {len(items)}종 · **선택 원장** · execution / pension / purpose 순서. "
            "Ops A: 순위·편입 미반영 · 환원 순위는 score_sr SR4. "
            "점수 50은 잠정 중립(pension/purpose 또는 미확인 execution)인 경우가 포함됩니다."
        )
        for index, item in enumerate(items, 1):
            ticker = str(item.get("ticker") or "")
            name = str(item.get("name") or ticker)
            with st.container(border=True):
                st.markdown(f"##### {index}. {name} (`{ticker}`)")
                score_cols = st.columns(3)
                for col, axis, label in zip(
                    score_cols,
                    ("execution", "pension", "purpose"),
                    ("실행·환원", "연기금", "투자목적"),
                ):
                    detail = item.get(axis) or {}
                    score = detail.get("score_100")
                    provisional = bool(detail.get("provisional"))
                    display = f"{score:g}" if isinstance(score, (int, float)) else "—"
                    if provisional and isinstance(score, (int, float)):
                        display = f"{score:g} · AI잠정"
                    col.metric(label, display)

                for axis, label in (
                    ("execution", "실행·환원"),
                    ("pension", "연기금"),
                    ("purpose", "투자목적"),
                ):
                    detail = item.get(axis) or {}
                    title = f"**{label} 판단**"
                    if detail.get("provisional"):
                        title += " · `AI 잠정값(빈 점수→50)` — 사람 확인 전 최종으로 쓰지 마세요"
                    st.markdown(title)
                    st.write(detail.get("rationale") or "내용 없음")
                    _render_sources(detail.get("sources") or [])

        deep = [
            item
            for item in (payload.get("deep_dives") or [])
            if any(
                str(item.get(key) or "").strip() not in {"", "_____", "확인 불가"}
                for key in (
                    "disclosure",
                    "buyback_dividend",
                    "pension",
                    "investment_purpose",
                    "risks",
                )
            )
        ]
        if deep:
            st.markdown("#### 최종 후보 심층 검토")
            for item in deep:
                with st.container(border=True):
                    st.markdown(
                        f"##### {item.get('name') or item.get('ticker')} "
                        f"(`{item.get('ticker') or '—'}`)"
                    )
                    for key, label in (
                        ("disclosure", "공시·지배구조"),
                        ("buyback_dividend", "자사주·배당·환원"),
                        ("pension", "연기금·수급"),
                        ("investment_purpose", "투자목적"),
                        ("risks", "리스크"),
                    ):
                        st.markdown(f"**{label}**")
                        st.write(item.get(key) or "내용 없음")
                    _render_sources(item.get("sources") or [])

    elif domain == "t2":
        items = payload.get("t2") or []
        for index, item in enumerate(items, 1):
            with st.container(border=True):
                st.markdown(
                    f"##### {index}. T2 이벤트 `{item.get('event_id') or '—'}`"
                )
                st.markdown(
                    f"- 발생 판단: **{'발생' if item.get('fired') else '미발생'}**"
                )
                st.markdown("**판단 근거**")
                st.write(item.get("rationale") or "내용 없음")
                _render_sources(item.get("sources") or [])

    elif domain == "thesis":
        item = payload.get("thesis") or {}
        with st.container(border=True):
            st.markdown(
                "##### 논지 훼손 판단: "
                + ("**훼손**" if item.get("damage") else "**훼손 없음**")
            )
            st.markdown("**판단 근거**")
            st.write(item.get("rationale") or "내용 없음")
            _render_sources(item.get("sources") or [])

    elif domain == "targets":
        items = payload.get("targets") or []
        st.info("이 보고서를 승인해도 `target_portfolio.csv`는 변경되지 않습니다.")
        for index, item in enumerate(items, 1):
            with st.container(border=True):
                st.markdown(
                    f"##### {index}. {item.get('name') or item.get('ticker')} "
                    f"(`{item.get('ticker') or '—'}`)"
                )
                cols = st.columns(2)
                cols[0].metric("PBR 상한", item.get("pbr_max") or "—")
                cols[1].metric("목표가", item.get("target_price") or "—")
                st.markdown("**펀더멘털 사유**")
                st.write(item.get("fundamental_reason") or "내용 없음")
                st.markdown("**판단 근거**")
                st.write(item.get("rationale") or "내용 없음")
                _render_sources(item.get("sources") or [])


def _render_sources(sources: list[str] | tuple[str, ...]) -> None:
    st.markdown("**출처**")
    if not sources:
        st.caption("• 출처 없음")
        return
    for index, source in enumerate(sources, 1):
        value = str(source).strip()
        if value.startswith(("http://", "https://")):
            st.markdown(f"- [출처 {index}]({value}) — `{value}`")
        elif value.startswith("[") and "](" in value:
            st.markdown(f"- {value}")
        else:
            st.caption(f"• {value or '출처 없음'}")


def _domain_review_keys(payload: dict, domain: str) -> list[str]:
    if domain == "cecs":
        return [str(x.get("ticker")) for x in payload.get("cecs") or [] if x.get("ticker")]
    if domain == "t2":
        fired = [
            str(x.get("event_id"))
            for x in payload.get("t2") or []
            if x.get("fired") and x.get("event_id")
        ]
        return fired or ["t2_none"]
    if domain == "thesis":
        return ["thesis"]
    if domain == "targets":
        return [str(x.get("ticker")) for x in payload.get("targets") or [] if x.get("ticker")]
    return []


def _render_t3_detail(ctx: DashboardContext) -> None:
    st.markdown("#### T3 PBR 이력·판정")
    pbr = ctx.t3_pbr
    if not pbr.available:
        st.markdown(
            '<div class="alpha-muted-note">'
            "이력 데이터 필요 — KOSPI 시장 PBR 10년 이력이 없어 저가 매수 조건을 "
            "판단할 수 없습니다. 아래 데이터 갱신·이력 적재를 확인하세요."
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption(pbr.source_note)
        return
    pct = pbr.percentile_10y
    history_detail = ""
    hist_path = ctx.root / "data" / "kospi_market_pbr_history.csv"
    if hist_path.exists():
        try:
            import pandas as pd

            history = pd.read_csv(hist_path)
            dates = pd.to_datetime(history.get("month_end"), errors="coerce").dropna()
            if not dates.empty:
                history_detail = (
                    f"- 이력: **{len(history)}개월** "
                    f"({dates.min().date().isoformat()} ~ {dates.max().date().isoformat()})\n"
                    f"- 파일: `{hist_path}`\n"
                )
        except Exception:
            history_detail = f"- 파일: `{hist_path}`\n"
    st.markdown(
        history_detail
        + f"- 최근 완료월 PBR: **{pbr.current_pbr if pbr.current_pbr is not None else '—'}**\n"
        f"- 10년 백분위: **{pct if pct is not None else '—'}%** "
        f"(하위 {pbr.bottom_pct}% 밴드)\n"
        f"- 밴드 진입: **{'예' if pbr.in_bottom_band else '아니오' if pbr.in_bottom_band is not None else '판정 불가'}**\n"
        f"- as_of: {pbr.as_of.isoformat() if pbr.as_of else '—'}\n"
        f"- 다음 판정: **매월 말**\n"
        f"- 소스: {pbr.source_note}"
    )


def _render_go_live(ctx: DashboardContext, *, expand: bool = False) -> None:
    st.markdown("#### Go-live 선언")
    if not ctx.pre_launch and ctx.effective_go_live is not None:
        st.info(
            copy_get(
                "go_live",
                "already_live",
                date=ctx.effective_go_live.isoformat(),
            )
        )
        return

    if ctx.checklist is not None:
        st.caption(f"체크리스트 {ctx.checklist.done}/{ctx.checklist.total}")
        for item in ctx.checklist.items:
            mark = "OK" if item.ok else "미충족"
            st.markdown(f"- **{mark}** {item.title}: {item.why} → {item.todo}")

    st.warning(copy_get("go_live", "warn"))
    c1 = st.checkbox(copy_get("go_live", "confirm_1"), key="gl_c1")
    c2 = st.checkbox(copy_get("go_live", "confirm_2"), key="gl_c2")
    live_date = st.date_input("가동 기준일", value=date.today(), key="gl_date")
    if st.button("go-live 선언", disabled=not (c1 and c2), key="gl_submit"):
        blocking = block_go_live_reasons(ctx.checklist) if ctx.checklist else []
        if blocking:
            msg = copy_get(
                "checklist",
                "go_live_blocked",
                items="; ".join(blocking),
            )
            journal_go_live_blocked(as_of=date.today(), items=blocking)
            st.error(msg)
            return
        iso = live_date.isoformat()
        append_record(
            action_kind="GO_LIVE_DECLARE",
            as_of=live_date,
            subject="*",
            rationale="operator go-live declaration",
            trigger_snapshot={"go_live_date": iso},
            payload={"go_live_date": iso},
        )
        runtime = RuntimeState.load(ctx.root / "data" / "alpha_dashboard_runtime.json")
        runtime.go_live_date = iso
        runtime.save(ctx.root / "data" / "alpha_dashboard_runtime.json")
        st.success(copy_get("go_live", "success", date=iso))
        st.rerun()


def _render_data_refresh(ctx: DashboardContext) -> None:
    st.caption(
        "정량 전체 갱신 한 번으로 운용 데이터와 alpha_scores를 함께 갱신합니다. "
        "이 PC에서 실행되며 수 분 걸릴 수 있습니다."
    )
    for src in ctx.source_status:
        rec = f"권장 {src.recommended_days}일" if src.recommended_days else "수동"
        st.text(f"• {src.label} — {src.path} ({rec})")
    hist = ctx.root / "data" / "kospi_market_pbr_history.csv"
    st.caption(f"T3 이력 CSV: {'있음' if hist.exists() else '없음'} — {hist}")
    if st.button(
        "정량 전체 갱신",
        type="primary",
        key="btn_quant_snapshot_refresh",
        use_container_width=True,
    ):
        with st.spinner("PyKRX·DART 수집과 alpha_scores 재계산 중…"):
            result = run_quant_snapshot_refresh(ctx.root, collect_scope="holdings")
        journal_data_refresh(
            as_of=date.today(),
            ok=result.ok,
            message=result.message,
            detail=result.detail,
        )
        if result.ok:
            ctx.runtime.touch_refresh("alpha_quant_snapshot")
            ctx.runtime.save(ctx.root / "data" / "alpha_dashboard_runtime.json")
            st.success(result.message)
            provenance = result.detail.get("provenance") or {}
            if provenance:
                st.caption(
                    f"run_id {provenance.get('run_id', '—')} · "
                    f"scored {provenance.get('scored_rows', '—')} · "
                    f"as_of {provenance.get('as_of', '—')}"
                )
            st.rerun()
        else:
            st.error(result.message)
            with st.expander("실패 상세"):
                st.json(result.detail)
