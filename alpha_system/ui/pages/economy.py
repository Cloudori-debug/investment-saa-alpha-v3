"""Economy compass — global sleeves + rate regime (Review-only)."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from alpha_system.economy_compass import build_compass
from alpha_system.economy_signal import load_cached_signal
from alpha_system.ui.services.approval_chrome import page_head
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.economy_compass_board import (
    alpha_ops_bridge_html,
    apply_mean_reversion_sleeve_notes,
    asset_move_board_html,
    compass_with_posture,
    executable_compact_html,
    fear_greed_soft_panel_html,
    history_panel_html,
    mean_reversion_panel_html,
    metric_sleeve_lines_html,
    spx_200dma_soft_panel_html,
    why_drivers_html,
)
from alpha_system.ui.services.economy_display import (
    format_fetched_at,
    hero_copy,
    ladder_rows,
    metric_rows,
)
from alpha_system.ui.services.ui_copy import copy_get


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _html(body: str) -> None:
    """Render HTML without Markdown indent→code-block escaping (Streamlit)."""
    st.html(body)


def render_economy(ctx: DashboardContext) -> None:
    page_head(
        kicker=copy_get("economy", "page_kicker", default="경제 나침반"),
        title=copy_get(
            "economy", "page_title", default="국면 · 태도 (참고)"
        ),
        lead=copy_get(
            "economy",
            "page_lead",
            default=(
                "거시 태도만 · 종목 매매·포트 구성은 포트폴리오 · "
                "E/C는 strategy_portfolio 자세 우선."
            ),
        ),
    )
    st.caption(
        copy_get(
            "economy",
            "mission_caption",
            default=(
                "참고만 · 여기 숫자로 알파 전량 공격하지 않음 · "
                "사이드바 「포트폴리오」에서 팔→유지→사"
            ),
        )
    )
    tab_compass, tab_pension = st.tabs(
        [
            copy_get("economy", "tab_compass", default="나침반"),
            copy_get("economy", "tab_pension", default="연기금 수급"),
        ]
    )
    with tab_compass:
        _render_compass_tab(ctx)
    with tab_pension:
        _render_pension_tab(ctx)


def _render_compass_tab(ctx: DashboardContext) -> None:
    from alpha_system.economy_compass.fear_greed_soft import (
        build_fear_greed_soft_board,
    )
    from alpha_system.economy_compass.marks_continuum import (
        build_marks_continuum_board,
    )
    from alpha_system.economy_compass.mean_reversion_review import (
        build_mean_reversion_board,
    )
    from alpha_system.economy_compass.stress_overlay import build_bubble_stress_board
    from alpha_system.ui.services.economy_playbook import stage_playbook

    cached = load_cached_signal(ctx.root)
    compass = build_compass(cached)
    stress = build_bubble_stress_board(cached)
    mean_rev = build_mean_reversion_board(cached, root=ctx.root)
    fear_greed = build_fear_greed_soft_board(cached, root=ctx.root)
    marks = build_marks_continuum_board(mean_rev, fear_greed)
    posture_compass = compass_with_posture(
        compass,
        cached,
        stress.posture_stage,
        elevated=stress.elevated,
    )
    posture_compass = apply_mean_reversion_sleeve_notes(posture_compass, mean_rev)
    book = stage_playbook(
        stress.posture_stage
        if stress.posture_stage is not None
        else (None if cached is None else cached.stage)
    )
    hero = hero_copy(cached) if cached is not None else {}
    scoreline = str(hero.get("scoreline") or "")
    action_lines = tuple((c.label, c.body) for c in book.cards)
    try:
        from alpha_system.ui.services.investment_stance import (
            investment_stance_html,
            load_investment_stance,
            merge_playbook_cards,
        )

        _inv = load_investment_stance(ctx.root)
        action_lines = merge_playbook_cards(action_lines, _inv)
        _inv_html = investment_stance_html(_inv)
        if _inv_html:
            _html(_inv_html)
    except Exception:  # noqa: BLE001
        pass
    # 1) 결론 — 자산이 어떻게 움직이는지
    _html(
        asset_move_board_html(
            signal=cached,
            compass=posture_compass,
            playbook_title=book.title,
            playbook_tone=book.tone,
            action_lines=action_lines,
            posture_stage=(
                stress.posture_stage
                if stress is not None and getattr(stress, "show_posture_chip", False)
                else None
            ),
            stage_for_posture=None if stress is None else stress.stage,
            scoreline=scoreline,
            fetched_at=format_fetched_at(
                "" if cached is None else str(cached.fetched_at or "")
            ),
        )
    )
    # 1b) 포트로 넘기기 — 매매 실행 위치 명시
    _html(
        alpha_ops_bridge_html(
            playbook_title=book.title,
            playbook_tone=book.tone,
            action_lines=action_lines,
        )
    )
    _render_refresh(ctx.root, cached)
    # 2) 근거 — 왜 그런지 (지표만, 중복 패널 없음)
    _html(
        f'<div class="eco-sec eco-sec-2">'
        f'{_esc(copy_get("economy", "sec_why", default="왜 이렇게"))}'
        f"</div>"
    )
    st.caption(
        copy_get(
            "economy",
            "why_caption",
            default="위 자산 움직임의 근거 지표 · 같은 말을 카드로 반복하지 않음",
        )
    )
    _html(
        why_drivers_html(
            stress=stress,
            mean_rev=mean_rev,
            scoreline=scoreline,
            marks=marks,
        )
    )
    st.caption(
        copy_get(
            "economy",
            "fear_greed_caption",
            default=(
                "Fear&Greed Soft · CNN 원본 아님 · QVM·target·알파 E/C 불변"
            ),
        )
    )
    _html(fear_greed_soft_panel_html(fear_greed))
    from alpha_system.economy_compass.spx_200dma_soft import (
        build_spx_200dma_soft_board,
    )

    spx200 = build_spx_200dma_soft_board(ctx.root)
    st.caption(
        copy_get(
            "economy",
            "spx200_caption",
            default=(
                "S&P 200일 Soft · 2027H2~ 이탈 시 축소 Review · "
                "지금=관측 · 밸류 전량매도·target 불변"
            ),
        )
    )
    _html(spx_200dma_soft_panel_html(spx200))
    # 2b) 바젤 관찰 (거시 Review · 알파 target 불변)
    from alpha_system.ui.services.basel_observation_widgets import (
        render_basel_observation,
    )

    render_basel_observation(ctx, key_prefix="eco_basel_obs")
    # 2c) 숲(SAA) 자산배분 참고 — 예측 실패해도 버는 논리 (Review-only)
    try:
        from alpha_system.ui.services.saa_allocation_reference import (
            render_saa_allocation_reference,
        )

        with st.expander(
            copy_get(
                "economy",
                "saa_ref_fold",
                default="숲(SAA) 참고 · 예측 틀려도 버는 배분 논리",
            ),
            expanded=False,
        ):
            render_saa_allocation_reference(ctx.root)
    except Exception:  # noqa: BLE001
        pass
    # 2d) 정적·나침반 레그 상관 Review (비중 자동변경 없음)
    try:
        from alpha_system.ui.services.corr_review_board import (
            build_and_render_corr_review,
        )

        with st.expander(
            copy_get(
                "economy",
                "corr_review_fold",
                default="상관 Review · 정적·나침반 레그 (표시만)",
            ),
            expanded=False,
        ):
            st.caption(
                copy_get(
                    "economy",
                    "corr_review_caption",
                    default=(
                        "롤링·하락월 상관 · 고상관 경고 · 슬리브 내 제안비중 · "
                        "yaml/Executable 자동변경 없음 · Soft·target 불변"
                    ),
                )
            )
            if st.button(
                copy_get(
                    "economy",
                    "corr_review_btn",
                    default="상관 다시 계산 (가격 보충 가능)",
                ),
                key="eco_corr_review_btn",
                use_container_width=True,
            ):
                _board, _html_corr = build_and_render_corr_review(
                    ctx.root, ensure_fetch=True
                )
            else:
                _board, _html_corr = build_and_render_corr_review(
                    ctx.root, ensure_fetch=False
                )
            st.markdown(_html_corr, unsafe_allow_html=True)
    except Exception:  # noqa: BLE001
        pass
    # 2e) 가계 본체 최종 1개 — Lab×상관 선택 (비중 합성·yaml 불변)
    try:
        from alpha_system.ui.services.static_body_pick_board import (
            build_and_render_static_body_pick,
        )

        _html(
            f'<div class="eco-sec eco-sec-2">'
            f'{_esc(copy_get("economy", "sec_body_pick", default="투자 포트폴리오 · 운영 본체"))}'
            f"</div>"
        )
        st.caption(
            copy_get(
                "economy",
                "body_pick_caption",
                default=(
                    "정적 Lab + 나침반 고정비중 + 월말 국면 스위칭 · "
                    "CAGR·MDD·|ρ|로 최종 1개 · Soft 자세 제외 · "
                    "비중 합성·yaml 자동변경 없음 · Soft 합산 금지 · target 사람만"
                ),
            )
        )
        _pick_board, _pick_html = build_and_render_static_body_pick(
            ctx.root, ensure_fetch=False
        )
        _html(_pick_html)
        _ = _pick_board
    except Exception:  # noqa: BLE001
        pass
    # 3) 상품 후보 — 결론과 분리된 짧은 목록
    exec_html = executable_compact_html(posture_compass)
    if exec_html:
        _html(
            f'<div class="eco-sec eco-sec-2">'
            f'{_esc(copy_get("economy", "sec_exec", default="상품 후보"))}'
            f"</div>"
        )
        st.caption(
            copy_get(
                "economy",
                "exec_caption",
                default=(
                    "Executable ETF 후보(참고) · 알파 개별주 제안과 별개 · "
                    "사람만 매매 · target 불변"
                ),
            )
        )
        _html(exec_html)
    # 4) 더 참고 — 탭으로 근거만 (운영 방향은 위 바젤 관찰)
    with st.expander(
        copy_get(
            "economy",
            "sec_more",
            default="근거 더 보기 · 평소엔 안 펴도 됨",
        ),
        expanded=False,
    ):
        _html(
            '<div class="pf-fold-lead" role="note">'
            '<div class="pf-fold-row">'
            '<span class="pf-fold-lab">이 칸</span>'
            "<span>위 결론·「알파로 넘기기」로 부족한 <b>근거·시계열</b>만. "
            "매매 순서는 바꾸지 않습니다.</span></div>"
            '<div class="pf-fold-row pf-fold-do">'
            '<span class="pf-fold-lab">지금</span>'
            "<span>궁금한 탭만: 정책 일정 / 지표 숫자 / 빈도·장부 갭. "
            "종목 주문은 사이드바 포트폴리오.</span></div>"
            '<div class="pf-fold-row pf-fold-ignore">'
            '<span class="pf-fold-lab">무시</span>'
            "<span>표 숫자로 알파 전량 공격 · target·점수 자동 변경</span></div>"
            "</div>"
        )
        tab_pol, tab_inst, tab_met, tab_book = st.tabs(
            [
                copy_get(
                    "economy",
                    "sec_more_tab_policy",
                    default="정책 일정 (Basel 등)",
                ),
                copy_get(
                    "economy",
                    "sec_more_tab_inst",
                    default="기관 원문",
                ),
                copy_get(
                    "economy",
                    "sec_more_tab_metrics",
                    default="지표 숫자",
                ),
                copy_get(
                    "economy",
                    "sec_more_tab_book",
                    default="빈도·장부 갭",
                ),
            ]
        )
        with tab_pol:
            st.caption(
                "발표≠시행 · 일정 가설만 · 본문「바젤 관찰」이 운영 방향"
            )
            from alpha_system.ui.services.basel_theme_widgets import (
                render_basel_theme_board,
            )
            from alpha_system.ui.services.macro_policy_widgets import (
                render_macro_policy_timeline,
            )

            render_macro_policy_timeline(ctx, key_prefix="eco_macro_pol")
            render_basel_theme_board(ctx, key_prefix="eco_basel")
        with tab_inst:
            from alpha_system.ui.services.institutional_report_widgets import (
                ensure_inst_rep_css,
                render_institutional_report_board,
            )

            ensure_inst_rep_css()
            render_institutional_report_board(ctx, key_prefix="eco_inst_rep")
        with tab_met:
            st.caption(
                copy_get(
                    "economy",
                    "mean_rev_caption",
                    default=(
                        "실질금리·밸류·VIX 숫자 확인용 · "
                        "바닥 타이밍·target 불변"
                    ),
                )
            )
            _html(mean_reversion_panel_html(mean_rev))
            # Fear&Greed는 위「왜 이렇게」에 이미 표시 — 여기 중복 생략
            _render_ladder(cached)
            _render_metrics(cached, compass)
        with tab_book:
            st.caption(
                "과거 빈도·보유↔제안 갭 · 한국 주식은 포트로 · 주문 지시 아님"
            )
            _render_history(compass)
            _render_holdings_gap(ctx)
            _render_dividend_sleeve(ctx, cached)
            _render_kr_link(compass)


def _render_pension_tab(ctx: DashboardContext) -> None:
    """Alpha-native 수급 브리핑 tab — sibling DB/API read-only, Review-only."""
    from alpha_system.ui.services.pension_briefing_board import (
        PENSION_BRIEFING_CSS,
        pension_briefing_html,
    )
    from alpha_system.ui.services.pension_briefing_bridge import (
        fetch_pension_briefing,
    )

    st.markdown(f"<style>{PENSION_BRIEFING_CSS}</style>", unsafe_allow_html=True)
    st.caption(
        copy_get(
            "economy",
            "pension_tab_caption",
            default=(
                "알파 안에서 보는 수급 브리핑 · "
                "일상 갱신은 확인①에 포함 · 여기선 다시 읽기·형제 강제갱신 · "
                "제안·보유 겹침만 · 점수·target 불변"
            ),
        )
    )
    from alpha_system.ui.services.approval_chrome import (
        refresh_action_button,
        refresh_rail,
    )
    from alpha_system.ui.services.pension_briefing_refresh import (
        refresh_pension_briefing,
    )

    refresh_rail(
        title=copy_get("economy", "pension_refresh_rail", default="수급 브리핑 갱신"),
        hint=copy_get(
            "economy",
            "pension_refresh_rail_hint",
            default="확인①에 포함 · 여기선 재읽기 또는 형제 강제갱신 · 순위·target 불변",
        ),
    )
    col_reread, col_force = st.columns(2)
    with col_reread:
        refresh = refresh_action_button(
            copy_get("economy", "pension_refresh", default="수급 다시 읽기"),
            key="eco_pension_refresh",
            help="형제 DB(우선) 또는 API를 다시 읽습니다. 알파 순위·target은 쓰지 않습니다.",
            primary=True,
        )
    with col_force:
        force = refresh_action_button(
            copy_get("economy", "pension_force", default="형제 수급 강제갱신"),
            key="eco_pension_force",
            help="형제 폴더에서 수급 KRX 갱신을 실행합니다. 확인①과 동일 · 점수·target 불변.",
            primary=False,
        )
    if force:
        with st.spinner(
            copy_get(
                "economy",
                "pension_force_spin",
                default="형제 수급 갱신 중…",
            )
        ):
            result = refresh_pension_briefing(Path(ctx.root))
        st.session_state.pop("eco_pension_briefing_cache", None)
        status = str(result.get("status") or "")
        msg = str(result.get("message") or "")
        from alpha_system.ui.services.data_fetch_alerts import action_for_key

        pension_tip = action_for_key("pension")
        if status in {"ok", "noop"}:
            st.success(msg or "수급 갱신 완료")
        elif status in {"blocked", "missing_sibling", "missing_python"}:
            st.warning(
                (msg or status)
                + f"\n\n→ **조치:** {pension_tip}"
            )
        else:
            st.error(
                (msg or "수급 갱신 실패")
                + f"\n\n→ **조치:** {pension_tip}"
            )
        refresh = True
    if refresh:
        st.session_state.pop("eco_pension_briefing_cache", None)
    cache_key = "eco_pension_briefing_cache"
    if cache_key not in st.session_state or refresh:
        st.session_state[cache_key] = fetch_pension_briefing(
            alpha_root=Path(ctx.root),
            proposal_rows=getattr(ctx, "portfolio_rows", None),
            holdings_rows=getattr(ctx, "ops_portfolio_rows", None),
        )
    view = st.session_state[cache_key]
    _html(pension_briefing_html(view))
    if view.origin == "db":
        st.caption(
            copy_get(
                "economy",
                "pension_origin_db",
                default="데이터: 형제 pension.db 읽기 전용 · FastAPI 기동 불필요",
            )
            + f" · {view.base_url}"
        )
    elif view.origin == "http":
        st.caption(
            copy_get(
                "economy",
                "pension_origin_http",
                default="데이터: 형제 API · DB 파일이 없거나 비어 API로 대체",
            )
        )
        st.link_button(
            copy_get("economy", "pension_open", default="형제 수급 창 열기"),
            "http://127.0.0.1:8000",
        )
    elif view.sibling_path is None:
        st.caption(
            copy_get(
                "economy",
                "pension_sibling_missing",
                default=(
                    "형제 폴더 investment-fund-screener 가 옆에 없습니다. "
                    "폴더를 나란히 두거나 수급을 한 번 갱신하세요."
                ),
            )
        )
    else:
        st.caption(f"형제 경로 · {view.sibling_path}")


def _render_history(compass) -> None:
    _html(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_history", default="과거 유사국면"))}'
        f"</div>"
    )
    st.caption(
        copy_get(
            "economy",
            "history_caption",
            default=(
                "같은 긴축 버킷의 사전계산 월수익률 빈도 · "
                "온라인 전수 백테스트 아님 · 참고용"
            ),
        )
    )
    _html(history_panel_html(compass))


def _render_kr_link(compass) -> None:
    _html(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_kr_link", default="한국 주식"))}'
        f"</div>"
    )
    _html(
        f'<div class="eco-compass-block">'
        f'<div class="eco-kr-link">{_esc(compass.kr_link)}</div>'
        f"</div>"
    )
    st.caption(
        copy_get(
            "economy",
            "kr_link_caption",
            default=(
                "한국 개별주=포트폴리오 「오늘 매매」·집합·카드 · "
                "나침반은 편입·target을 바꾸지 않음"
            ),
        )
    )


def _render_refresh(root, signal) -> None:
    """Recalculate under the hero — FRED + market_indicators + 바젤."""
    from alpha_system.ui.services.approval_chrome import (
        refresh_action_button,
        refresh_rail,
    )
    from alpha_system.ui.services.compass_inputs_refresh import (
        market_indicators_as_of,
        market_indicators_stale_days,
        refresh_compass_inputs,
    )

    refresh_rail(
        title=copy_get("economy", "refresh_rail", default="나침반 다시 계산"),
        hint=copy_get(
            "economy",
            "refresh_rail_hint",
            default="FRED 국면 + VIX·코스피(market_indicators) + 바젤 · Soft·target 불변",
        ),
    )
    stale = market_indicators_stale_days(Path(root))
    mi_asof = market_indicators_as_of(Path(root))
    if stale is not None and stale >= 3:
        st.warning(
            copy_get(
                "economy",
                "market_stale",
                default=(
                    "시장지표(VIX·코스피) as_of {as_of} · {days}일 전 · "
                    "Fear&Greed Soft·평균회귀가 멈춘 것처럼 보입니다. 「다시 계산」하세요."
                ),
                as_of=mi_asof or "—",
                days=stale,
            )
        )
    col, _ = st.columns((1, 1))
    with col:
        clicked = refresh_action_button(
            copy_get("economy", "refresh", default="다시 계산"),
            key="economy_signal_refresh",
            primary=True,
        )
    from alpha_system.ui.services.refresh_progress_ui import render_inline_job_progress

    # 확인① 등 백그라운드 작업이 돌면 옆(아래)에 진행도 표시
    render_inline_job_progress(Path(root))
    if clicked:
        basel_detail = ""
        prog = st.progress(0.0, text="나침반 다시 계산…")
        try:
            prog.progress(0.25, text="1/3 FRED 국면·스냅샷…")
            bundle = refresh_compass_inputs(Path(root))
            from alpha_system.ui.services.basel_policy_refresh import (
                refresh_basel_policy,
            )

            prog.progress(0.7, text="2/3 바젤 공식 페이지…")
            basel_report = refresh_basel_policy(Path(root))
            basel_detail = basel_report.detail
            prog.progress(1.0, text="3/3 완료")
            if bundle.errors:
                from alpha_system.ui.services.data_fetch_alerts import (
                    action_for_issue,
                )

                tips = [
                    f"{e}\n\n→ **조치:** {action_for_issue(str(e))}"
                    for e in bundle.errors[:5]
                ]
                st.error(
                    "데이터 갱신이 막혔습니다\n\n"
                    + "\n\n---\n\n".join(tips)
                )
            elif any(
                "비밀번호" in w or "로그인" in w or "KRX" in w
                for w in (bundle.warnings or [])
            ):
                st.warning(
                    "일부 데이터만 갱신됨 (KRX 등)\n\n"
                    + "\n\n".join(bundle.warnings[:4])
                    + "\n\n→ **조치:** 설정 › KRX 로그인 확인 후 다시 계산"
                )
            elif bundle.warnings:
                st.caption(" · ".join(bundle.warnings[:2]))
            if bundle.detail:
                st.caption(bundle.detail)
        except Exception as exc:
            prog.progress(0.0, text="실패")
            st.error(
                "데이터 갱신 실패\n\n"
                f"{str(exc)[:400]}\n\n"
                "→ **조치:** 설정 › KRX/API 테스트 후 나침반「다시 계산」"
            )
        else:
            if basel_detail:
                st.caption(f"바젤 공식 페이지 · {basel_detail}")
            # 막힘·경고는 화면에서 읽고 조치할 수 있게 즉시 rerun하지 않음
            if bundle.errors or any(
                "비밀번호" in w or "로그인" in w
                for w in (bundle.warnings or [])
            ):
                pass
            else:
                st.rerun()
    when = format_fetched_at(signal.fetched_at) if signal is not None else ""
    mi_bit = f" · 시장지표 {mi_asof}" if mi_asof else ""
    if when:
        st.caption(
            copy_get(
                "economy",
                "refresh_as_of",
                default=(
                    "마지막 FRED {when}{mi} · 「다시 계산」=국면+VIX/코스피+바젤 "
                    "(배당 표는 중기 정량 · Soft·target 불변)"
                ),
                when=when,
                mi=mi_bit,
            )
        )
    else:
        st.caption(
            copy_get(
                "economy",
                "refresh_never",
                default=(
                    "아직 계산 없음 · 누르면 FRED 국면 + 시장지표 + 바젤을 갱신합니다"
                ),
            )
        )


def _render_dividend_sleeve(ctx: DashboardContext, signal) -> None:
    """Rate-regime hint only — dividend columns live on portfolio 후보 30."""
    from alpha_system.ui.services.economy_dividend_board import dividend_sleeve_hint

    stage = None if signal is None else signal.stage
    hint = dividend_sleeve_hint(stage)
    market = str(getattr(ctx, "screen_market", None) or "KOSPI")

    _html(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_dividend", default="배당 · 환원"))}</div>'
    )
    _html(
        f'<div class="eco-div eco-div-{_esc(hint.tone)}">'
        f'<div class="eco-div-title">{_esc(hint.title)}</div>'
        f'<div class="eco-div-body">{_esc(hint.detail)}</div>'
        f"</div>"
    )
    st.caption(
        copy_get(
            "economy",
            "dividend_caption",
            default=(
                f"종목별 SR·배당%는 포트폴리오 › 후보 30 표에 표시합니다 "
                f"({market} 중기) · 경제 시그널은 금리 국면 힌트만 · "
                "순위·target 변경 없음 · 표 최신화는 확인 › ① 정량"
            ),
        )
    )


def _render_ladder(signal) -> None:
    current = None if signal is None else signal.stage
    cells = []
    for row in ladder_rows(current):
        now_cls = " is-now" if row["current"] else ""
        mark = '<div class="eco-step-now">지금</div>' if row["current"] else ""
        cells.append(
            f'<div class="eco-step{now_cls}">'
            f'<div class="eco-step-n">{int(row["stage"])}단계</div>'
            f'<div class="eco-step-label">{_esc(row["label"])}</div>'
            f'<div class="eco-step-split">{_esc(row["equity"])} / {_esc(row["cash"])}</div>'
            f"{mark}"
            "</div>"
        )
    _html(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_ladder", default="단계"))}</div>'
        f'<div class="eco-steps">{"".join(cells)}</div>'
    )


def _render_holdings_gap(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.economy_playbook import holdings_proposal_gap
    from alpha_system.ui.services.screen_horizon import is_short

    gap = holdings_proposal_gap(
        getattr(ctx, "ops_portfolio_rows", None),
        getattr(ctx, "portfolio_rows", None),
    )
    market = str(getattr(ctx, "screen_market", None) or "KOSPI")
    book_lab = "단기" if is_short(getattr(ctx, "screen_horizon", None)) else "중기"
    _html(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_gap", default="보유 · 제안 괴리"))}</div>'
    )
    st.caption(
        copy_get(
            "economy",
            "gap_caption",
            default=(
                f"{market} · {book_lab} · 실보유 vs 최종 제안 · "
                "교체·편입은 사람 Review · target 자동기입 없음"
            ),
        )
    )
    if gap.no_books:
        st.info(
            copy_get(
                "economy",
                "gap_empty",
                default=(
                    "실보유 또는 최종 제안이 비어 있습니다. "
                    "포트폴리오에서 보유 체크·제안 확정 후 다시 보세요."
                ),
            )
        )
        return

    def _chips(rows: list, empty_label: str) -> str:
        if not rows:
            return f'<span class="eco-gap-empty">{_esc(empty_label)}</span>'
        return "".join(
            f'<span class="eco-gap-chip">{_esc(r.name)} '
            f'<span class="eco-gap-tk">{_esc(r.ticker)}</span></span>'
            for r in rows
        )

    _html(
        '<div class="eco-gap-grid">'
        f'<div class="eco-gap-card eco-gap-out">'
        f'<div class="eco-gap-h">{_esc(copy_get("economy", "gap_held_out", default="보유 · 제안 밖"))}'
        f' · {len(gap.held_not_proposed)}</div>'
        f'<div class="eco-gap-hint">{_esc(copy_get("economy", "gap_held_out_hint", default="교체·축소 Review"))}</div>'
        f'<div class="eco-gap-chips">{_chips(gap.held_not_proposed, "없음")}</div>'
        f"</div>"
        f'<div class="eco-gap-card eco-gap-in">'
        f'<div class="eco-gap-h">{_esc(copy_get("economy", "gap_prop_in", default="제안 · 미보유"))}'
        f' · {len(gap.proposed_not_held)}</div>'
        f'<div class="eco-gap-hint">{_esc(copy_get("economy", "gap_prop_in_hint", default="편입 Review"))}</div>'
        f'<div class="eco-gap-chips">{_chips(gap.proposed_not_held, "없음")}</div>'
        f"</div>"
        f'<div class="eco-gap-card eco-gap-ok">'
        f'<div class="eco-gap-h">{_esc(copy_get("economy", "gap_overlap", default="보유 · 제안 일치"))}'
        f' · {len(gap.overlap)}</div>'
        f'<div class="eco-gap-hint">{_esc(copy_get("economy", "gap_overlap_hint", default="유지 후보"))}</div>'
        f'<div class="eco-gap-chips">{_chips(gap.overlap, "없음")}</div>'
        f"</div>"
        "</div>"
    )
    if not gap.has_gaps:
        st.caption(
            copy_get(
                "economy",
                "gap_aligned",
                default="보유와 최종 제안이 같습니다. 비중(단기채)만 단계에 맞추면 됩니다.",
            )
        )


def _render_metrics(signal, compass=None) -> None:
    _html(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_inputs", default="근거 · 읽는 법"))}'
        f"</div>"
    )
    st.caption(
        copy_get(
            "economy",
            "inputs_caption",
            default="가로바=위치 · 아래=구간 해석 · 슬리브 함의",
        )
    )
    if signal is None or not signal.inputs:
        st.caption(
            copy_get("economy", "need_fred", default="설정 › API 키에 FRED 키가 있으면 계산합니다.")
        )
        return
    hint_by_key = {}
    if compass is not None:
        hint_by_key = {h.key: h for h in compass.metric_hints}
    cards = []
    for row in metric_rows(signal):
        reading = str(row.get("reading") or "").strip()
        reading_html = (
            f'<div class="eco-m-read">{_esc(reading)}</div>' if reading else ""
        )
        hint = hint_by_key.get(str(row.get("key") or ""))
        sleeve_html = (
            f'<div class="eco-m-sleeve-v">{_esc(hint.sleeve_implication)}</div>'
            if hint and hint.sleeve_implication
            else ""
        )
        cards.append(
            '<div class="eco-metric">'
            f'<div class="eco-m-title">{_esc(row["title"])}</div>'
            f'<span class="eco-stress eco-{_esc(row["tone"])}">{_esc(row["stress"])}</span>'
            f'<div class="eco-val">{_esc(row["value"])}</div>'
            f'<div class="eco-m-hint">{_esc(row["hint"])}</div>'
            f'<div class="eco-date">{_esc(row["as_of"])}</div>'
            f"{_slider_html(row.get('slider'))}"
            f"{reading_html}"
            f"{sleeve_html}"
            "</div>"
        )
    _html(f'<div class="eco-grid">{"".join(cards)}</div>')
    if compass is not None and not any("eco-m-sleeve-v" in c for c in cards):
        extra = metric_sleeve_lines_html(compass)
        if extra:
            _html(extra)


def _slider_html(slider: object) -> str:
    if not isinstance(slider, dict):
        return ""
    segs = []
    for seg in slider.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        width = seg.get("width")
        tone = seg.get("tone") or "off"
        segs.append(
            f'<span class="eco-slide-seg eco-{_esc(tone)}" style="width:{float(width):g}%"></span>'
        )
    ticks = []
    for tick in slider.get("ticks") or []:
        if not isinstance(tick, dict):
            continue
        ticks.append(
            f'<span class="eco-slide-tick" style="left:{float(tick["pct"]):g}%">'
            f'<span class="eco-slide-tick-mark"></span>'
            f'<span class="eco-slide-tick-lab">{_esc(tick["label"])}</span>'
            "</span>"
        )
    mark_tone = _esc(slider.get("tone") or "off")
    pct = float(slider.get("pct") or 0)
    clamp = " is-clamp" if slider.get("clamped") else ""
    return (
        f'<div class="eco-slide{clamp}">'
        f'<div class="eco-slide-track">{"".join(segs)}'
        f'<span class="eco-slide-mark eco-{mark_tone}" style="left:{pct:g}%"></span>'
        "</div>"
        f'<div class="eco-slide-ticks">{"".join(ticks)}</div>'
        "</div>"
    )
