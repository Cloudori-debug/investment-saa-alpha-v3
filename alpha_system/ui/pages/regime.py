"""레짐 — SAA/나침반 시장 레짐 조회·참고 (승인·target 변경 없음)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.judgment_snapshot import build_judgment_snapshot
from alpha_system.ui.services.nav import (
    FOCUS_REGIME,
    FOCUS_SETTINGS_DATA,
    FOCUS_T3_DETAIL,
    PAGE_APPROVAL,
    PAGE_SETTINGS,
    consume_focus,
    navigate,
    peek_focus,
)
from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.ui.services.v2_chrome import regime_info, render_regime_concerns
from alpha_system.ui.styles import status_card_class


def _load_indicator_row(root: Path) -> dict[str, Any] | None:
    path = root / "data" / "market_indicators.csv"
    if not path.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_csv(path)
        if df.empty:
            return None
        return df.iloc[-1].to_dict()
    except Exception:
        return None


def _fmt(v: Any, *, digits: int | None = None) -> str:
    if v is None:
        return "—"
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none"}:
        return "—"
    if digits is not None:
        try:
            return f"{float(s):.{digits}f}"
        except (TypeError, ValueError):
            return s
    return s


def _kospi_drawdown_pct(row: dict[str, Any]) -> str:
    try:
        kospi = float(row.get("kospi"))
        high = float(row.get("kospi_recent_high"))
        if high <= 0:
            return "—"
        return f"{(kospi / high - 1.0) * 100.0:+.1f}%"
    except (TypeError, ValueError):
        return "—"


def _render_analysis_refresh(ctx: DashboardContext) -> None:
    flash = st.session_state.pop("regime_analysis_flash", None)
    with st.container(border=True):
        st.subheader(
            copy_get("regime_page", "refresh_title", default="나침반 분석 갱신")
        )
        st.caption(
            copy_get(
                "regime_page",
                "refresh_caption",
                default=(
                    "런처 [3]과 동일 (standard + --refresh-market). "
                    "Tier-1·레짐 동기화·outputs 갱신 · target_portfolio 자동 변경 없음 · "
                    "보통 5~15분"
                ),
            )
        )
        if flash:
            level = str(flash.get("level") or "success")
            msg = str(flash.get("message") or "")
            if level == "warning":
                st.warning(msg)
            elif level == "error":
                st.error(msg)
            else:
                st.success(msg)
            caption = flash.get("caption")
            if caption:
                st.caption(str(caption))
        if st.button(
            copy_get(
                "regime_page",
                "refresh_cta",
                default="나침반·레짐 분석 실행",
            ),
            type="primary",
            key="regime_run_compass_analysis",
            use_container_width=True,
        ):
            from alpha_system.ui.services.auto_journal import journal_data_refresh
            from alpha_system.ui.services.refresh import run_compass_analysis

            with st.spinner(
                copy_get(
                    "regime_page",
                    "refresh_spinner",
                    default="나침반 분석 실행 중… 5~15분 걸릴 수 있습니다. 창을 닫지 마세요.",
                )
            ):
                result = run_compass_analysis(ctx.root, run_mode="standard")
            journal_data_refresh(
                as_of=ctx.as_of,
                ok=result.ok,
                message=result.message,
                detail=result.detail,
            )
            if result.ok:
                ctx.runtime.touch_refresh("compass_analysis")
                gate = str(result.detail.get("data_gate") or "").upper()
                caption = " · ".join(
                    x
                    for x in [
                        f"Data Gate: {gate}" if gate else "",
                        f"Actual Buy Allowed: {result.detail.get('actual_buy_allowed')}"
                        if result.detail.get("actual_buy_allowed") is not None
                        else "",
                        f"Health: {result.detail.get('health')}"
                        if result.detail.get("health")
                        else "",
                        (
                            f"as_of {result.detail.get('market_as_of')}"
                            if result.detail.get("market_as_of")
                            else ""
                        ),
                    ]
                    if x
                )
                st.session_state["regime_analysis_flash"] = {
                    "level": "warning" if gate == "RED" else "success",
                    "message": result.message,
                    "caption": caption,
                }
                st.rerun()
            else:
                st.session_state["regime_analysis_flash"] = {
                    "level": "error",
                    "message": result.message,
                    "caption": "",
                }
                st.error(result.message)
                tail = result.detail.get("stdout_tail") or result.detail.get(
                    "stderr_tail"
                )
                if tail:
                    with st.expander("로그 일부"):
                        st.code(str(tail))


def render_regime(ctx: DashboardContext) -> None:
    if peek_focus() == FOCUS_REGIME:
        consume_focus()
    info = regime_info(ctx.root)
    snap = build_judgment_snapshot(ctx)
    row = _load_indicator_row(ctx.root)
    tone = info.get("tone") if info.get("tone") in {"ok", "warn", "danger", "muted"} else "muted"

    st.markdown(
        f"""
<div class="ap-page-head">
  <p class="ap-page-lead">
    {copy_get(
        "regime_page",
        "lead",
        default="나침반 시장 레짐·Tier-1 지표 조회. 승인 화면이 아니며 target_portfolio·QVM 순위를 바꾸지 않습니다.",
    )}
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.subheader(copy_get("regime_page", "status_title", default="현재 적용 레짐"))
        st.caption(
            copy_get(
                "regime_page",
                "status_caption",
                default="조회·참고 · 사람이 메뉴에서 레짐을 고르지 않음 · 순수 자동 시 산출=적용",
            )
        )
        st.markdown(
            f'<div class="{status_card_class(tone)}">'
            f"<strong>{info.get('label') or '—'}</strong><br/>"
            f"<small>{info.get('detail') or ''}</small></div>",
            unsafe_allow_html=True,
        )
        if info.get("pure_auto"):
            render_regime_concerns(expanded=True)
        else:
            st.info(
                copy_get(
                    "regime_page",
                    "override_note",
                    default="현재 respect_override 모드입니다. CSV regime 값을 사람이 고정할 수 있습니다.",
                )
            )

    _render_analysis_refresh(ctx)

    with st.container(border=True):
        st.subheader(copy_get("regime_page", "indicators_title", default="Tier-1 시장 지표"))
        st.caption(
            copy_get(
                "regime_page",
                "indicators_caption",
                default="data/market_indicators.csv 최신 행 · 분석 버튼/런처 [3]은 Tier-1 네트워크 갱신+레짐 동기화 후 분석",
            )
        )
        if row is None:
            st.warning("market_indicators.csv가 없거나 비어 있습니다.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("as_of", _fmt(row.get("date")))
                st.metric("KOSPI", _fmt(row.get("kospi"), digits=2))
                st.metric("고점 대비", _kospi_drawdown_pct(row))
            with c2:
                st.metric("VIX", _fmt(row.get("vix"), digits=2))
                st.metric("USD/KRW", _fmt(row.get("usdkrw"), digits=2))
                st.metric("외국인 3일", _fmt(row.get("foreign_flow_3d")))
            with c3:
                st.metric("S&P500", _fmt(row.get("sp500"), digits=2))
                st.metric("설정일", _fmt(row.get("regime_set_date")))
                st.metric("만료일", _fmt(row.get("regime_expires_date")))
            reason = _fmt(row.get("regime_override_reason"))
            if reason != "—":
                st.markdown(f"**근거·동기화**  \n{reason}")

    with st.container(border=True):
        st.subheader(copy_get("regime_page", "related_title", default="연관 판정"))
        t3_tone = "ok" if snap.t3_available else "muted"
        st.markdown(
            f'<div class="{status_card_class(t3_tone)}">'
            f"<strong>T3</strong><br/><small>{snap.t3_summary}</small></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="{status_card_class("muted")}">'
            f"<strong>다음 판정</strong> — {snap.next_judgment}</div>",
            unsafe_allow_html=True,
        )
        b1, b2 = st.columns(2)
        with b1:
            if st.button(
                copy_get("system_judgment", "cta_t3", default="T3 상세 →"),
                key="regime_page_t3",
                use_container_width=True,
            ):
                navigate(PAGE_APPROVAL, focus=FOCUS_T3_DETAIL)
        with b2:
            if st.button(
                copy_get("regime_page", "cta_settings", default="Tier-2·데이터 →"),
                key="regime_page_settings",
                use_container_width=True,
            ):
                navigate(PAGE_SETTINGS, focus=FOCUS_SETTINGS_DATA)

    with st.container(border=True):
        st.subheader(copy_get("regime_page", "how_title", default="안내"))
        st.markdown(
            copy_get(
                "regime_page",
                "how_body",
                default=(
                    "1. 위 **나침반·레짐 분석 실행** (또는 런처 [3] Analysis)\n"
                    "2. 산출: `data/market_indicators.csv` · `outputs/` 일일 리포트\n"
                    "3. 레짐 값은 UI에서 수동 선택하지 않습니다 (순수 자동/파일 기준).\n"
                    "4. 알파 점수만 필요하면 홈 **정량 전체 갱신**을 쓰세요 (이 버튼과 다름)."
                ),
            )
        )
        st.caption(
            copy_get(
                "regime_page",
                "invariant",
                default="불변: proposal_mode pure_qvm · target_portfolio 자동 변경 없음 · 레짐≠종목 순위",
            )
        )
