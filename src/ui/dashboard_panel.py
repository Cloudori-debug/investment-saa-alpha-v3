from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.alpha.target_draft_bridge import default_target_draft_path, is_target_draft_pending
from src.compass.profile_options import DEFAULT_PROFILE
from src.settings.user_secrets import credential_status
from src.ui.helpers import load_output_csv, load_output_json
from src.ui.nav_shortcuts import (
    SHORTCUT_ALPHA_TARGET,
    SHORTCUT_COMPASS,
    SHORTCUT_EXPORT_DETAIL,
    SHORTCUT_GAP,
    SHORTCUT_OPS,
    SHORTCUT_PORTFOLIO,
    SHORTCUT_SAA,
    SHORTCUT_SETTINGS_API,
    SHORTCUT_SETTINGS_DATA,
    ai_export_prereq_shortcuts,
    render_shortcut_row,
)
from src.ui.operating_card import render_operating_card
from src.runtime.run_mode import RunMode
from src.ui.pipeline_actions import run_ai_export, run_full_analysis
from src.ui.run_progress_panel import StreamlitRunProgress, render_run_summary
from src.ui.status_banner import render_operational_status
from src.ui.table_display import show_trade_actions_table
from src.ui.target_draft_workflow import render_target_draft_workflow

STATUS_ICON = {"done": "✅", "warn": "⚠️", "todo": "⬜", "fail": "❌"}


@dataclass
class StepState:
    key: str
    title: str
    status: str
    detail: str


def _step_anchor(step_key: str) -> None:
    st.markdown(
        f'<div id="dash-step-{step_key}" style="scroll-margin-top: 5.5rem;"></div>',
        unsafe_allow_html=True,
    )


def _step_expanded(step: StepState, *, default: bool) -> bool:
    focus = st.session_state.get("dash_focus_step")
    if focus:
        return step.key == focus
    return default


def _scroll_to_step(step_key: str) -> None:
    components.html(
        f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const el = doc.getElementById("dash-step-{step_key}");
            if (el) {{
                el.scrollIntoView({{ behavior: "smooth", block: "start" }});
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _render_progress(steps: list[StepState]) -> None:
    st.caption("단계를 누르면 해당 섹션으로 이동합니다.")
    cols = st.columns(len(steps))
    for col, step in zip(cols, steps, strict=True):
        short = step.title.split(" ", 1)[1]
        label = f"{STATUS_ICON.get(step.status, '⬜')} {short}"
        with col:
            if st.button(
                label,
                key=f"dash_nav_{step.key}",
                use_container_width=True,
                help=step.detail,
            ):
                st.session_state["dash_focus_step"] = step.key
                st.session_state["dash_scroll_pending"] = step.key
                st.rerun()


def _market_as_of(data_dir: Path) -> str | None:
    path = data_dir / "market_indicators.csv"
    if not path.exists():
        return None
    import pandas as pd

    df = pd.read_csv(path, dtype=str, nrows=1)
    if df.empty:
        return None
    return str(df.iloc[0].get("date", "")) or None


def _run_today(output_dir: Path) -> bool:
    manifest = load_output_json(output_dir, "run_manifest.json")
    if not manifest:
        return False
    gen = str(manifest.get("generated_at", ""))[:10]
    return gen == date.today().isoformat()


def _build_step_states(data_dir: Path, output_dir: Path) -> list[StepState]:
    cred = credential_status(data_dir)
    market = _market_as_of(data_dir)
    compass = load_output_json(output_dir, "compass_regime.json")
    trade = load_output_csv(output_dir, "trade_actions.csv")
    ac = load_output_json(output_dir, "acceptance_report.json")
    draft_path = default_target_draft_path()
    draft_pending = draft_path.exists() and is_target_draft_pending(data_dir, draft_path)

    data_status = "done" if market and (cred["dart"] or cred["krx"]) else "warn" if market else "todo"
    analysis_status = (
        "done" if _run_today(output_dir)
        else "warn" if (output_dir / "run_manifest.json").exists()
        else "todo"
    )
    compass_status = "done" if compass else "todo"
    gap_status = "done" if trade is not None and not trade.empty else "todo" if compass else "todo"
    ac_status = "done" if ac else "todo"
    draft_status = "warn" if draft_pending else "done"
    ai_status = (
        "done"
        if (output_dir / "ai_export_bundle.json").exists() and _run_today(output_dir)
        else "todo"
    )

    scope = ac.get("execution_scope", "—") if ac else "—"
    gate = compass.get("data_gate", "—") if compass else "—"

    return [
        StepState("prep", "① 데이터", data_status, f"시장 {market or '—'} · API"),
        StepState("run", "② 분석", analysis_status, "전체 파이프라인"),
        StepState("compass", "③ 나침반", compass_status, f"Gate {gate}"),
        StepState("gap", "④ Gap", gap_status, "trade_actions"),
        StepState("ac", "⑤ 승인", ac_status, f"Scope {scope}"),
        StepState("alpha", "⑥ 알파", draft_status, "target_draft" if draft_pending else "스킵 가능"),
        StepState("pos", "⑦ 보유", "todo", "positions"),
        StepState("ai", "⑧ AI검증", ai_status, "ZIP보내기"),
    ]


def render_dashboard_page(data_dir: Path, output_dir: Path) -> None:
    st.header("🏠 대시보드 — 일일 운용")
    cred = credential_status(data_dir)
    st.caption(
        f"①→⑧ 순서대로 · 자동화: `daily_pipeline` / 작업 스케줄러 · "
        f"DART {'✅' if cred['dart'] else '⬜'} · KRX {'✅' if cred['krx'] else '⬜'}"
    )

    render_operational_status(data_dir, output_dir)

    render_operating_card(output_dir)

    brief_path = output_dir / "executable_brief.md"
    if brief_path.exists():
        with st.expander("📋 Executable 상세 (executable_brief.md)", expanded=False):
            text = brief_path.read_text(encoding="utf-8")
            # 핵심 섹션만 미리보기 (너무 길면 앞부분)
            preview = text[:3500] + ("\n\n…" if len(text) > 3500 else "")
            st.markdown(preview)

    steps = _build_step_states(data_dir, output_dir)
    _render_progress(steps)
    st.divider()

    # --- Step 1 ---
    s1 = steps[0]
    _step_anchor(s1.key)
    with st.expander(
        f"{STATUS_ICON[s1.status]} {s1.title} — {s1.detail}",
        expanded=_step_expanded(s1, default=s1.status != "done"),
    ):
        render_shortcut_row([SHORTCUT_SETTINGS_DATA, SHORTCUT_SETTINGS_API], key_prefix="dash_s1", columns=2)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🌐 시장지표 갱신", key="dash_market_refresh", use_container_width=True):
                from src.data_refresh.market_indicators_refresh import refresh_all_market_indicators

                try:
                    mi = refresh_all_market_indicators(data_dir)
                    st.success(f"갱신 ({mi.as_of})")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with c2:
            st.caption(f"기준일: {_market_as_of(data_dir) or '없음'} (market_indicators.csv)")
            st.caption("② 「시장지표」 체크 후 전체 분석 시 자동 갱신")

    # --- Step 2 ---
    s2 = steps[1]
    _step_anchor(s2.key)
    with st.expander(
        f"{STATUS_ICON[s2.status]} {s2.title} — {s2.detail}",
        expanded=_step_expanded(s2, default=True),
    ):
        if st.session_state.pop("dash_prompt_reanalysis", False):
            st.info("target_draft 반영됨 — 아래 **▶ 전체 분석**을 실행하세요.")
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        auto_decompose = c2.checkbox("target 분해", value=True, key="dash_decompose")
        run_backtest = c3.checkbox("백테스트", value=False, key="dash_backtest")
        refresh_market = c4.checkbox("시장지표", value=True, key="dash_refresh_market")

        if st.session_state.get("dash_last_run_summary"):
            last = st.session_state["dash_last_run_summary"]
            with st.expander("📊 마지막 실행 결과", expanded=True):
                render_run_summary(
                    output_dir,
                    run_mode=str(last.get("run_mode", "")),
                    actual_buy_allowed=int(last.get("actual_buy_allowed") or 0),
                    advisory_note=str(last.get("advisory_note") or ""),
                    prof=last.get("runtime_profile") or {},
                )

        b1, b2, b3, b4 = st.columns(4)
        run_mode_used = RunMode.STANDARD.value
        analysis = None

        def _execute_run(mode: RunMode) -> None:
            nonlocal run_mode_used, analysis
            run_mode_used = mode.value
            progress = StreamlitRunProgress(mode.value)
            analysis = run_full_analysis(
                data_dir,
                output_dir,
                auto_decompose=auto_decompose,
                run_backtest=run_backtest,
                refresh_market=refresh_market if mode != RunMode.QUICK else False,
                run_mode=mode,
                progress=progress,
            )
            progress.render_summary(
                output_dir,
                actual_buy_allowed=analysis.actual_buy_allowed,
                advisory_note=analysis.advisory_note,
                prof=analysis.runtime_profile,
            )

        try:
            if b1.button("⚡ 빠른 점검", key="dash_run_quick", use_container_width=True):
                _execute_run(RunMode.QUICK)
            elif b2.button("▶ 전체 분석", type="primary", key="dash_run_analysis", use_container_width=True):
                _execute_run(RunMode.STANDARD)
            elif b3.button("🔬 주간 정밀", key="dash_run_deep", use_container_width=True):
                _execute_run(RunMode.DEEP)
            elif b4.button("📦 번들만", key="dash_run_bundle_only", use_container_width=True):
                _execute_run(RunMode.BUNDLE_ONLY)
        except Exception as exc:
            st.error(str(exc))
        else:
            if analysis is not None:
                st.session_state.pop("ai_export_zip", None)
                st.session_state.pop("ai_export_meta", None)
                st.session_state.pop("dash_ai_zip", None)
                st.session_state["dash_last_run_summary"] = {
                    "run_mode": run_mode_used,
                    "actual_buy_allowed": analysis.actual_buy_allowed,
                    "advisory_note": analysis.advisory_note,
                    "runtime_profile": analysis.runtime_profile,
                }
                st.rerun()
        manifest = load_output_json(output_dir, "run_manifest.json")
        if manifest:
            st.caption(f"마지막: {manifest.get('run_id', '—')} · as_of {manifest.get('as_of', '—')}")

    # --- Step 3 ---
    s3 = steps[2]
    compass = load_output_json(output_dir, "compass_regime.json")
    _step_anchor(s3.key)
    with st.expander(
        f"{STATUS_ICON[s3.status]} {s3.title} — {s3.detail}",
        expanded=_step_expanded(s3, default=compass is None),
    ):
        render_shortcut_row([SHORTCUT_COMPASS, SHORTCUT_SAA], key_prefix="dash_s3", columns=2)
        if compass is None:
            st.info("② 분석 후 표시")
        else:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("적용 레짐", compass.get("applied_regime", "—"))
            c2.metric("산출 레짐", compass.get("computed_regime", "—"))
            c3.metric("국면", compass.get("computed_market_phase", "—"))
            c4.metric("Data Gate", compass.get("data_gate", "—"))
            c5.metric("실행 레벨", compass.get("execution_level", "—"))
            if compass.get("data_gate") == "RED":
                st.error("Data Gate RED — ① 데이터·④ 실행 전 확인")

    # --- Step 4 ---
    s4 = steps[3]
    trade = load_output_csv(output_dir, "trade_actions.csv")
    _step_anchor(s4.key)
    with st.expander(
        f"{STATUS_ICON[s4.status]} {s4.title} — {s4.detail}",
        expanded=_step_expanded(s4, default=True),
    ):
        render_shortcut_row([SHORTCUT_GAP, SHORTCUT_PORTFOLIO], key_prefix="dash_s4", columns=2)
        if trade is None or trade.empty:
            st.info("② 분석 후 trade_actions 생성")
        else:
            actionable = trade[~trade["action"].isin(["Hold", "No trade", "Stop-buy"])]
            c1, c2 = st.columns(2)
            c1.metric("실행 검토", len(actionable))
            c2.metric("전체 액션", len(trade))
            show_trade_actions_table(
                actionable if not actionable.empty else trade,
                key_prefix="dash_trade",
                split_review=True,
            )

    # --- Step 5 ---
    s5 = steps[4]
    ac = load_output_json(output_dir, "acceptance_report.json") or {}
    _step_anchor(s5.key)
    with st.expander(
        f"{STATUS_ICON[s5.status]} {s5.title} — {s5.detail}",
        expanded=_step_expanded(s5, default=True),
    ):
        render_shortcut_row([SHORTCUT_OPS], key_prefix="dash_s5", columns=1)
        if st.button("🔒 AC 검증 실행", key="dash_ac_run"):
            from src.validation.acceptance_check import run_acceptance_check, write_acceptance_report

            report = run_acceptance_check(data_dir, output_dir)
            write_acceptance_report(report, output_dir / "acceptance_report.json")
            st.rerun()
        if ac:
            overall = ac.get("overall", "YELLOW")
            icon = STATUS_ICON.get(
                "done" if overall == "GREEN" else "warn" if overall == "YELLOW" else "fail", "·"
            )
            final = load_output_json(output_dir, "final_execution_decision.json") or {}
            c1, c2, c3 = st.columns(3)
            c1.metric("운용 승인", f"{icon} {final.get('system_status') or overall}")
            c2.metric("Scope", final.get("execution_scope") or ac.get("execution_scope", "—"))
            c3.metric("dry-run", f"{final.get('dry_run_days', ac.get('dry_run_days', 0))}/10")
            if final:
                st.caption(
                    f"최종 권위: final_execution_decision.json · "
                    f"Alpha `{final.get('alpha_execution_status', '—')}` · "
                    f"gap `{final.get('group_gap_source', '—')}`"
                )

    # --- Step 6 ---
    s6 = steps[5]
    draft_path = default_target_draft_path()
    _step_anchor(s6.key)
    with st.expander(
        f"{STATUS_ICON[s6.status]} {s6.title} — {s6.detail}",
        expanded=_step_expanded(s6, default=is_target_draft_pending(data_dir, draft_path)),
    ):
        render_shortcut_row([SHORTCUT_ALPHA_TARGET], key_prefix="dash_s6", columns=1)
        render_target_draft_workflow(data_dir, output_dir, draft_path, key_prefix="dash_draft")

    # --- Step 7 ---
    s7 = steps[6]
    _step_anchor(s7.key)
    with st.expander(
        f"{STATUS_ICON[s7.status]} {s7.title} — {s7.detail}",
        expanded=_step_expanded(s7, default=False),
    ):
        render_shortcut_row([SHORTCUT_PORTFOLIO], key_prefix="dash_s7", columns=1)
        st.markdown("매매 후 **종합 포트 → 포트폴리오**에서 positions 저장 → **② 재분석**")

    # --- Step 8 ---
    s8 = steps[7]
    _step_anchor(s8.key)
    with st.expander(
        f"{STATUS_ICON[s8.status]} {s8.title} — {s8.detail}",
        expanded=_step_expanded(s8, default=True),
    ):
        st.markdown("**보내기 전 확인** (미완료 항목은 바로가기)")
        render_shortcut_row(
            ai_export_prereq_shortcuts(include_alpha_target=draft_path.exists()),
            key_prefix="dash_ai_go",
            columns=3,
        )
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📦 번들 생성", type="primary", key="dash_ai_export", use_container_width=True):
                try:
                    result = run_ai_export(data_dir, output_dir)
                    st.session_state["ai_export_zip"] = result.zip_bytes
                    st.session_state["ai_export_meta"] = {
                        "as_of": result.as_of,
                        "run_id": result.run_id,
                    }
                    st.success(f"as_of {result.as_of}")
                except FileNotFoundError as exc:
                    st.warning(str(exc))
                except Exception as exc:
                    st.error(str(exc))
        with c2:
            render_shortcut_row([SHORTCUT_EXPORT_DETAIL], key_prefix="dash_ai_det", columns=1)
        zip_bytes = st.session_state.get("ai_export_zip") or st.session_state.get("dash_ai_zip")
        meta = st.session_state.get("ai_export_meta") or {}
        if zip_bytes:
            stamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                "⬇ ZIP 다운로드",
                zip_bytes,
                file_name=f"ai_cross_validation_{stamp}.zip",
                mime="application/zip",
                key="dash_ai_dl",
                use_container_width=True,
            )
            if meta.get("run_id"):
                st.caption(f"run_id: {str(meta['run_id'])[:19]}…")
            st.caption("ZIP + validation_prompt.md → 외부 AI. draft 있으면 replace_pairs CSV도 별도 첨부.")

    if pending := st.session_state.pop("dash_scroll_pending", None):
        _scroll_to_step(pending)
