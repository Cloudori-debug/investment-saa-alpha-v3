from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.data_loader import (
    apply_prices_from_csv,
    dataframe_to_positions,
    enrich_positions_dataframe,
    load_positions,
    positions_to_dataframe,
    write_positions,
)
from src.models import VALID_ASSET_GROUPS
from src.position_lookup import lookup_ticker_metadata
from src.ui.copyable_table import render_copyable_table, target_portfolio_table_height
from src.ui.table_display import target_portfolio_column_config

ASSET_GROUP_LABELS: dict[str, str] = {
    "cash_short_bond": "현금·채권",
    "domestic_beta": "국내 베타",
    "global_beta": "글로벌 베타",
    "fx_dollar": "달러·FX",
    "hedge_alt": "헤지(금 등)",
    "income_alt": "인컴",
    "kr_alpha": "국내 알파",
}

ASSET_GROUP_ORDER = list(ASSET_GROUP_LABELS.keys())
EDITOR_COLUMNS = [
    "ticker",
    "name",
    "asset_group",
    "quantity",
    "current_price",
    "current_value",
    "weight_pct",
    "sector",
    "style",
    "avg_price",
]


def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _group_rollup(df: pd.DataFrame, weight_col: str) -> pd.DataFrame:
    if df is None or df.empty or weight_col not in df.columns:
        return pd.DataFrame(columns=["asset_group", "label", "weight_pct"])
    grouped = (
        df.assign(weight_pct=pd.to_numeric(df[weight_col], errors="coerce").fillna(0))
        .groupby("asset_group", as_index=False)["weight_pct"]
        .sum()
    )
    grouped["label"] = grouped["asset_group"].map(ASSET_GROUP_LABELS).fillna(grouped["asset_group"])
    grouped["weight_pct"] = grouped["weight_pct"].round(2)
    order = {g: i for i, g in enumerate(ASSET_GROUP_ORDER)}
    grouped["_ord"] = grouped["asset_group"].map(order).fillna(99)
    return grouped.sort_values("_ord").drop(columns="_ord")


def _load_optimal_target(output_dir: Path, data_dir: Path) -> tuple[pd.DataFrame | None, str]:
    generated = _load_csv(output_dir / "generated_target_portfolio.csv")
    if generated is not None and not generated.empty:
        generated = generated.copy()
        generated["target_weight"] = pd.to_numeric(generated["target_weight"], errors="coerce").fillna(0)
        return generated, "나침반 레짐 + SAA/TAA 자동 분해 (`generated_target_portfolio.csv`)"
    template = _load_csv(data_dir / "target_portfolio.csv")
    if template is not None and not template.empty:
        template = template.copy()
        template["target_weight"] = pd.to_numeric(template["target_weight"], errors="coerce").fillna(0)
        return template, "설계 템플릿 (`target_portfolio.csv`) — 전체 분석 실행 후 분해 결과 권장"
    return None, ""


def _build_gap_table(actual: pd.DataFrame, optimal: pd.DataFrame) -> pd.DataFrame:
    left = actual[["ticker", "name", "asset_group", "weight_pct"]].copy()
    left = left.rename(columns={"weight_pct": "current_weight"})
    right = optimal[["ticker", "name", "asset_group", "target_weight"]].copy()
    merged = pd.merge(left, right, on=["ticker", "asset_group"], how="outer", suffixes=("_act", "_opt"))
    if "name_act" in merged.columns:
        merged["name"] = merged["name_act"].fillna(merged.get("name_opt", ""))
    elif "name" not in merged.columns:
        merged["name"] = merged.get("name_opt", "")
    merged["current_weight"] = pd.to_numeric(merged["current_weight"], errors="coerce").fillna(0).round(2)
    merged["target_weight"] = pd.to_numeric(merged["target_weight"], errors="coerce").fillna(0).round(2)
    merged["gap"] = (merged["target_weight"] - merged["current_weight"]).round(2)
    cols = ["ticker", "name", "asset_group", "current_weight", "target_weight", "gap"]
    return merged[cols].sort_values(["asset_group", "gap"], ascending=[True, False])


def exit_status_label_for_gap(
    *,
    on_board: bool,
    targets_missing: bool,
    exit_leg: str | None,
    fund_proximity_pct: float | None = None,
    val_proximity_pct: float | None = None,
) -> str:
    """Display-only TP reach status for Gap table (not yaml 설정 여부)."""
    if not on_board:
        return "—"
    if targets_missing:
        return "목표 미설정"
    leg = str(exit_leg or "NONE").strip().upper()
    if leg in {"FUND", "VAL", "BOTH"}:
        return f"도달({leg})"
    from src.alpha.take_profit_thesis import format_proximity_gap_suffix

    suffix = format_proximity_gap_suffix(fund_proximity_pct, val_proximity_pct)
    return f"미도달 {suffix}".strip() if suffix else "미도달"


def enrich_gap_with_exit_status(gap_df: pd.DataFrame, board: pd.DataFrame | None) -> pd.DataFrame:
    """Merge read-only 익절상태 onto Gap rows from alpha_signal_board (no Gap recalculation)."""
    out = gap_df.copy()
    if out.empty:
        out["익절상태"] = []
        return out

    def _missing(v) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"true", "1", "yes"}

    def _opt_float(v) -> float | None:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        s = str(v).strip()
        if s == "" or s.lower() in {"nan", "none"}:
            return None
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    lookup: dict[str, tuple[bool, str, float | None, float | None]] = {}
    if board is not None and not board.empty and "ticker" in board.columns:
        for _, row in board.iterrows():
            t = str(row.get("ticker", "")).strip()
            if not t:
                continue
            lookup[t] = (
                _missing(row.get("targets_missing")),
                str(row.get("exit_leg", "NONE")),
                _opt_float(row.get("fund_proximity_pct")),
                _opt_float(row.get("val_proximity_pct")),
            )

    labels: list[str] = []
    for t in out["ticker"].astype(str).str.strip():
        if t in lookup:
            missing, leg, fp, vp = lookup[t]
            labels.append(
                exit_status_label_for_gap(
                    on_board=True,
                    targets_missing=missing,
                    exit_leg=leg,
                    fund_proximity_pct=fp,
                    val_proximity_pct=vp,
                )
            )
        else:
            labels.append(exit_status_label_for_gap(on_board=False, targets_missing=False, exit_leg=None))
    out["익절상태"] = labels
    cols = [c for c in out.columns if c != "익절상태"]
    # Place after gap when present.
    if "gap" in cols:
        i = cols.index("gap") + 1
        cols = cols[:i] + ["익절상태"] + cols[i:]
    else:
        cols = cols + ["익절상태"]
    return out[cols]


def _file_cache_key(*paths: Path) -> str:
    parts: list[str] = []
    for path in paths:
        if path.exists():
            parts.append(f"{path}:{path.stat().st_mtime_ns}")
        else:
            parts.append(f"{path}:missing")
    return "|".join(parts)


def _empty_row() -> dict[str, object]:
    return {
        "ticker": "",
        "name": "",
        "asset_group": "kr_alpha",
        "quantity": 0,
        "current_price": "",
        "current_value": 0,
        "weight_pct": 0.0,
        "sector": "",
        "style": "",
        "avg_price": "",
    }


def _prepare_editor_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([_empty_row()])
    out = df.copy()
    for col in EDITOR_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    qty = pd.to_numeric(out["quantity"], errors="coerce").fillna(0)
    out["quantity"] = qty.round(0).astype(int)
    return out[EDITOR_COLUMNS]


def _non_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["ticker"].astype(str).str.strip() != ""].copy()


def _render_portfolio_view_tab(preview: pd.DataFrame) -> None:
    if preview.empty:
        st.info("보유 종목이 없습니다. **편집** 탭에서 종목을 추가하세요.")
        return
    show = preview[
        [c for c in ("ticker", "name", "asset_group", "quantity", "current_price", "current_value", "weight_pct") if c in preview.columns]
    ].copy()
    show["asset_group"] = show["asset_group"].map(ASSET_GROUP_LABELS).fillna(show["asset_group"])
    st.dataframe(
        show,
        column_config={
            "ticker": st.column_config.TextColumn("코드", width="small"),
            "name": st.column_config.TextColumn("종목명"),
            "asset_group": st.column_config.TextColumn("자산군"),
            "quantity": st.column_config.NumberColumn("보유수량(주)", format="%d"),
            "current_price": st.column_config.NumberColumn("현재가", format="%.0f"),
            "current_value": st.column_config.NumberColumn("평가금액", format="%.0f"),
            "weight_pct": st.column_config.NumberColumn("비중(%)", format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
    )


def _render_portfolio_edit_tab(data_dir: Path, edit_df: pd.DataFrame) -> pd.DataFrame:
    """Unified add / delete / quantity edit in one table-like layout."""
    st.caption(
        "표에서 **보유수량**을 바로 수정 · 각 행 **−** 삭제 · 맨 아래 빈 줄에 코드·수량 입력 후 **＋** 추가"
    )

    working = _non_empty_rows(edit_df)
    if working.empty:
        working = pd.DataFrame(columns=EDITOR_COLUMNS)
    else:
        working = enrich_positions_dataframe(working)

    header = st.columns([0.45, 1.1, 2.2, 1.6, 1.1, 1.0, 0.9])
    header[0].markdown("**−**")
    header[1].markdown("**코드**")
    header[2].markdown("**종목명**")
    header[3].markdown("**자산군**")
    header[4].markdown("**보유수량**")
    header[5].markdown("**현재가**")
    header[6].markdown("**비중%**")

    updated_rows: list[dict[str, object]] = []
    group_options = sorted(VALID_ASSET_GROUPS)

    for idx, row in working.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        if not ticker:
            continue
        cols = st.columns([0.45, 1.1, 2.2, 1.6, 1.1, 1.0, 0.9])
        with cols[0]:
            if st.button("−", key=f"pf_rm_{ticker}_{idx}", help=f"{ticker} 삭제"):
                remain = working.drop(index=idx)
                st.session_state["portfolio_edit_df"] = _prepare_editor_df(remain)
                st.rerun()
        with cols[1]:
            st.text(ticker)
        with cols[2]:
            st.text(str(row.get("name", "")))
        with cols[3]:
            ag = str(row.get("asset_group") or "kr_alpha")
            group_idx = group_options.index(ag) if ag in group_options else group_options.index("kr_alpha")
            asset_group = st.selectbox(
                "자산군",
                group_options,
                index=group_idx,
                key=f"pf_grp_{ticker}_{idx}",
                label_visibility="collapsed",
            )
        with cols[4]:
            qty = st.number_input(
                "보유수량",
                min_value=0,
                step=1,
                value=int(pd.to_numeric(row.get("quantity"), errors="coerce") or 0),
                format="%d",
                key=f"pf_qty_{ticker}_{idx}",
                label_visibility="collapsed",
            )
        price = pd.to_numeric(row.get("current_price"), errors="coerce")
        weight = pd.to_numeric(row.get("weight_pct"), errors="coerce")
        with cols[5]:
            st.text(f"{int(price):,}" if pd.notna(price) and price else "—")
        with cols[6]:
            st.text(f"{weight:.2f}" if pd.notna(weight) else "—")

        new_row = row.to_dict()
        new_row["asset_group"] = asset_group
        new_row["quantity"] = int(qty)
        updated_rows.append(new_row)

    st.markdown("---")
    add_cols = st.columns([0.45, 1.1, 2.2, 1.6, 1.1, 2.0])
    with add_cols[0]:
        add_clicked = st.button("＋", key="pf_add_plus", help="신규 종목 추가")
    with add_cols[1]:
        new_ticker = st.text_input(
            "신규 코드",
            key="pf_add_ticker_inline",
            placeholder="005830",
            label_visibility="collapsed",
        )
    with add_cols[2]:
        st.text_input(
            "종목명",
            key="pf_add_name_hint",
            placeholder="＋ 누르면 자동 조회",
            disabled=True,
            label_visibility="collapsed",
        )
    with add_cols[3]:
        new_group = st.selectbox(
            "자산군",
            group_options,
            index=group_options.index("kr_alpha"),
            key="pf_add_group_inline",
            label_visibility="collapsed",
        )
    with add_cols[4]:
        new_qty = st.number_input(
            "신규 수량",
            min_value=0,
            step=1,
            value=0,
            format="%d",
            key="pf_add_qty_inline",
            label_visibility="collapsed",
        )
    with add_cols[5]:
        st.caption("코드·수량 입력 후 ＋")

    if add_clicked:
        code = str(new_ticker).strip()
        if not code:
            st.error("종목코드를 입력하세요.")
        else:
            try:
                meta = lookup_ticker_metadata(data_dir, code)
                row = _empty_row()
                row["ticker"] = meta["ticker"]
                row["name"] = meta["name"]
                row["sector"] = meta["sector"]
                row["style"] = meta["style"]
                row["asset_group"] = meta["asset_group"] or new_group
                if meta.get("current_price"):
                    row["current_price"] = meta["current_price"]
                row["quantity"] = int(new_qty)
                base = pd.DataFrame(updated_rows) if updated_rows else pd.DataFrame(columns=EDITOR_COLUMNS)
                dup = base[base["ticker"].astype(str) == str(meta["ticker"])]
                if not dup.empty:
                    idx = dup.index[0]
                    base.at[idx, "quantity"] = int(new_qty)
                    if int(new_qty) > 0:
                        base.at[idx, "name"] = meta["name"]
                else:
                    base = pd.concat([base, pd.DataFrame([row])], ignore_index=True)
                st.session_state["portfolio_edit_df"] = _prepare_editor_df(base)
                st.success(f"{meta['ticker']} {meta['name']} 반영")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if updated_rows:
        return _prepare_editor_df(pd.DataFrame(updated_rows))
    return _prepare_editor_df(pd.DataFrame([_empty_row()]))


def _render_portfolio_price_tab(edit_df: pd.DataFrame, prices_path: Path, price_stats: dict) -> None:
    applied = int(price_stats.get("applied", 0))
    as_of = str(price_stats.get("as_of", "") or "—")
    missing = price_stats.get("missing_tickers") or []
    if prices_path.exists():
        st.caption(f"시세 반영 **{applied}**종 · 기준일 `{as_of}`")
        if missing:
            st.warning("시세 없음: " + ", ".join(str(t) for t in missing[:8]))
    else:
        st.warning("`data/prices.csv` 없음 — **설정 → 데이터**에서 PyKRX 수집")
    if st.button("시세 다시 불러오기", key="pf_refresh_px", use_container_width=True):
        refreshed, stats = apply_prices_from_csv(edit_df, prices_path)
        st.session_state["portfolio_edit_df"] = _prepare_editor_df(refreshed)
        st.session_state["portfolio_price_stats"] = stats
        st.rerun()


def _reset_portfolio_state(base_df: pd.DataFrame, cache_key: str, price_stats: dict) -> None:
    st.session_state["portfolio_cache_key"] = cache_key
    st.session_state["portfolio_edit_df"] = _prepare_editor_df(base_df)
    st.session_state["portfolio_price_stats"] = price_stats


def render_portfolio_page(data_dir: Path, output_dir: Path) -> None:
    st.subheader("포트폴리오 — 실제 vs 목표 (티커)")
    st.caption(
        "왼쪽 **실제 보유** · 오른쪽 **TAA 반영 최종 목표** · "
        "자산군 SAA→TAA %는 **SAA·TAA** 메뉴 · 저장 후 **전체 분석 실행**"
    )

    positions_path = data_dir / "positions.csv"
    prices_path = data_dir / "prices.csv"
    try:
        positions = load_positions(positions_path)
    except Exception as exc:
        st.error(f"positions.csv 읽기 실패: {exc}")
        return

    base_df, price_stats = apply_prices_from_csv(
        positions_to_dataframe(positions),
        prices_path,
    )
    cache_key = _file_cache_key(positions_path, prices_path)
    if st.session_state.get("portfolio_cache_key") != cache_key:
        _reset_portfolio_state(base_df, cache_key, price_stats)

    edit_df = st.session_state.get("portfolio_edit_df", _prepare_editor_df(base_df))
    price_stats = st.session_state.get("portfolio_price_stats", price_stats)
    optimal_df, optimal_source = _load_optimal_target(output_dir, data_dir)

    preview = enrich_positions_dataframe(edit_df)
    total_value = float(preview["current_value"].sum()) if not preview.empty else 0.0
    m1, m2, m3 = st.columns(3)
    m1.metric("실제 평가합", f"{total_value:,.0f}원")
    m2.metric("보유 종목", f"{len(preview)}")
    if optimal_df is not None:
        m3.metric("목표 종목", f"{len(optimal_df)}")
    else:
        m3.metric("목표 종목", "—", delta="전체 분석 실행 필요")

    left, right = st.columns(2)

    with left:
        st.subheader("내 실제 포트폴리오")

        tab_view, tab_edit, tab_px = st.tabs(["📋 요약", "✏️ 편집", "🔄 시세"])

        with tab_view:
            _render_portfolio_view_tab(preview)

        edited = edit_df
        with tab_edit:
            edited = _render_portfolio_edit_tab(data_dir, edit_df)
            st.session_state["portfolio_edit_df"] = edited
            live_preview = enrich_positions_dataframe(edited)
            if not live_preview.empty:
                live_total = float(live_preview["current_value"].sum())
                if live_total > 0:
                    rollup = _group_rollup(live_preview, "weight_pct")
                    if not rollup.empty:
                        st.caption(f"편집 미리보기 · 평가합 {live_total:,.0f}원")
                        st.bar_chart(rollup.set_index("label")["weight_pct"], height=140)

            c_save, c_reload = st.columns(2)
            with c_save:
                if st.button("💾 실제 포트 저장", type="primary", use_container_width=True, key="pf_save"):
                    try:
                        cleaned = edited[edited["ticker"].astype(str).str.strip() != ""].copy()
                        rows = dataframe_to_positions(cleaned)
                        if not rows:
                            st.error("저장할 종목이 없습니다.")
                        else:
                            write_positions(rows, positions_path, backup=True)
                            st.session_state.pop("portfolio_edit_df", None)
                            st.session_state.pop("portfolio_cache_key", None)
                            st.success(f"저장 완료 — {len(rows)}종목")
                            st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            with c_reload:
                if st.button("↩️ 파일에서 다시 불러오기", use_container_width=True, key="pf_reload"):
                    st.session_state.pop("portfolio_edit_df", None)
                    st.session_state.pop("portfolio_cache_key", None)
                    st.rerun()

        with tab_px:
            _render_portfolio_price_tab(
                st.session_state.get("portfolio_edit_df", edited),
                prices_path,
                price_stats,
            )

        live_preview = enrich_positions_dataframe(st.session_state.get("portfolio_edit_df", edit_df))

    with right:
        st.subheader("시스템 목표 포트폴리오")
        if optimal_df is None:
            st.info("사이드바 **전체 분석 실행** 후 `generated_target_portfolio.csv`가 생성됩니다.")
        else:
            st.caption(optimal_source)
            show_cols = [
                c
                for c in (
                    "ticker", "name", "asset_group", "target_weight", "min_weight", "max_weight", "role"
                )
                if c in optimal_df.columns
            ]
            render_copyable_table(
                optimal_df[show_cols],
                height=target_portfolio_table_height(len(optimal_df)),
                key="optimal_target",
                column_config=target_portfolio_column_config(),
            )
            opt_rollup = _group_rollup(optimal_df, "target_weight")
            if not opt_rollup.empty:
                st.caption("자산군 목표 비중 (티커 합산)")
                st.bar_chart(opt_rollup.set_index("label")["weight_pct"], height=180)

    st.divider()
    st.subheader("실제 vs 목표 Gap")
    st.caption(
        "익절상태 = 목표 미설정 / 미도달(근접도%) / 도달(FUND·VAL·BOTH) — "
        "상세 설명은 알파 → 보유 리뷰 참고"
    )
    if optimal_df is None or live_preview.empty:
        st.caption("실제 포트 저장 + 전체 분석 실행 후 비교표가 채워집니다.")
    else:
        gap_path = output_dir / "current_vs_target.csv"
        board = _load_csv(output_dir / "alpha_signal_board.csv")
        if gap_path.exists():
            gap_df = pd.read_csv(gap_path, dtype=str, keep_default_na=False)
            for col in ("current_weight", "target_weight", "gap"):
                if col in gap_df.columns:
                    gap_df[col] = pd.to_numeric(gap_df[col], errors="coerce").fillna(0)
        else:
            gap_df = _build_gap_table(live_preview, optimal_df)
        gap_df = enrich_gap_with_exit_status(gap_df, board)
        st.dataframe(gap_df, use_container_width=True, height=320)

        act_roll = _group_rollup(live_preview, "weight_pct")
        opt_roll = _group_rollup(optimal_df, "target_weight")
        if not act_roll.empty and not opt_roll.empty:
            compare = pd.merge(
                act_roll[["asset_group", "label", "weight_pct"]],
                opt_roll[["asset_group", "weight_pct"]],
                on="asset_group",
                how="outer",
                suffixes=("_actual", "_target"),
            ).fillna(0)
            compare["gap"] = (compare["weight_pct_target"] - compare["weight_pct_actual"]).round(2)
            st.dataframe(
                compare.rename(
                    columns={
                        "label": "자산군",
                        "weight_pct_actual": "실제%",
                        "weight_pct_target": "목표%",
                        "gap": "Gap(%p)",
                    }
                )[["자산군", "실제%", "목표%", "Gap(%p)"]],
                use_container_width=True,
                hide_index=True,
            )
