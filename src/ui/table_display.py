from __future__ import annotations

import hashlib
import html
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def table_height(row_count: int, *, row_px: int = 46, min_h: int = 260, max_h: int = 680) -> int:
    if row_count <= 0:
        return min_h
    return min(max_h, max(min_h, row_count * row_px + 52))


def target_approval_table_height(row_count: int) -> int:
    """Target 승인 탭 — 넓은 표 (행 수에 따라 자동 확장)."""
    return table_height(row_count, row_px=48, min_h=380, max_h=820)


def alpha_list_table_height(row_count: int) -> int:
    """알파 숏리스트·제외 종목 등 긴 목록."""
    return table_height(row_count, row_px=40, min_h=420, max_h=920)


def _pick_columns(df: pd.DataFrame, preferred: tuple[str, ...]) -> list[str]:
    return [c for c in preferred if c in df.columns]


def trade_actions_column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn("코드", width="small"),
        "name": st.column_config.TextColumn("종목명", width="medium"),
        "action": st.column_config.TextColumn("액션", width="small"),
        "allowed_size_pct": st.column_config.NumberColumn("허용(%)", format="%.2f", width="small"),
        "priority": st.column_config.TextColumn("우선", width="small"),
        "reason": st.column_config.TextColumn("사유", width="large"),
    }


def target_draft_column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn("코드", width="small"),
        "name": st.column_config.TextColumn("종목명", width="medium"),
        "target_weight": st.column_config.NumberColumn("목표(%)", format="%.2f", width="small"),
        "matrix_action": st.column_config.TextColumn("액션", width="small"),
        "change_reason": st.column_config.TextColumn("변경 사유", width="medium"),
        "reason": st.column_config.TextColumn("사유", width="large"),
    }


def kr_alpha_current_column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn("코드", width="small"),
        "name": st.column_config.TextColumn("종목명", width="medium"),
        "target_weight": st.column_config.NumberColumn("목표(%)", format="%.2f", width="small"),
        "min_weight": st.column_config.NumberColumn("하한(%)", format="%.2f", width="small"),
        "max_weight": st.column_config.NumberColumn("상한(%)", format="%.2f", width="small"),
    }


def target_changes_column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn("코드", width="small"),
        "name": st.column_config.TextColumn("종목명", width="medium"),
        "action": st.column_config.TextColumn("액션", width="small"),
        "old_weight": st.column_config.NumberColumn("이전(%)", format="%.2f", width="small"),
        "new_weight": st.column_config.NumberColumn("제안(%)", format="%.2f", width="small"),
        "reason": st.column_config.TextColumn("사유 코드", width="medium"),
        "paired_with": st.column_config.TextColumn("연결 티커", width="small"),
        "paired_with_name": st.column_config.TextColumn("연결 종목명", width="medium"),
    }


def replace_pairs_column_config() -> dict:
    return {
        "exit_ticker": st.column_config.TextColumn("퇴출 코드", width="small"),
        "exit_name": st.column_config.TextColumn("퇴출 종목", width="medium"),
        "candidate_ticker": st.column_config.TextColumn("편입 코드", width="small"),
        "candidate_name": st.column_config.TextColumn("편입 후보", width="medium"),
        "rank": st.column_config.NumberColumn("후보 순위", format="%d", width="small"),
        "reason": st.column_config.TextColumn("편입 사유", width="medium"),
    }


def target_proposal_diff_column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn("코드", width="small"),
        "name": st.column_config.TextColumn("종목명", width="medium"),
        "change_type": st.column_config.TextColumn("변경", width="small"),
        "old_weight": st.column_config.NumberColumn("이전(%)", format="%.2f", width="small"),
        "new_weight": st.column_config.NumberColumn("제안(%)", format="%.2f", width="small"),
        "asset_group": st.column_config.TextColumn("자산군", width="small"),
        "reason": st.column_config.TextColumn("사유", width="large"),
    }


def kr_alpha_comparison_column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn("코드", width="small"),
        "name": st.column_config.TextColumn("종목명", width="medium"),
        "current_pct": st.column_config.NumberColumn("현재 목표(%)", format="%.2f", width="small"),
        "draft_pct": st.column_config.NumberColumn("제안 목표(%)", format="%.2f", width="small"),
        "delta_pct": st.column_config.NumberColumn("차이(%p)", format="%.2f", width="small"),
        "matrix_action": st.column_config.TextColumn("draft 액션", width="small"),
        "change_reason": st.column_config.TextColumn("사유", width="medium"),
        "user_action": st.column_config.TextColumn("해야 할 일", width="large"),
    }


def target_portfolio_column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn("코드", width="small"),
        "name": st.column_config.TextColumn("종목명", width="medium"),
        "asset_group": st.column_config.TextColumn("자산군", width="small"),
        "target_weight": st.column_config.NumberColumn("목표(%)", format="%.2f", width="small"),
        "min_weight": st.column_config.NumberColumn("하한(%)", format="%.2f", width="small"),
        "max_weight": st.column_config.NumberColumn("상한(%)", format="%.2f", width="small"),
        "role": st.column_config.TextColumn("역할", width="small"),
    }


def _column_header(col: str, column_config: dict | None) -> str:
    cfg = (column_config or {}).get(col)
    if isinstance(cfg, dict):
        label = cfg.get("label")
        if label:
            return str(label)
    elif cfg is not None:
        label = getattr(cfg, "label", None)
        if label:
            return str(label)
    return str(col)


def _format_cell_value(val: Any, col: str, column_config: dict | None) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    cfg = (column_config or {}).get(col)
    fmt = None
    if isinstance(cfg, dict):
        fmt = (cfg.get("type_config") or {}).get("format")
    elif cfg is not None:
        fmt = getattr(cfg, "format", None)
    if fmt:
        try:
            return fmt % float(val)
        except (TypeError, ValueError):
            pass
    return str(val)


def _table_dom_id(key: str | None, view: pd.DataFrame) -> str:
    raw = f"{key or ''}|{list(view.columns)}|{len(view)}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"matp-tbl-{digest}"


def _render_copyable_html_table(
    view: pd.DataFrame,
    *,
    height: int,
    column_config: dict | None,
    table_id: str,
) -> None:
    headers = "".join(
        f"<th>{html.escape(_column_header(col, column_config))}</th>"
        for col in view.columns
    )
    body_rows: list[str] = []
    for _, row in view.iterrows():
        cells = "".join(
            f'<td tabindex="0">{html.escape(_format_cell_value(row[col], col, column_config))}</td>'
            for col in view.columns
        )
        body_rows.append(f"<tr>{cells}</tr>")

    doc = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "Source Sans Pro", sans-serif;
    font-size: 0.875rem;
    color: #fafafa;
    background: transparent;
  }}
  .wrap {{
    max-height: {height}px;
    overflow: auto;
    border: 1px solid rgba(250, 250, 250, 0.15);
    border-radius: 0.35rem;
  }}
  table.matp-copyable-table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: auto;
  }}
  table.matp-copyable-table th {{
    position: sticky;
    top: 0;
    z-index: 1;
    background: rgb(38, 39, 48);
    text-align: left;
    padding: 0.45rem 0.55rem;
    border-bottom: 1px solid rgba(250, 250, 250, 0.18);
    white-space: nowrap;
  }}
  table.matp-copyable-table td {{
    padding: 0.4rem 0.55rem;
    border-bottom: 1px solid rgba(250, 250, 250, 0.08);
    vertical-align: top;
    cursor: cell;
    user-select: text;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  table.matp-copyable-table tr:hover td {{
    background: rgba(255, 255, 255, 0.03);
  }}
  table.matp-copyable-table td.selected {{
    outline: 2px solid #4dabf7;
    outline-offset: -2px;
    background: rgba(77, 171, 247, 0.12);
  }}
</style>
</head>
<body>
  <div class="wrap" id="{table_id}-wrap">
    <table class="matp-copyable-table" id="{table_id}">
      <thead><tr>{headers}</tr></thead>
      <tbody>{"".join(body_rows)}</tbody>
    </table>
  </div>
  <script>
  (function() {{
    const doc = window.parent.document;
    const table = doc.getElementById("{table_id}");
    if (!table) return;
    table.querySelectorAll("td").forEach((td) => {{
      td.addEventListener("click", () => {{
        table.querySelectorAll("td.selected").forEach((el) => el.classList.remove("selected"));
        td.classList.add("selected");
        doc.__matpSelectedCellText = td.textContent.trim();
      }});
    }});
  }})();
  </script>
</body>
</html>
"""
    components.html(doc, height=height + 12, scrolling=False)


def show_dataframe_readable(
    df: pd.DataFrame,
    *,
    column_config: dict | None = None,
    columns: tuple[str, ...] | None = None,
    height: int | None = None,
    key: str | None = None,
) -> None:
    if df is None or df.empty:
        st.caption("표시할 행 없음")
        return
    if columns:
        use_cols = [c for c in columns if c in df.columns]
        view = df[use_cols].copy() if use_cols else df.copy()
    else:
        view = df.copy()
    h = height if height is not None else table_height(len(view))
    table_id = _table_dom_id(key, view)
    _render_copyable_html_table(view, height=h, column_config=column_config, table_id=table_id)
    st.caption("셀 클릭 → **Ctrl+C** (Mac: ⌘+C) 로 해당 칸 복사")


def show_trade_actions_table(
    df: pd.DataFrame,
    *,
    key_prefix: str = "trade",
    split_review: bool = True,
) -> None:
    if df is None or df.empty:
        st.caption("표시할 액션 없음")
        return

    cols = _pick_columns(
        df,
        ("ticker", "name", "action", "allowed_size_pct", "priority", "reason"),
    )
    cfg = trade_actions_column_config()

    if not split_review or "action" not in df.columns:
        show_dataframe_readable(df, column_config=cfg, columns=tuple(cols), key=f"{key_prefix}_all")
        return

    exec_df = df[~df["action"].eq("Review-only")]
    review_df = df[df["action"].eq("Review-only")]

    if not exec_df.empty:
        st.markdown("**Executable** — ETF·현금·채권")
        show_dataframe_readable(
            exec_df,
            column_config=cfg,
            columns=tuple(cols),
            key=f"{key_prefix}_exec",
        )

    if not review_df.empty:
        st.markdown("**Review-only** — kr_alpha (실행 금지)")
        st.caption("theoretical Replace/Trim — 실제 매도 신호 아님")
        show_dataframe_readable(
            review_df,
            column_config=cfg,
            columns=tuple(cols),
            key=f"{key_prefix}_review",
        )
