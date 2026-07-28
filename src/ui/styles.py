from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        /* 사이드바 메뉴 (세로 radio) */
        section[data-testid="stSidebar"] div[data-testid="stRadio"] > div {
            flex-direction: column;
            gap: 0.2rem;
        }
        section[data-testid="stSidebar"] div[data-testid="stRadio"] label {
            width: 100%;
            padding: 0.45rem 0.65rem !important;
            border-radius: 0.45rem;
            background: rgba(49, 51, 63, 0.35);
            margin: 0 !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stRadio"] label p {
            font-size: 0.92rem !important;
        }
        /* 사이드바 상태 카드 */
        .ops-status-card {
            padding: 0.75rem 0.9rem;
            border-radius: 0.6rem;
            border: 1px solid rgba(250, 250, 250, 0.12);
            background: rgba(28, 30, 38, 0.55);
            margin-bottom: 0.5rem;
            font-size: 0.88rem;
            line-height: 1.45;
        }
        .ops-status-card strong { color: #fafafa; }
        .ops-pill {
            display: inline-block;
            padding: 0.1rem 0.45rem;
            border-radius: 0.35rem;
            font-size: 0.78rem;
            margin-right: 0.25rem;
        }
        .pill-green { background: #1b4332; color: #95d5b2; }
        .pill-yellow { background: #5c4d00; color: #ffe066; }
        .pill-red { background: #5c1a1a; color: #ffb3b3; }
        .pill-muted { background: #2b2d36; color: #adb5bd; }
        /* 가이드 단계 */
        .guide-step {
            border-left: 3px solid #4dabf7;
            padding: 0.5rem 0 0.5rem 0.9rem;
            margin: 0.4rem 0 0.8rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_table_cell_copy() -> None:
    """표 셀 클릭 후 Ctrl+C 복사 — HTML 표 + Streamlit dataframe 공통."""
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (doc.__matpTableCopyInit) return;
            doc.__matpTableCopyInit = true;

            doc.addEventListener("keydown", function (e) {
                if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "c") return;
                const selected = doc.getSelection && doc.getSelection().toString().trim();
                if (selected) return;

                const text = doc.__matpSelectedCellText;
                if (!text) return;

                const inCopyable = doc.querySelector(".matp-copyable-table td.selected");
                const inStreamlitGrid = e.target.closest(
                    '[data-testid="stDataFrame"], [data-testid="stDataEditor"]'
                );
                if (!inCopyable && !inStreamlitGrid) return;

                e.preventDefault();
                e.stopPropagation();
                const done = (t) => {
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        navigator.clipboard.writeText(t).catch(() => {});
                    }
                };
                done(text);
            }, true);
        })();
        </script>
        """,
        height=0,
        width=0,
    )
