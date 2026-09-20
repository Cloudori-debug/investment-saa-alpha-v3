"""설정 — API 키·수집 기본값·활성에 필요한 자격 정보."""

from __future__ import annotations

import os

import streamlit as st

from alpha_system.ui.services.approval_chrome import ap_chips, ap_head, ap_subhead, page_head, page_tabs
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.nav import (
    FOCUS_DATA_REFRESH,
    FOCUS_SETTINGS_API,
    FOCUS_SETTINGS_DATA,
    PAGE_APPROVAL,
    consume_focus,
    navigate,
)
from alpha_system.ui.services.v2_chrome import render_theme_picker
from alpha_system.ui.services.ui_copy import copy_get
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
    test_data_go_kr_api_key,
    test_fred_api_key,
    test_kosis_api_key,
    test_krx_credentials,
)

_TAB_DISPLAY = "화면"
_TAB_API = "API 키"
_TAB_DEFAULTS = "수집 기본값"
_TAB_DATA = "데이터 상태"
_TAB_PORTABLE = "이식·백업"
_TAB_TOOLS = "도구"
_TAB_HELP = "안내"
_TABS = (
    _TAB_DISPLAY,
    _TAB_API,
    _TAB_DEFAULTS,
    _TAB_DATA,
    _TAB_PORTABLE,
    _TAB_TOOLS,
    _TAB_HELP,
)
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

    page_head(
        kicker="설정",
        title="화면 · API · 수집 · 이식 · 도구",
        lead=(
            "화면 테마와 시스템이 활성되는 데 필요한 API·로그인 정보를 기입·갱신합니다. "
            "장부 백업·업데이트·런타임 복구는 「도구」에서 합니다. "
            "키는 data/local/user_secrets.json에만 저장되며 Git에 올리지 않습니다."
        ),
    )

    status = credential_status(data_dir)
    ap_chips(
        [
            (f"Open DART · {'설정됨' if status['dart'] else '미설정'}", "ok" if status["dart"] else "wait"),
            (f"PyKRX / KRX · {'설정됨' if status['krx'] else '미설정'}", "ok" if status["krx"] else "wait"),
            (
                f"FRED · {'설정됨' if status.get('fred') else '미설정'}",
                "ok" if status.get("fred") else "wait",
            ),
            (
                f"KOSIS · {'설정됨' if status.get('kosis') else '미설정'}",
                "ok" if status.get("kosis") else "wait",
            ),
            (
                f"공정위 · {'설정됨' if status.get('data_go_kr') else '미설정'}",
                "ok" if status.get("data_go_kr") else "wait",
            ),
        ]
    )

    section = page_tabs("설정 구역", _TABS, key=_SESSION_TAB)

    saved = load_user_secrets(data_dir)

    if section == _TAB_DISPLAY:
        _render_display(ctx)
    elif section == _TAB_API:
        _render_api(data_dir, saved)
    elif section == _TAB_DEFAULTS:
        _render_defaults(data_dir, saved)
    elif section == _TAB_DATA:
        _render_data_status(ctx, data_dir, status)
    elif section == _TAB_PORTABLE:
        _render_portable(ctx)
    elif section == _TAB_TOOLS:
        _render_tools(ctx)
    else:
        _render_help(data_dir)


def _render_display(ctx: DashboardContext) -> None:
    ap_head(
        kicker=copy_get("display", "tab", default="화면"),
        title=copy_get("display", "theme_label", default="화면 테마"),
        desc=copy_get(
            "display",
            "theme_lead",
            default="기본은 다크입니다. 이 PC에만 저장되며 점수·장부는 바뀌지 않습니다.",
        ),
    )
    with st.container(border=True):
        ap_subhead(copy_get("display", "theme_label", default="화면 테마"))
        render_theme_picker(ctx.root, key="saa_theme_settings", compact=False)


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

    ap_head(
        kicker="이식",
        title=PRODUCT_NAME,
        desc=f"{PRODUCT_TAGLINE}. 포맷·다른 Windows PC용 백업/복원.",
    )
    st.markdown(
        "다른 컴퓨터로 옮길 때 **프로그램 폴더**와 **장부 백업**만 있으면 됩니다. "
        "자동매매·증권사 연결은 없습니다."
    )
    st.markdown(
        "1. 이 PC에서 아래 **백업 zip 생성** 또는 「도구」의 장부 내보내기\n"
        "2. 새 PC에 Python 3.11+ 설치(PATH 추가) 후 프로그램 폴더 복사\n"
        "3. `투자나침반.bat` — `.venv`는 자동으로 다시 만듦 · "
        "장부가 비면 「도구」에서 가져오기"
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


def _render_tools(ctx: DashboardContext) -> None:
    """BAT 메뉴에 있던 이식·복구·업데이트. 일상 실행은 투자나침반.bat 만."""
    import os
    import subprocess
    import sys

    from alpha_system.ui.services.ops_assistant_pack import (
        create_ops_backup_folder,
        restore_ops_backup_any,
    )

    ap_head(
        kicker="도구",
        title="장부 · 업데이트 · 복구",
        desc="예전에 루트 BAT로 하던 일입니다. 일상 실행 파일은 투자나침반.bat 만 둡니다.",
    )

    with st.container(border=True):
        ap_subhead("장부 내보내기")
        st.caption("보유·목표가·승인만 USB로. 프로그램 폴더는 그대로 둡니다.")
        inc_cache = st.checkbox("가격·스코어 캐시 포함", value=True, key="ops_tool_cache")
        inc_sec = st.checkbox("API 키 포함", value=False, key="ops_tool_sec")
        if st.button("장부 폴더 만들기", type="primary", key="ops_tool_export"):
            try:
                result = create_ops_backup_folder(
                    ctx.root,
                    dest_dir=ctx.root / "dist" / "CARRY" / "02_SAA-Alpha-Backup",
                    include_optional_data=inc_cache,
                    include_secrets=inc_sec,
                )
                st.success(f"생성: `{result.path}`")
            except Exception as exc:
                st.error(str(exc))

    with st.container(border=True):
        ap_subhead("장부 가져오기")
        st.caption("프로그램은 그대로, 장부만 덮어씁니다. 가져오기 후 투자나침반을 다시 켜세요.")
        uploaded = st.file_uploader(
            "백업 zip",
            type=["zip"],
            key="ops_tool_import_up",
        )
        if uploaded is not None and st.button("이 PC에 장부 복원", key="ops_tool_import"):
            dest = ctx.root / "data" / "local" / "backups" / uploaded.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(uploaded.getvalue())
            try:
                info = restore_ops_backup_any(ctx.root, dest)
                st.success(
                    f"복원 {len(info.get('restored', []))} · skip {len(info.get('skipped', []))}"
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with st.container(border=True):
        ap_subhead("프로그램만 업데이트")
        st.caption("data\\ 장부는 유지합니다. UI를 끈 뒤 zip을 고르세요.")
        upd = st.file_uploader("saa-alpha-update.zip", type=["zip"], key="ops_tool_upd_up")
        if upd is not None and st.button("업데이트 적용", key="ops_tool_upd"):
            zip_path = ctx.root / "saa-alpha-update.zip"
            zip_path.write_bytes(upd.getvalue())
            ps1 = ctx.root / "scripts" / "apply_update.ps1"
            try:
                proc = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(ps1),
                        "-InstallRoot",
                        str(ctx.root),
                        "-ZipPath",
                        str(zip_path),
                    ],
                    cwd=str(ctx.root),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if proc.returncode != 0:
                    st.error(proc.stderr or proc.stdout or f"exit {proc.returncode}")
                else:
                    st.success("적용됨. UI를 끄고 투자나침반.bat 으로 다시 여세요.")
                    if proc.stdout:
                        st.caption(proc.stdout[-1500:])
            except Exception as exc:
                st.error(str(exc))

    with st.container(border=True):
        ap_subhead("다른 PC로 이사 준비")
        st.caption("장부 폴더 + 안내문을 dist\\CARRY 에 만듭니다. 폴더 통째 복사해도 됩니다.")
        move_sec = st.checkbox("API 키도 넣기", value=True, key="ops_tool_move_sec")
        if st.button("이사 폴더 만들기", key="ops_tool_move"):
            try:
                result = create_ops_backup_folder(
                    ctx.root,
                    dest_dir=ctx.root / "dist" / "CARRY" / "02_SAA-Alpha-Backup",
                    include_optional_data=True,
                    include_secrets=move_sec,
                )
                readme_py = ctx.root / "scripts" / "write_pc_move_readme.py"
                subprocess.run(
                    [sys.executable, str(readme_py), "--root", str(ctx.root)],
                    cwd=str(ctx.root),
                    check=False,
                )
                st.success(f"준비: `{result.path.parent}`")
            except Exception as exc:
                st.error(str(exc))

    with st.container(border=True):
        ap_subhead("런타임 복구")
        st.caption(".venv 가 없거나 깨졌을 때. 인터넷이 필요합니다.")
        if st.button("패키지 설치·복구", key="ops_tool_venv"):
            script = ctx.root / "scripts" / "ensure_runtime.py"
            try:
                proc = subprocess.run(
                    [sys.executable, str(script), "--root", str(ctx.root)],
                    cwd=str(ctx.root),
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if proc.returncode != 0:
                    st.error(proc.stderr or proc.stdout or f"exit {proc.returncode}")
                else:
                    st.success("런타임 OK")
                    if proc.stdout:
                        st.caption(proc.stdout[-800:])
            except Exception as exc:
                st.error(str(exc))

    with st.container(border=True):
        ap_subhead("책상")
        st.caption("알파와 수급 브리핑은 따로 켜집니다. 점수·장부는 섞지 않습니다.")
        desk = ctx.root / "desk" / "책상.html"
        if desk.exists() and st.button("책상 페이지 열기", key="ops_tool_desk"):
            try:
                os.startfile(str(desk))  # type: ignore[attr-defined]
            except AttributeError:
                st.info(str(desk))


def _render_api(data_dir, saved: UserSecrets) -> None:
    with st.container(border=True):
        ap_subhead("Open DART")
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
        ap_subhead("PyKRX / KRX 로그인")
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
        ap_subhead("FRED (Tier-2 매크로)")
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
        ap_subhead("KOSIS (Tier-2 매크로)")
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

    with st.container(border=True):
        ap_subhead("공공데이터포털 (공정위 순환출자)")
        st.markdown(
            "[기업집단별 순환출자 현황 OpenAPI](https://www.data.go.kr/data/15093661/openapi.do) "
            "와 [지정 기업집단 현황](https://www.data.go.kr/data/15091886/openapi.do) 활용신청. "
            "일반 인증키의 **디코딩** 키를 넣습니다. 인코딩 키(%3D 포함)를 넣어도 프로그램이 풀어 씁니다. "
            "지정집단 API를 신청하지 않으면 순환출자 집단명만 매칭합니다."
        )
        data_go_key = st.text_input(
            "data.go.kr API Key",
            value=saved.data_go_kr_api_key,
            type="password",
            placeholder="공공데이터포털 일반 인증키",
            key="v2_settings_data_go_kr_key",
        )
        if saved.data_go_kr_api_key:
            st.caption(f"저장됨: `{mask_secret(saved.data_go_kr_api_key)}`")

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
                    data_go_kr_api_key=data_go_key.strip(),
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
        if st.button("공정위 테스트", use_container_width=True, key="v2_set_ftc"):
            ok, msg = test_data_go_kr_api_key(data_go_key.strip() or saved.data_go_kr_api_key)
            st.success(msg) if ok else st.error(msg)
    if st.button("키 삭제", use_container_width=True, key="v2_set_clear"):
        clear_user_secrets(data_dir)
        for name in (
            "DART_API_KEY",
            "OPENDART_API_KEY",
            "KRX_ID",
            "KRX_PW",
            "FRED_API_KEY",
            "KOSIS_API_KEY",
            "DATA_GO_KR_API_KEY",
            "DATA_API_KEY",
        ):
            os.environ.pop(name, None)
        st.warning("저장된 키를 삭제했습니다.")
        st.rerun()


def _render_defaults(data_dir, saved: UserSecrets) -> None:
    with st.container(border=True):
        ap_subhead("데이터 수집 기본값")
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
                    data_go_kr_api_key=saved.data_go_kr_api_key,
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
        ap_subhead("정량 잠금 정책")
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
        ap_subhead("자격·필수 파일")
        if not status["dart"] or not status["krx"]:
            st.warning("정량 수집 전에 API 키 탭에서 DART·KRX를 저장하세요.")
        for label, files in (
            ("필수", ("positions.csv", "target_portfolio.csv")),
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
        ap_subhead("갱신 경로")
        st.caption(
            "일상 정량 갱신은 확인 › ① 숫자의 「정량 전체 갱신」을 사용합니다. "
            "아래는 Tier-2·시장지표 보조 갱신입니다."
        )
        if st.button("확인 · 정량 갱신으로", use_container_width=True, key="v2_set_to_quant"):
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

                try:
                    mi = refresh_all_market_indicators(data_dir, as_of=as_of or None)
                    st.success(f"market_indicators 갱신 ({mi.as_of})")
                    st.json(
                        {
                            "updated": mi.updated_fields,
                            "warnings": mi.warnings,
                            "errors": mi.errors,
                        }
                    )
                except Exception as exc:
                    st.error(str(exc))


def saved_as_of(data_dir) -> str:
    return load_user_secrets(data_dir).default_as_of


def _render_help(data_dir) -> None:
    with st.container(border=True):
        ap_subhead("우선순위·저장 위치")
        st.markdown(
            f"""
1. **UI 저장값** (`{secrets_path(data_dir)}`)
2. **환경변수** (`DART_API_KEY`, `KRX_ID`, `KRX_PW`, `FRED_API_KEY`, `KOSIS_API_KEY`, `DATA_GO_KR_API_KEY`)

`data/local/` 은 `.gitignore` 대상입니다. 키를 채팅·커밋에 넣지 마세요.

| 키 | 용도 |
|----|------|
| DART | ROE·OCF·재무 보강 |
| KRX | PyKRX 가격·시총 |
| FRED / KOSIS | Tier-2 매크로·레짐 보조 |
| data.go.kr | 공정위 순환출자 (REST, HTML 아님) |
"""
        )
