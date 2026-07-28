from __future__ import annotations

import hashlib
import html as html_module
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.ui.table_display import _column_header, _format_cell_value, table_height


def _prepare_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    for col in display.columns:
        if pd.api.types.is_numeric_dtype(display[col]):
            display[col] = pd.to_numeric(display[col], errors="coerce").map(
                lambda v: "" if pd.isna(v) else f"{float(v):g}"
            )
    return display


def dataframe_to_tsv(df: pd.DataFrame, *, column_config: dict | None = None) -> str:
    """Tab-separated — Excel/Sheets 붙여넣기용."""
    if df is None or df.empty:
        return ""
    display = _prepare_display_df(df)
    headers = [_column_header(col, column_config) for col in display.columns]
    lines = ["\t".join(headers)]
    for _, row in display.iterrows():
        lines.append(
            "\t".join(
                _format_cell_value(row[col], col, column_config) for col in display.columns
            )
        )
    return "\n".join(lines)


def dataframe_column_to_text(
    df: pd.DataFrame,
    column: str,
    *,
    column_config: dict | None = None,
) -> str:
    if df is None or df.empty or column not in df.columns:
        return ""
    display = _prepare_display_df(df)
    header = _column_header(column, column_config)
    lines = [header]
    for val in display[column]:
        lines.append(_format_cell_value(val, column, column_config))
    return "\n".join(lines)


def _table_dom_id(key: str | None, view: pd.DataFrame) -> str:
    raw = f"{key or ''}|{list(view.columns)}|{len(view)}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"matp-copy-{digest}"


def render_copyable_table(
    df: pd.DataFrame,
    *,
    height: int = 360,
    key: str | None = None,
    column_config: dict | None = None,
) -> None:
    """표 전체·열·셀 복사 — TSV + 클릭 복사."""
    if df is None or df.empty:
        st.caption("표시할 데이터 없음")
        return

    display = _prepare_display_df(df)
    full_tsv = dataframe_to_tsv(display, column_config=column_config)
    table_id = _table_dom_id(key, display)
    col_labels = [_column_header(col, column_config) for col in display.columns]
    col_payloads = {
        str(col): dataframe_column_to_text(display, str(col), column_config=column_config)
        for col in display.columns
    }

    with st.expander("📋 복사 (전체 표 · 열 단위)", expanded=False):
        st.caption("코드 블록 우측 **Copy** 또는 아래 **TSV 다운로드**")
        st.code(full_tsv, language=None)
        st.download_button(
            "⬇️ TSV 다운로드",
            data=full_tsv.encode("utf-8-sig"),
            file_name="table_export.tsv",
            mime="text/tab-separated-values",
            key=f"{key or table_id}_tsv_download",
            use_container_width=True,
        )
        st.markdown("**열 단위**")
        pick = st.selectbox(
            "복사할 열",
            options=list(display.columns),
            format_func=lambda c: _column_header(str(c), column_config),
            key=f"{key or table_id}_col_pick",
            label_visibility="collapsed",
        )
        st.code(col_payloads[str(pick)], language=None)

    headers_html = "".join(
        f'<th data-col-idx="{i}" title="클릭 → 이 열 전체 복사">{html_module.escape(label)}</th>'
        for i, label in enumerate(col_labels)
    )
    body_rows: list[str] = []
    for _, row in display.iterrows():
        cells = "".join(
            f'<td tabindex="0">{html_module.escape(_format_cell_value(row[col], col, column_config))}</td>'
            for col in display.columns
        )
        body_rows.append(f"<tr>{cells}</tr>")

    col_json = json.dumps(col_payloads, ensure_ascii=False)
    tsv_json = json.dumps(full_tsv, ensure_ascii=False)

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
  .toolbar {{
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.45rem;
    flex-wrap: wrap;
  }}
  .toolbar button {{
    font-size: 0.8rem;
    padding: 0.3rem 0.65rem;
    border-radius: 0.35rem;
    border: 1px solid rgba(250, 250, 250, 0.25);
    background: rgba(49, 51, 63, 0.85);
    color: #fafafa;
    cursor: pointer;
  }}
  .toolbar button:hover {{ background: rgba(77, 171, 247, 0.25); }}
  .toolbar .hint {{
    font-size: 0.75rem;
    color: #adb5bd;
  }}
  .toast {{
    font-size: 0.75rem;
    color: #95d5b2;
    min-height: 1.1rem;
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
    cursor: pointer;
    user-select: none;
  }}
  table.matp-copyable-table th:hover {{
    background: rgba(77, 171, 247, 0.2);
  }}
  table.matp-copyable-table th.col-selected {{
    background: rgba(77, 171, 247, 0.35);
    outline: 2px solid #4dabf7;
    outline-offset: -2px;
  }}
  table.matp-copyable-table td {{
    padding: 0.4rem 0.55rem;
    border-bottom: 1px solid rgba(250, 250, 250, 0.08);
    cursor: cell;
    user-select: text;
    white-space: nowrap;
  }}
  table.matp-copyable-table td.col-selected {{
    background: rgba(77, 171, 247, 0.1);
  }}
  table.matp-copyable-table td.selected {{
    outline: 2px solid #4dabf7;
    outline-offset: -2px;
    background: rgba(77, 171, 247, 0.18);
  }}
  table.matp-copyable-table tr:hover td {{
    background: rgba(255, 255, 255, 0.03);
  }}
</style>
</head>
<body>
  <div class="toolbar">
    <button type="button" id="{table_id}-copy-all">📋 전체 표 복사</button>
    <span class="hint">열 헤더 클릭 → 열 전체 · 셀 클릭 → Ctrl+C</span>
  </div>
  <div class="toast" id="{table_id}-toast"></div>
  <div class="wrap">
    <table class="matp-copyable-table" id="{table_id}">
      <thead><tr>{headers_html}</tr></thead>
      <tbody>{"".join(body_rows)}</tbody>
    </table>
  </div>
  <script>
  (function() {{
    const doc = window.parent.document;
    const table = document.getElementById("{table_id}");
    const toast = document.getElementById("{table_id}-toast");
    const copyAllBtn = document.getElementById("{table_id}-copy-all");
    const colPayloads = {col_json};
    const colKeys = {json.dumps([str(c) for c in display.columns], ensure_ascii=False)};
    const fullTsv = {tsv_json};

    function showToast(msg) {{
      if (toast) toast.textContent = msg;
      setTimeout(() => {{ if (toast) toast.textContent = ""; }}, 2200);
    }}

    function copyText(text) {{
      const done = () => showToast("클립보드에 복사됨");
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(done).catch(() => {{
          doc.__matpSelectedCellText = text;
          showToast("복사 실패 — 텍스트 선택 후 Ctrl+C");
        }});
      }} else {{
        doc.__matpSelectedCellText = text;
        showToast("Ctrl+C 로 복사");
      }}
    }}

    function clearSelection() {{
      table.querySelectorAll("td.selected").forEach((el) => el.classList.remove("selected"));
      table.querySelectorAll("th.col-selected").forEach((el) => el.classList.remove("col-selected"));
      table.querySelectorAll("td.col-selected").forEach((el) => el.classList.remove("col-selected"));
    }}

    function selectColumn(idx) {{
      clearSelection();
      const th = table.querySelector('th[data-col-idx="' + idx + '"]');
      if (th) th.classList.add("col-selected");
      table.querySelectorAll("tbody tr").forEach((tr) => {{
        const cell = tr.children[idx];
        if (cell) cell.classList.add("col-selected");
      }});
    }}

    if (copyAllBtn) {{
      copyAllBtn.addEventListener("click", () => copyText(fullTsv));
    }}

    table.querySelectorAll("th[data-col-idx]").forEach((th) => {{
      th.addEventListener("click", () => {{
        const idx = parseInt(th.getAttribute("data-col-idx"), 10);
        const key = colKeys[idx];
        const text = colPayloads[key] || "";
        selectColumn(idx);
        copyText(text);
      }});
    }});

    table.querySelectorAll("td").forEach((td) => {{
      td.addEventListener("click", () => {{
        clearSelection();
        td.classList.add("selected");
        doc.__matpSelectedCellText = td.textContent.trim();
      }});
    }});
  }})();
  </script>
</body>
</html>
"""
    components.html(doc, height=height + 56, scrolling=False)
    st.caption(
        "**📋 복사** 펼치기 → 전체 TSV · **열 헤더 클릭** → 열 전체 · **셀 클릭** → Ctrl+C"
    )


def target_portfolio_table_height(row_count: int) -> int:
    return table_height(row_count, row_px=40, min_h=320, max_h=720)
