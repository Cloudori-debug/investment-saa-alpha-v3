from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.compass.profile_aliases import resolve_profile_name
from src.compass.saa_engine import get_group_bounds, get_saa_weights, load_saa_profiles
from src.models import VALID_ASSET_GROUPS
from src.ui.allocation_tickers import ASSET_GROUP_LABELS
from src.ui.helpers import load_output_csv

ALLOCATION_FLOW_MD = """
**한 줄 요약:** 별도 SAA 포트 + TAA 포트가 **아닙니다**.

```
SAA 프로필 (장기 코어 %)  →  + 국면 tilt  →  + 레짐 tilt  →  bounds 정규화  →  자산군 최종 %
                                                              ↓
                              target_portfolio 템플릿 비율로 종목 분해  →  generated_target_portfolio
```

- **SAA** = 레짐과 무관한 **기준 슬롯** (현금·베타·알파 등)
- **TAA** = 오늘 레짐/국면에 따른 **±%p 조정**
- **종목 티커·실제 보유·Gap** = **종합 포트** 메뉴에서만 확인 (중복 방지)
"""


def _profile_table(profiles: dict, name: str) -> pd.DataFrame:
    saa = get_saa_weights(profiles, name)
    bounds = get_group_bounds(profiles, name)
    rows = []
    for group in sorted(VALID_ASSET_GROUPS):
        b = bounds.get(group, {"min": 0, "max": 100})
        rows.append(
            {
                "자산군": ASSET_GROUP_LABELS.get(group, group),
                "group": group,
                "SAA(%)": saa.get(group, 0.0),
                "min": b["min"],
                "max": b["max"],
            }
        )
    return pd.DataFrame(rows)


def _flow_table(allocation: pd.DataFrame) -> pd.DataFrame:
    alloc = allocation.copy()
    for col in ("saa_weight", "phase_tilt", "regime_tilt", "final_target"):
        if col in alloc.columns:
            alloc[col] = pd.to_numeric(alloc[col], errors="coerce").fillna(0)
    if "asset_group" in alloc.columns:
        alloc["자산군"] = alloc["asset_group"].map(ASSET_GROUP_LABELS).fillna(alloc["asset_group"])
    alloc["TAA합±"] = alloc.get("phase_tilt", 0) + alloc.get("regime_tilt", 0)
    cols = ["자산군", "SAA(%)", "국면±", "레짐±", "TAA합±", "최종(%)"]
    out = pd.DataFrame(
        {
            "자산군": alloc["자산군"],
            "SAA(%)": alloc.get("saa_weight", 0),
            "국면±": alloc.get("phase_tilt", 0),
            "레짐±": alloc.get("regime_tilt", 0),
            "TAA합±": alloc["TAA합±"],
            "최종(%)": alloc.get("final_target", 0),
        }
    )
    return out[cols]


def render_allocation_page(data_dir: Path, output_dir: Path, profile: str) -> None:
    st.header("📐 SAA · TAA — 자산배분")
    st.caption("SAA 기준 + TAA tilt = **하나의 목표 배분**. 종목·Gap은 **종합 포트**에서만 봅니다.")

    st.markdown(ALLOCATION_FLOW_MD)

    profiles = load_saa_profiles(data_dir / "saa_profiles.yaml")
    canonical = resolve_profile_name(profiles, profile)
    profile_def = profiles.get("profiles", {}).get(canonical, {})
    saa_df = _profile_table(profiles, profile)

    allocation = load_output_csv(output_dir, "target_asset_allocation.csv")

    tab_flow, tab_saa_ref, tab_tilt_rules, tab_hakedaka = st.tabs(
        ["배분 흐름 (오늘)", "SAA 기준 (프로필)", "Tilt 규칙", "하케다카×kr_alpha"]
    )

    with tab_flow:
        st.info(profile_def.get("description", canonical))
        if allocation is None or allocation.empty:
            st.warning("**전체 분석 실행** 후 SAA→TAA→최종% 흐름이 표시됩니다.")
            st.dataframe(
                saa_df[["자산군", "SAA(%)", "min", "max"]],
                use_container_width=True,
                hide_index=True,
            )
            st.caption("위는 SAA **기준만** (TAA 미적용)")
        else:
            if "applied_regime" in allocation.columns:
                c1, c2, c3 = st.columns(3)
                c1.metric("프로필", canonical)
                c2.metric("적용 레짐", str(allocation["applied_regime"].iloc[0]))
                c3.metric(
                    "최종 합계",
                    f"{pd.to_numeric(allocation['final_target'], errors='coerce').fillna(0).sum():.1f}%",
                )
            flow = _flow_table(allocation)
            st.dataframe(flow, use_container_width=True, hide_index=True)
            st.bar_chart(flow.set_index("자산군")[["SAA(%)", "최종(%)"]], height=220)
            changed = flow[flow["TAA합±"].abs() >= 0.01]
            if not changed.empty:
                st.markdown("**오늘 TAA가 움직인 자산군**")
                st.dataframe(changed, use_container_width=True, hide_index=True)
            else:
                st.caption("오늘 적용 레짐·국면에서 TAA tilt = 0 (SAA = 최종)")

        st.info("📁 **종목별 목표·실제 보유·Gap** → 상단 메뉴 **종합 포트**")

    with tab_saa_ref:
        st.markdown("레짐과 무관한 **전략적 기준**. TAA는 이 값에 ± 합니다.")
        m1, m2 = st.columns(2)
        m1.metric("프로필", canonical)
        m2.metric("SAA 합계", f"{float(saa_df['SAA(%)'].sum()):.1f}%")
        st.dataframe(saa_df[["자산군", "SAA(%)", "min", "max"]], use_container_width=True, hide_index=True)

    with tab_tilt_rules:
        st.caption("참고용 YAML — 실제 적용값은 **배분 흐름** 탭의 국면±·레짐±")
        tab_regime, tab_phase = st.tabs(["레짐 tilt", "국면 tilt"])
        with tab_regime:
            tilts = profiles.get("taa_tilts", {})
            if tilts:
                regime_df = pd.DataFrame(tilts).T
                regime_df.columns = [ASSET_GROUP_LABELS.get(c, c) for c in regime_df.columns]
                st.dataframe(regime_df, use_container_width=True)
        with tab_phase:
            phase_tilts = profiles.get("phase_tilts", {})
            if phase_tilts:
                phase_df = pd.DataFrame(phase_tilts).T
                phase_df.columns = [ASSET_GROUP_LABELS.get(c, c) for c in phase_df.columns]
                st.dataframe(phase_df, use_container_width=True)

    with tab_hakedaka:
        from src.ui.helpers import load_markdown, load_output_json

        overlay = load_output_json(output_dir, "hakedaka_compass_overlay.json")
        note = load_markdown(output_dir, "hakedaka_taa_note.md")
        if overlay:
            st.info(overlay.get("stance_note", ""))
            c1, c2 = st.columns(2)
            c1.metric("알파∩하케다카", overlay.get("alpha_shortlist_overlap", 0))
            c2.metric("DART verified A", overlay.get("dart_verified_a_count", 0))
            cross = overlay.get("kr_alpha_cross_candidates") or []
            if cross:
                st.markdown("**QVM 숏리스트 ∩ 하케다카**")
                st.dataframe(pd.DataFrame(cross), use_container_width=True, hide_index=True)
            st.caption(overlay.get("integration_hint", ""))
        if note:
            st.markdown(note)
        if not overlay and not note:
            st.caption("전체 분석 실행 후 하케다카 DART 검증·알파 교차 결과가 표시됩니다.")
