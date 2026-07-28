from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.data_loader import _normalize_ticker


def summarize_universe(data_dir: Path) -> dict[str, int | str]:
    path = data_dir / "universe.csv"
    if not path.exists():
        return {"total": 0, "common": 0, "prices": 0, "fundamentals": 0, "as_of": ""}

    uni = pd.read_csv(path, dtype=str, keep_default_na=False)
    common = uni[
        (uni["security_type"] == "common_stock")
        & (uni["is_preferred"].astype(str).str.lower() == "false")
        & (uni["is_etf_etn"].astype(str).str.lower() == "false")
    ]

    prices_n = 0
    prices_as_of = ""
    prices_path = data_dir / "prices.csv"
    if prices_path.exists():
        prices = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
        prices_n = len(prices)
        if "date" in prices.columns and not prices.empty:
            prices_as_of = str(prices["date"].max())

    fund_n = 0
    fund_path = data_dir / "fundamentals.csv"
    if fund_path.exists():
        fund_n = len(pd.read_csv(fund_path, dtype=str, keep_default_na=False))

    return {
        "total": len(uni),
        "common": len(common),
        "prices": prices_n,
        "fundamentals": fund_n,
        "as_of": prices_as_of,
    }


def render_universe_expand_panel(data_dir: Path) -> None:
    """설정·데이터 탭 — PyKRX 유니버스 확장."""
    from src.settings.user_secrets import credential_status, load_user_secrets

    st.subheader("🌐 Alpha 유니버스 확장 (PyKRX)")
    st.caption(
        "KOSPI 전 종목 → `universe.csv` · 유동성 통과 common → `prices.csv` + `fundamentals.csv` · "
        "Alpha 스크리너는 **prices에 있는 종목**을 스코어합니다."
    )

    cred = credential_status(data_dir)
    if not cred["krx"]:
        st.warning("**KRX ID/PW**가 없습니다. 위 **API 키** 탭에서 저장하세요.")
    else:
        st.success("KRX 자격증명 설정됨")

    stats = summarize_universe(data_dir)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("universe.csv", stats["total"])
    c2.metric("보통주", stats["common"])
    c3.metric("prices.csv", stats["prices"])
    c4.metric("fundamentals", stats["fundamentals"])
    if stats["as_of"]:
        st.caption(f"시세 기준일: `{stats['as_of']}`")

    prefs = load_user_secrets(data_dir)
    as_of = st.text_input(
        "as_of (YYYY-MM-DD)",
        value=prefs.default_as_of or "2026-06-17",
        key="universe_expand_as_of",
    )
    scope = st.selectbox(
        "수집 scope",
        ["liquid", "all", "holdings"],
        index=["liquid", "holdings", "all"].index(prefs.pykrx_scope)
        if prefs.pykrx_scope in {"liquid", "holdings", "all"}
        else 0,
        format_func=lambda s: {
            "liquid": "liquid (권장) — 시총·거래대금 필터 통과 common",
            "all": "all — 유동성 필터 없이 common 전체 (느림)",
            "holdings": "holdings — kr_alpha 보유·target만",
        }[s],
        key="universe_expand_scope",
    )
    max_t = st.number_input(
        "max tickers (0=무제한, 테스트용)",
        min_value=0,
        value=0,
        step=50,
        key="universe_expand_max",
    )
    enrich_dart = st.checkbox(
        "수집 후 DART 재무 보강 (ROE·OCF·PIT, 느림)",
        value=False,
        key="universe_expand_dart",
    )

    st.markdown(
        """
| scope | universe.csv | prices 대상 | Alpha 스크린 |
|-------|--------------|-------------|--------------|
| **liquid** | KOSPI ~900+ | ~200~400종 | **권장** |
| all | KOSPI ~900+ | common 전체 | 매우 느림 |
| holdings | 병합 유지 | 보유·target만 | 빠름 |
"""
    )

    if st.button("📡 PyKRX 유니버스 확장 실행", type="primary", key="universe_expand_run"):
        from src.data_refresh.pykrx_client import KrxCredentialsError
        from src.data_refresh.refresh_main import run_refresh

        with st.spinner("PyKRX 수집 중… (수백 종목이면 10~30분 소요)"):
            try:
                report = run_refresh(
                    data_dir,
                    as_of=as_of or None,
                    pykrx_bulk=True,
                    pykrx_scope=scope,
                    pykrx_max_tickers=int(max_t) if max_t > 0 else None,
                    enrich_dart=enrich_dart,
                    dart_scope="liquid" if scope == "liquid" else "prices",
                    refresh_kospi_market=True,
                )
                st.session_state["universe_expand_report"] = report
                st.success("수집 완료 — 사이드바 **전체 분석 실행**으로 Alpha 갱신")
                st.rerun()
            except KrxCredentialsError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(str(exc))

    report = st.session_state.get("universe_expand_report")
    if report:
        st.json(report)
        bulk = next((s.get("pykrx_bulk") for s in report.get("steps", []) if "pykrx_bulk" in s), None)
        if bulk:
            st.info(
                f"universe **{bulk.get('universe_count')}** · "
                f"prices **{bulk.get('prices_count')}** · "
                f"fundamentals **{bulk.get('fundamentals_count')}** · "
                f"DART **{bulk.get('dart_enriched', 0)}**"
            )
