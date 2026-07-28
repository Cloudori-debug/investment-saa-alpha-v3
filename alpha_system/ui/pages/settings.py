"""설정 — API 키·수집 기본값·활성에 필요한 자격 정보."""

from __future__ import annotations

import os

import streamlit as st

from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.nav import (
    FOCUS_DATA_REFRESH,
    FOCUS_SETTINGS_API,
    FOCUS_SETTINGS_DATA,
    PAGE_APPROVAL,
    consume_focus,
    navigate,
)
from src.settings.user_secrets import (
    UserSecrets,
    apply_secrets_to_env,
    clear_user_secrets,
    credential_status,
    load_user_secrets,
    mask_secret,
    save_user_secrets,
    secrets_path,
    test_dart_api_key,
    test_fred_api_key,
    test_kosis_api_key,
    test_krx_credentials,
)

_TAB_API = "API 키"
_TAB_DEFAULTS = "수집 기본값"
_TAB_DATA = "데이터 상태"
_TAB_PORTABLE = "이식·백업"
_TAB_HELP = "안내"
_TABS = (_TAB_API, _TAB_DEFAULTS, _TAB_DATA, _TAB_PORTABLE, _TAB_HELP)
_SESSION_TAB = "settings_section"


def render_settings(ctx: DashboardContext) -> None:
    focus = consume_focus()
    data_dir = ctx.root / "data"
    apply_secrets_to_env(data_dir)

    if focus == FOCUS_SETTINGS_API:
        st.session_state[_SESSION_TAB] = _TAB_API
    elif focus == FOCUS_SETTINGS_DATA:
        st.session_state[_SESSION_TAB] = _TAB_DATA
    if st.session_state.get(_SESSION_TAB) not in _TABS:
        st.session_state[_SESSION_TAB] = _TAB_API

    st.markdown(
        """
<div class="ap-page-head">
  <p class="ap-page-lead">
    시스템이 활성되는 데 필요한 API·로그인 정보를 기입·갱신합니다.
    키는 <code>data/local/user_secrets.json</code>에만 저장되며 Git에 올리지 않습니다.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    status = credential_status(data_dir)
    cols = st.columns(4)
    for col, label, ok in zip(
        cols,
        ("Open DART", "PyKRX / KRX", "FRED", "KOSIS"),
        (status["dart"], status["krx"], status.get("fred"), status.get("kosis")),
    ):
        level = "ok" if ok else "warn"
        with col:
            st.markdown(
                f'<div class="alpha-card alpha-card-{level}">'
                f"<strong>{label}</strong><br/>"
                f"<small>{'설정됨' if ok else '미설정'}</small></div>",
                unsafe_allow_html=True,
            )

    st.markdown('<div class="ap-tab-label">설정 구역</div>', unsafe_allow_html=True)
    section = st.segmented_control(
        "설정 구역",
        list(_TABS),
        selection_mode="single",
        required=True,
        label_visibility="collapsed",
        key=_SESSION_TAB,
        width="stretch",
    )
    if section is None:
        section = _TAB_API

    saved = load_user_secrets(data_dir)

    if section == _TAB_API:
        _render_api(data_dir, saved)
    elif section == _TAB_DEFAULTS:
        _render_defaults(data_dir, saved)
    elif section == _TAB_DATA:
        _render_data_status(ctx, data_dir, status)
    elif section == _TAB_PORTABLE:
        _render_portable(ctx)
    else:
        _render_help(data_dir)


def _render_portable(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.ops_assistant_pack import (
        PRODUCT_NAME,
        PRODUCT_TAGLINE,
        create_ops_backup_zip,
        list_pack_candidates,
        mark_setup_done,
        restore_ops_backup_zip,
        setup_status,
    )

    st.markdown(
        f"""
<div class="ap-panel">
  <div class="ap-panel-kicker">이식</div>
  <div class="ap-panel-title">{PRODUCT_NAME}</div>
  <p class="ap-panel-desc">{PRODUCT_TAGLINE}. 포맷·다른 Windows PC용 백업/복원.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    status = setup_status(ctx.root)
    st.caption(
        "체크: "
        f"DART {'OK' if status['dart_ok'] else '미설정'} · "
        f"target {'있음' if status['target_exists'] else '없음'} · "
        f"setup {'완료' if status['setup_done'] else '미완료'}"
    )
    include_opt = st.checkbox("가격·스코어 캐시 포함", value=True, key="ops_bk_opt")
    include_sec = st.checkbox(
        "API 키 포함 (USB 암호화 권장)",
        value=False,
        key="ops_bk_sec",
    )
    if st.button("백업 zip 생성", type="primary", key="ops_bk_create"):
        try:
            result = create_ops_backup_zip(
                ctx.root,
                include_optional_data=include_opt,
                include_secrets=include_sec,
            )
            st.success(f"생성: `{result.path}` · {len(result.included)}파일")
            if include_sec:
                st.warning("비밀키 포함 zip — 공유 금지")
        except Exception as exc:
            st.error(str(exc))

    with st.expander("포함 후보 목록", expanded=False):
        for item in list_pack_candidates(
            ctx.root,
            include_optional_data=include_opt,
            include_secrets=include_sec,
        ):
            mark = "OK" if item.exists else "—"
            st.text(f"[{mark}] {item.relative}")

    uploaded = st.file_uploader(
        "백업 zip 복원",
        type=["zip"],
        key="ops_bk_restore_up",
    )
    if uploaded is not None and st.button("이 PC에 복원", key="ops_bk_restore"):
        dest = ctx.root / "data" / "local" / "backups" / uploaded.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(uploaded.getvalue())
        try:
            info = restore_ops_backup_zip(ctx.root, dest)
            st.success(f"복원 {len(info['restored'])} · skip {len(info['skipped'])}")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if st.button("첫 설정 완료로 표시", key="ops_setup_done"):
        mark_setup_done(ctx.root, source="settings_ui")
        st.success("첫 실행 배너를 닫습니다.")
        st.rerun()


def _render_api(data_dir, saved: UserSecrets) -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">Open DART</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "[Open DART](https://opendart.fss.or.kr/) 인증키 (40자) — 펀더멘털·재무 보강"
        )
        dart_key = st.text_input(
            "DART API Key",
            value=saved.dart_api_key,
            type="password",
            placeholder="40자 인증키",
            key="v2_settings_dart_key",
        )
        if saved.dart_api_key:
            st.caption(f"저장됨: `{mask_secret(saved.dart_api_key)}`")

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">PyKRX / KRX 로그인</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "[data.krx.co.kr](https://data.krx.co.kr/) 회원 — 가격·시총 일괄 수집"
        )
        krx_id = st.text_input("KRX ID", value=saved.krx_id, key="v2_settings_krx_id")
        krx_pw = st.text_input(
            "KRX Password",
            value=saved.krx_pw,
            type="password",
            key="v2_settings_krx_pw",
        )
        if saved.krx_id:
            st.caption(f"저장 ID: `{mask_secret(saved.krx_id, 2)}`")

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">FRED (Tier-2 매크로)</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "[FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) — CPI·금리·HY OAS"
        )
        fred_key = st.text_input(
            "FRED API Key",
            value=saved.fred_api_key,
            type="password",
            key="v2_settings_fred_key",
        )
        if saved.fred_api_key:
            st.caption(f"저장됨: `{mask_secret(saved.fred_api_key)}`")

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">KOSIS (Tier-2 매크로)</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "[KOSIS Open API](https://kosis.kr/openapi/) — 한국 CPI·경기지수"
        )
        kosis_key = st.text_input(
            "KOSIS API Key",
            value=saved.kosis_api_key,
            type="password",
            key="v2_settings_kosis_key",
        )
        if saved.kosis_api_key:
            st.caption(f"저장됨: `{mask_secret(saved.kosis_api_key)}`")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        if st.button("저장", type="primary", use_container_width=True, key="v2_set_save"):
            path = save_user_secrets(
                data_dir,
                UserSecrets(
                    dart_api_key=dart_key.strip(),
                    krx_id=krx_id.strip(),
                    krx_pw=krx_pw.strip(),
                    fred_api_key=fred_key.strip(),
                    kosis_api_key=kosis_key.strip(),
                    pykrx_scope=saved.pykrx_scope,
                    dart_scope=saved.dart_scope,
                    default_as_of=saved.default_as_of,
                ),
            )
            apply_secrets_to_env(data_dir, overwrite=True)
            st.success(f"저장 완료 · `{path.name}`")
            st.rerun()
    with c2:
        if st.button("DART 테스트", use_container_width=True, key="v2_set_dart"):
            ok, msg = test_dart_api_key(dart_key.strip() or saved.dart_api_key)
            st.success(msg) if ok else st.error(msg)
    with c3:
        if st.button("KRX 테스트", use_container_width=True, key="v2_set_krx"):
            ok, msg = test_krx_credentials(
                krx_id.strip() or saved.krx_id,
                krx_pw.strip() or saved.krx_pw,
            )
            st.success(msg) if ok else st.error(msg)
    with c4:
        if st.button("FRED 테스트", use_container_width=True, key="v2_set_fred"):
            ok, msg = test_fred_api_key(fred_key.strip() or saved.fred_api_key)
            st.success(msg) if ok else st.error(msg)
    with c5:
        if st.button("KOSIS 테스트", use_container_width=True, key="v2_set_kosis"):
            ok, msg = test_kosis_api_key(kosis_key.strip() or saved.kosis_api_key)
            st.success(msg) if ok else st.error(msg)
    with c6:
        if st.button("키 삭제", use_container_width=True, key="v2_set_clear"):
            clear_user_secrets(data_dir)
            for name in (
                "DART_API_KEY",
                "OPENDART_API_KEY",
                "KRX_ID",
                "KRX_PW",
                "FRED_API_KEY",
                "KOSIS_API_KEY",
            ):
                os.environ.pop(name, None)
            st.warning("저장된 키를 삭제했습니다.")
            st.rerun()


def _render_defaults(data_dir, saved: UserSecrets) -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">데이터 수집 기본값</div>',
            unsafe_allow_html=True,
        )
        pykrx_scope = st.selectbox(
            "PyKRX scope 기본값",
            ["liquid", "holdings", "all"],
            index=["liquid", "holdings", "all"].index(saved.pykrx_scope)
            if saved.pykrx_scope in {"liquid", "holdings", "all"}
            else 0,
            key="v2_settings_pykrx_scope",
        )
        dart_scope = st.selectbox(
            "DART scope 기본값",
            ["prices", "liquid", "holdings"],
            index=["prices", "liquid", "holdings"].index(saved.dart_scope)
            if saved.dart_scope in {"prices", "liquid", "holdings"}
            else 0,
            key="v2_settings_dart_scope",
        )
        default_as_of = st.text_input(
            "기본 as_of (YYYY-MM-DD, 비우면 자동)",
            value=saved.default_as_of,
            key="v2_settings_default_as_of",
        )
        if st.button("기본값 저장", type="primary", key="v2_set_defaults_save"):
            save_user_secrets(
                data_dir,
                UserSecrets(
                    dart_api_key=saved.dart_api_key,
                    krx_id=saved.krx_id,
                    krx_pw=saved.krx_pw,
                    fred_api_key=saved.fred_api_key,
                    kosis_api_key=saved.kosis_api_key,
                    pykrx_scope=pykrx_scope,
                    dart_scope=dart_scope,
                    default_as_of=default_as_of.strip(),
                ),
            )
            st.success("기본값 저장 완료")
            st.rerun()


def _render_data_status(
    ctx: DashboardContext, data_dir, status: dict[str, bool]
) -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">정량 잠금 정책</div>',
            unsafe_allow_html=True,
        )
        from alpha_system.ui.services.proposal_freeze import (
            freeze_feature_enabled,
            set_freeze_feature_enabled,
        )

        enabled = freeze_feature_enabled(ctx.root)
        st.caption(
            "기본 off: 주간 요청서를 만들어도 정량이 잠기지 않습니다. "
            "주간 창 중 final 고정을 원하면 켜세요."
        )
        new_enabled = st.toggle(
            "요청서 생성 시 정량 재실행 차단",
            value=enabled,
            key="v2_proposal_freeze_policy",
        )
        if new_enabled != enabled:
            set_freeze_feature_enabled(ctx.root, enabled=new_enabled)
            st.success("잠금 on" if new_enabled else "잠금 off (영구 해제)")
            st.rerun()

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">자격·필수 파일</div>',
            unsafe_allow_html=True,
        )
        if not status["dart"] or not status["krx"]:
            st.warning("정량 수집 전에 API 키 탭에서 DART·KRX를 저장하세요.")
        for label, files in (
            ("필수", ("market_indicators.csv", "positions.csv", "target_portfolio.csv")),
            ("Alpha", ("universe.csv", "fundamentals.csv", "prices.csv", "alpha_scores.csv")),
            (
                "Tier-2",
                ("macro_tier2.csv", "tier2_sources.yaml", "tier2_provenance.json"),
            ),
        ):
            st.markdown(f"**{label}**")
            bits = []
            for name in files:
                ok = (data_dir / name).exists()
                bits.append(f"{'준비' if ok else '없음'} `{name}`")
            st.caption(" · ".join(bits))

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">갱신 경로</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "일상 정량 갱신은 결재함 › 정량·스코어의 「정량 전체 갱신」을 사용합니다. "
            "아래는 Tier-2·시장지표 보조 갱신입니다."
        )
        if st.button("결재함 · 정량 갱신으로", use_container_width=True, key="v2_set_to_quant"):
            navigate(PAGE_APPROVAL, focus=FOCUS_DATA_REFRESH)

        as_of = st.text_input(
            "보조 갱신 as_of (YYYY-MM-DD)",
            value=saved_as_of(data_dir) or ctx.as_of.isoformat(),
            key="v2_settings_refresh_as_of",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Tier-2 갱신 (FRED+KOSIS)", use_container_width=True, key="v2_set_t2"):
                from src.data_refresh.tier2_refresh import refresh_macro_tier2

                try:
                    t2 = refresh_macro_tier2(data_dir, as_of=as_of or None)
                    st.success(f"macro_tier2 갱신 ({t2.as_of})")
                    st.json(
                        {
                            "updated": t2.updated_fields,
                            "warnings": t2.warnings[:5],
                            "errors": t2.errors[:5],
                        }
                    )
                except Exception as exc:
                    st.error(str(exc))
        with c2:
            if st.button("시장지표 갱신", use_container_width=True, key="v2_set_mi"):
                from src.data_refresh.market_indicators_refresh import (
                    refresh_all_market_indicators,
                )
                from src.compass.regime_auto import sync_regime_from_compass

                try:
                    mi = refresh_all_market_indicators(data_dir, as_of=as_of or None)
                    regime = sync_regime_from_compass(
                        data_dir, ctx.root / "outputs", as_of=mi.as_of
                    )
                    st.success(
                        f"market_indicators 갱신 ({mi.as_of})"
                        + (f" · 레짐 {regime.applied_regime}" if regime.synced else "")
                    )
                    st.json(
                        {
                            "updated": mi.updated_fields,
                            "warnings": mi.warnings,
                            "errors": mi.errors,
                            "regime_synced": regime.synced,
                            "regime": regime.applied_regime or regime.computed_regime,
                            "regime_reason": regime.reason,
                        }
                    )
                except Exception as exc:
                    st.error(str(exc))


def saved_as_of(data_dir) -> str:
    return load_user_secrets(data_dir).default_as_of


def _render_help(data_dir) -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">우선순위·저장 위치</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
1. **UI 저장값** (`{secrets_path(data_dir)}`)
2. **환경변수** (`DART_API_KEY`, `KRX_ID`, `KRX_PW`, `FRED_API_KEY`, `KOSIS_API_KEY`)

`data/local/` 은 `.gitignore` 대상입니다. 키를 채팅·커밋에 넣지 마세요.

| 키 | 용도 |
|----|------|
| DART | ROE·OCF·재무 보강 |
| KRX | PyKRX 가격·시총 |
| FRED / KOSIS | Tier-2 매크로·레짐 보조 |
"""
        )
