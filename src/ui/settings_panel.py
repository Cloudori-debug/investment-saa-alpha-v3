from __future__ import annotations

from pathlib import Path

import streamlit as st

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


def render_settings_page(data_dir: Path, *, focus: str | None = None) -> None:
    from src.ui.nav_shortcuts import (
        FOCUS_SETTINGS_API,
        FOCUS_SETTINGS_DATA,
        render_nav_hint,
    )

    render_nav_hint(focus)
    st.header("⚙️ API · 수집 설정")
    st.caption("키는 `data/local/user_secrets.json`에만 저장됩니다. Git에 올리지 마세요.")

    status = credential_status(data_dir)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open DART", "✅ 설정됨" if status["dart"] else "⬜ 미설정")
    c2.metric("PyKRX (KRX)", "✅ 설정됨" if status["krx"] else "⬜ 미설정")
    c3.metric("FRED", "✅ 설정됨" if status.get("fred") else "⬜ 미설정")
    c4.metric("KOSIS", "✅ 설정됨" if status.get("kosis") else "⬜ 미설정")

    saved = load_user_secrets(data_dir)
    tab_api, tab_defaults, tab_data, tab_help = st.tabs(["API 키", "수집 기본값", "데이터", "안내"])

    if focus == FOCUS_SETTINGS_DATA:
        with st.container(border=True):
            st.subheader("📍 데이터 (바로가기)")
            _render_data_tab(data_dir, saved)
        st.divider()

    if focus == FOCUS_SETTINGS_API:
        with st.container(border=True):
            st.subheader("📍 API 키 (바로가기)")
            st.caption("아래 **API 키** 탭에서 저장·테스트하세요.")
        st.divider()

    with tab_api:
        st.subheader("Open DART")
        st.markdown("[Open DART](https://opendart.fss.or.kr/) → 인증키 신청/관리 (40자)")
        dart_key = st.text_input(
            "DART API Key",
            value=saved.dart_api_key,
            type="password",
            placeholder="40자 인증키",
            help="환경변수 DART_API_KEY보다 UI 저장값이 우선 적용됩니다(저장 후).",
            key="settings_dart_key",
        )
        if saved.dart_api_key:
            st.caption(f"저장됨: `{mask_secret(saved.dart_api_key)}`")

        st.divider()
        st.subheader("PyKRX / KRX 로그인")
        st.markdown("PyKRX 1.2+ 일괄 수집용 [KRX](https://data.krx.co.kr/) 회원 ID/PW")
        krx_id = st.text_input("KRX ID", value=saved.krx_id, key="settings_krx_id")
        krx_pw = st.text_input(
            "KRX Password",
            value=saved.krx_pw,
            type="password",
            key="settings_krx_pw",
        )
        if saved.krx_id:
            st.caption(f"저장 ID: `{mask_secret(saved.krx_id, 2)}`")

        st.divider()
        st.subheader("FRED (Tier2 매크로)")
        st.markdown("[FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) — 미국 CPI·금리스프레드·HY OAS 등")
        fred_key = st.text_input(
            "FRED API Key",
            value=saved.fred_api_key,
            type="password",
            key="settings_fred_key",
        )
        if saved.fred_api_key:
            st.caption(f"저장됨: `{mask_secret(saved.fred_api_key)}`")

        st.divider()
        st.subheader("KOSIS (Tier2 매크로)")
        st.markdown("[KOSIS Open API](https://kosis.kr/openapi/) — 한국 CPI·경기지수 등")
        kosis_key = st.text_input(
            "KOSIS API Key",
            value=saved.kosis_api_key,
            type="password",
            key="settings_kosis_key",
        )
        if saved.kosis_api_key:
            st.caption(f"저장됨: `{mask_secret(saved.kosis_api_key)}`")

        st.divider()
        col_save, col_test_dart, col_test_krx, col_test_fred, col_test_kosis, col_clear = st.columns(6)
        with col_save:
            if st.button("💾 저장", type="primary", use_container_width=True):
                new_secrets = UserSecrets(
                    dart_api_key=dart_key.strip(),
                    krx_id=krx_id.strip(),
                    krx_pw=krx_pw.strip(),
                    fred_api_key=fred_key.strip(),
                    kosis_api_key=kosis_key.strip(),
                    pykrx_scope=saved.pykrx_scope,
                    dart_scope=saved.dart_scope,
                    default_as_of=saved.default_as_of,
                )
                path = save_user_secrets(data_dir, new_secrets)
                apply_secrets_to_env(data_dir, overwrite=True)
                st.success(f"저장 완료: `{path.name}`")
                st.rerun()
        with col_test_dart:
            if st.button("🔌 DART 테스트", use_container_width=True):
                ok, msg = test_dart_api_key(dart_key.strip() or saved.dart_api_key)
                st.success(msg) if ok else st.error(msg)
        with col_test_krx:
            if st.button("🔌 KRX 테스트", use_container_width=True):
                ok, msg = test_krx_credentials(
                    krx_id.strip() or saved.krx_id,
                    krx_pw.strip() or saved.krx_pw,
                )
                st.success(msg) if ok else st.error(msg)
        with col_test_fred:
            if st.button("🔌 FRED", use_container_width=True):
                ok, msg = test_fred_api_key(fred_key.strip() or saved.fred_api_key)
                st.success(msg) if ok else st.error(msg)
        with col_test_kosis:
            if st.button("🔌 KOSIS", use_container_width=True):
                ok, msg = test_kosis_api_key(kosis_key.strip() or saved.kosis_api_key)
                st.success(msg) if ok else st.error(msg)
        with col_clear:
            if st.button("🗑️ 키 삭제", use_container_width=True):
                clear_user_secrets(data_dir)
                for name in ("DART_API_KEY", "OPENDART_API_KEY", "KRX_ID", "KRX_PW", "FRED_API_KEY", "KOSIS_API_KEY"):
                    import os
                    os.environ.pop(name, None)
                st.warning("저장된 키를 삭제했습니다.")
                st.rerun()

    with tab_defaults:
        st.subheader("데이터 수집 기본값")
        pykrx_scope = st.selectbox(
            "PyKRX scope 기본값",
            ["liquid", "holdings", "all"],
            index=["liquid", "holdings", "all"].index(saved.pykrx_scope)
            if saved.pykrx_scope in {"liquid", "holdings", "all"}
            else 0,
            key="settings_pykrx_scope",
        )
        dart_scope = st.selectbox(
            "DART scope 기본값",
            ["prices", "liquid", "holdings"],
            index=["prices", "liquid", "holdings"].index(saved.dart_scope)
            if saved.dart_scope in {"prices", "liquid", "holdings"}
            else 0,
            key="settings_dart_scope",
        )
        default_as_of = st.text_input(
            "기본 as_of (YYYY-MM-DD, 비우면 market/prices에서 자동)",
            value=saved.default_as_of,
            key="settings_default_as_of",
        )
        if st.button("💾 기본값 저장", key="save_defaults"):
            new_secrets = UserSecrets(
                dart_api_key=saved.dart_api_key,
                krx_id=saved.krx_id,
                krx_pw=saved.krx_pw,
                pykrx_scope=pykrx_scope,
                dart_scope=dart_scope,
                default_as_of=default_as_of.strip(),
            )
            save_user_secrets(data_dir, new_secrets)
            st.success("기본값 저장 완료")
            st.rerun()

    with tab_data:
        from src.ui.universe_expand_panel import render_universe_expand_panel
        from src.ui.universe_preset_panel import render_universe_preset_panel

        render_universe_preset_panel(data_dir)
        st.divider()
        render_universe_expand_panel(data_dir)
        if focus != FOCUS_SETTINGS_DATA:
            st.divider()
            _render_data_tab(data_dir, saved)
        else:
            st.caption("📍 데이터 갱신·상태는 위 **바로가기** 블록을 사용하세요.")

    with tab_help:
        st.markdown(
            """
### 우선순위
1. **UI에 저장한 값** (`data/local/user_secrets.json`)
2. **환경변수** (`DART_API_KEY`, `KRX_ID`, `KRX_PW`, `FRED_API_KEY`, `KOSIS_API_KEY`)

### Tier2 매크로 (FRED + KOSIS)
| 출처 | 지표 |
|------|------|
| FRED | 미국 CPI YoY, 2Y-10Y 스프레드, HY OAS, 소비자심리(대리) |
| KOSIS | 한국 CPI YoY, 경기종합지수(대리) |
| 파생 | `real_rate_kr` = `korea_10y` − `cpi_kr_yoy` |

일일 파이프라인(`daily_pipeline.py`)에서 Tier2 갱신 후 시장지표·레짐 자동 동기화가 실행됩니다.
수동 레짐(`YELLOW_STABLE` 등)이 **만료 전**이면 override가 유지됩니다.
`outputs/regime_auto_suggestion.json`에서 산출 vs 적용 레짐을 확인하세요.

### PER/PBR vs ROE
| 출처 | 지표 |
|------|------|
| PyKRX | PER, PBR, 배당수익률 |
| Open DART | ROE, ROA, 부채비율, OCF, FCF, `usable_from_date` |

### PowerShell (대안)
```powershell
$env:DART_API_KEY="your_key"
$env:KRX_ID="your_id"
$env:KRX_PW="your_password"
```

### 저장 위치
```
"""
            + f"`{secrets_path(data_dir)}`"
        )


def _render_data_tab(data_dir: Path, prefs) -> None:
    cred = credential_status(data_dir)
    st.subheader("입력 데이터 상태")
    if not cred["dart"] or not cred["krx"]:
        st.info("PyKRX/DART 수집 전 **API 키** 탭에서 키를 저장하세요.")

    for label, files in (
        ("필수", ("market_indicators.csv", "positions.csv", "target_portfolio.csv")),
        ("나침반", ("compass_rules.yaml", "saa_profiles.yaml")),
        ("Alpha", ("universe.csv", "fundamentals.csv", "prices.csv", "alpha_scoring.yaml", "universe_filter.yaml")),
        ("확장·백테스트", ("macro_tier2.csv", "macro_tier2_history.csv", "tier2_provenance.json", "tier2_sources.yaml", "tier2_kosis_manual.yaml", "market_indicators_history.csv", "prices_history.csv")),
    ):
        st.markdown(f"**{label}**")
        for f in files:
            ok = (data_dir / f).exists()
            st.write(f"{'✅' if ok else '⬜'} `{f}`")

    st.divider()
    st.subheader("데이터 갱신")
    refresh_as_of = st.text_input(
        "as_of (YYYY-MM-DD)",
        value=prefs.default_as_of or "2026-06-17",
        key="refresh_as_of",
    )
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        if st.button("🔄 수동 갱신 (병합/검증)", key="settings_refresh"):
            from src.data_refresh.refresh_main import run_refresh

            try:
                report = run_refresh(data_dir, as_of=refresh_as_of or None)
                st.json(report)
                st.success("갱신 완료")
            except Exception as exc:
                st.error(str(exc))
    with col_d:
        if st.button("📊 Tier2 갱신 (FRED+KOSIS)", key="settings_tier2"):
            from src.data_refresh.tier2_refresh import refresh_macro_tier2

            try:
                t2 = refresh_macro_tier2(data_dir, as_of=refresh_as_of or None)
                st.json({
                    "updated": t2.updated_fields,
                    "preserved": t2.preserved_fields,
                    "api_fields_fetched": t2.api_fields_fetched,
                    "warnings": t2.warnings[:5],
                    "errors": t2.errors[:5],
                })
                st.success(f"macro_tier2 갱신 ({t2.as_of})")
            except Exception as exc:
                st.error(str(exc))
    with col_c:
        if st.button("🌐 시장지표 갱신 (KOSPI+글로벌)", key="settings_market"):
            from src.data_refresh.market_indicators_refresh import refresh_all_market_indicators

            try:
                mi = refresh_all_market_indicators(data_dir, as_of=refresh_as_of or None)
                st.json({"updated": mi.updated_fields, "warnings": mi.warnings, "errors": mi.errors})
                st.success(f"market_indicators 갱신 ({mi.as_of})")
            except Exception as exc:
                st.error(str(exc))
    with col_b:
        bulk_scope = st.selectbox(
            "PyKRX scope",
            ["liquid", "holdings", "all"],
            index=["liquid", "holdings", "all"].index(prefs.pykrx_scope)
            if prefs.pykrx_scope in {"liquid", "holdings", "all"}
            else 0,
            key="settings_bulk_scope",
        )
        max_t = st.number_input("max tickers (0=무제한)", min_value=0, value=0, step=50, key="settings_max_t")
        if st.button("📡 PyKRX 일괄 수집", key="settings_pykrx_bulk"):
            from src.data_refresh.pykrx_client import KrxCredentialsError
            from src.data_refresh.refresh_main import run_refresh

            try:
                report = run_refresh(
                    data_dir,
                    as_of=refresh_as_of or None,
                    pykrx_bulk=True,
                    pykrx_scope=bulk_scope,
                    pykrx_max_tickers=int(max_t) if max_t > 0 else None,
                )
                st.json(report)
                st.success("일괄 수집 완료")
            except KrxCredentialsError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Open DART 상세 재무")
    dart_scope = st.selectbox(
        "DART scope",
        ["prices", "liquid", "holdings"],
        index=["prices", "liquid", "holdings"].index(prefs.dart_scope)
        if prefs.dart_scope in {"prices", "liquid", "holdings"}
        else 0,
        key="settings_dart_scope_run",
    )
    if st.button("📑 DART 재무 보강", key="settings_dart_enrich"):
        from src.data_refresh.dart_client import DartCredentialsError
        from src.data_refresh.dart_enrich import enrich_fundamentals_from_dart

        try:
            result = enrich_fundamentals_from_dart(
                data_dir,
                as_of=refresh_as_of or None,
                scope=dart_scope,  # type: ignore[arg-type]
            )
            st.json({
                "requested": result.requested,
                "enriched": result.enriched,
                "skipped": result.skipped,
                "errors_sample": result.errors[:10],
            })
            st.success(f"DART 보강 {result.enriched}건 완료")
        except DartCredentialsError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(str(exc))

    st.divider()
    from src.ui.pmi_kr_manual_panel import render_pmi_kr_manual_panel

    render_pmi_kr_manual_panel(data_dir, data_dir.parent / "outputs")
