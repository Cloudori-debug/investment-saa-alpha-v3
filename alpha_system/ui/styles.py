"""Mobile-first Streamlit styles — v2 shell + semantic status colors."""

from __future__ import annotations

import streamlit as st


def inject_dashboard_styles(*, compact: bool = False) -> None:
    compact_css = ""
    if compact:
        compact_css = """
[data-testid="stAppViewContainer"] .main .block-container {
  max-width: 480px !important;
}
"""
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Sans:wght@500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .stMarkdown, .stText, .stCaption {{
  font-family: "IBM Plex Sans KR", "IBM Plex Sans", sans-serif;
}}

[data-testid="stAppViewContainer"] {{
  background:
    radial-gradient(1200px 480px at 0% -10%, rgba(15, 118, 110, 0.08), transparent 55%),
    linear-gradient(180deg, #f4f7f6 0%, #eef2f1 40%, #f8faf9 100%);
}}
[data-testid="stAppViewContainer"] .main .block-container {{
  padding-top: 0.85rem;
  padding-bottom: 2.25rem;
  max-width: 760px;
}}

/* —— v2 shell —— */
/* Sidebar main menu (sellable IA) */
.v2-side-nav-brand {{
  margin: 0.15rem 0 0.85rem;
}}
.v2-side-nav-title {{
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #134e4a;
  line-height: 1.2;
}}
.v2-side-nav-sub {{
  margin-top: 0.15rem;
  font-size: 0.8rem;
  color: #5b6b68;
  font-weight: 500;
}}
.v2-side-nav-label {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #0f766e;
  margin: 0 0 0.45rem;
}}
.v2-nav-card-hint {{
  margin: -0.15rem 0 0.7rem;
  padding: 0 0.15rem;
  font-size: 0.75rem;
  color: #5b6b68;
  line-height: 1.35;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button {{
  min-height: 2.85rem !important;
  font-size: 1.05rem !important;
  font-weight: 600 !important;
  justify-content: flex-start !important;
  text-align: left !important;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {{
  font-size: 1.05rem !important;
  font-weight: 600 !important;
}}
.v2-shell-header-slim {{
  align-items: center;
  padding: 0.15rem 0 0.55rem;
}}
.v2-shell-page {{
  font-size: 1.15rem;
  font-weight: 700;
  color: #134e4a;
  letter-spacing: -0.02em;
}}
/* Legacy sticky top-nav markers (unused) */
.v2-primary-nav-mark {{
  display: none;
}}
.v2-primary-nav-label {{
  display: none;
}}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label {{
  font-size: 1.05rem !important;
  font-weight: 600 !important;
  line-height: 1.35 !important;
  padding: 0.55rem 0.25rem !important;
}}
section[data-testid="stSidebar"] div[data-testid="stRadio"] label p {{
  font-size: 1.05rem !important;
  font-weight: 600 !important;
}}

.v2-shell-header {{
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.65rem 1rem;
  margin: 0 0 0.75rem;
  padding: 0.55rem 0 0.65rem;
  border-bottom: 1px solid #c5cdca;
}}
.v2-shell-brand {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
}}
.v2-badge {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.2rem;
  height: 2.2rem;
  padding: 0 0.4rem;
  border-radius: 6px;
  background: #0f766e;
  color: #ecfdf5;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}}
.v2-title {{
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #134e4a;
  line-height: 1.15;
}}
.v2-subtitle {{
  margin-top: 0.1rem;
  font-size: 0.78rem;
  color: #5b6b68;
  font-weight: 500;
}}
.v2-asof {{
  font-size: 0.78rem;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}}
.v2-ops-strip {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: 0.55rem;
  margin: 0 0 0.85rem;
}}
.v2-ops-card {{
  display: block;
  padding: 0.55rem 0.65rem 0.6rem;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  background: rgba(255,255,255,0.92);
  border-left: 4px solid #94a3b8;
  min-height: 4.2rem;
}}
.v2-ops-card-title {{
  display: block;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #134e4a;
  margin-bottom: 0.2rem;
}}
.v2-ops-card-body {{
  display: block;
  font-size: 0.72rem;
  line-height: 1.35;
  color: #5b6b68;
  font-weight: 500;
}}
.v2-ops-card-ok {{
  border-left-color: #0d9488;
  background: #f0fdfa;
}}
.v2-ops-card-ok .v2-ops-card-title {{ color: #115e59; }}
.v2-ops-card-warn {{
  border-left-color: #d97706;
  background: #fffbeb;
}}
.v2-ops-card-warn .v2-ops-card-title {{ color: #92400e; }}
.v2-ops-card-muted {{
  border-left-color: #94a3b8;
  background: #f8fafc;
}}
.v2-chip {{
  display: none;
}}
.v2-chip b {{
  font-weight: 600;
  margin-right: 0.2rem;
}}
.v2-chip-ok {{
  border-color: #99f6e4;
  background: #f0fdfa;
  color: #115e59;
}}
.v2-chip-warn {{
  border-color: #fcd34d;
  background: #fffbeb;
  color: #92400e;
}}
.v2-chip-muted {{
  border-color: #e2e8f0;
  background: #f8fafc;
  color: #64748b;
}}
.v2-section-label {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #0f766e;
  margin: 0.35rem 0 0.45rem;
}}

/* —— Menu tabs: segmented control (labels always visible) —— */
div[data-testid="stButtonGroup"] {{
  margin: 0 0 0.85rem !important;
}}
div[data-testid="stButtonGroup"] > div {{
  display: flex !important;
  flex-wrap: wrap !important;
  gap: 0.35rem !important;
  width: 100% !important;
  padding: 0.4rem !important;
  border: 1px solid #c5cdca !important;
  border-radius: 8px !important;
  background: rgba(255, 255, 255, 0.95) !important;
  box-sizing: border-box !important;
}}
div[data-testid="stButtonGroup"] button {{
  flex: 1 1 0 !important;
  min-width: 0 !important;
  min-height: 2.6rem !important;
  justify-content: center !important;
  font-family: "IBM Plex Sans KR", "IBM Plex Sans", sans-serif !important;
  font-size: 0.875rem !important;
  font-weight: 600 !important;
  line-height: 1.25 !important;
  letter-spacing: -0.01em !important;
  white-space: normal !important;
  border: 1px solid #d1d5db !important;
  border-radius: 6px !important;
  background: #f8faf9 !important;
  color: #1e293b !important;
}}
div[data-testid="stButtonGroup"] button p,
div[data-testid="stButtonGroup"] button span,
div[data-testid="stButtonGroup"] button div {{
  font-family: inherit !important;
  font-size: inherit !important;
  font-weight: 600 !important;
  color: inherit !important;
  opacity: 1 !important;
  visibility: visible !important;
  white-space: normal !important;
}}
div[data-testid="stButtonGroup"] button:hover {{
  border-color: #0f766e !important;
  color: #134e4a !important;
  background: #f0fdfa !important;
}}
div[data-testid="stButtonGroup"] button[kind="primary"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"],
div[data-testid="stButtonGroup"] button[aria-checked="true"],
div[data-testid="stButtonGroup"] button[aria-pressed="true"] {{
  background: #0f766e !important;
  border-color: #0f766e !important;
  color: #ecfdf5 !important;
}}
div[data-testid="stButtonGroup"] button[kind="primary"] p,
div[data-testid="stButtonGroup"] button[kind="primary"] span,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"] p,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"] span {{
  color: #ecfdf5 !important;
}}

/* Primary nav sticky: stretch segments */
div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(> div .v2-primary-nav-mark) div[data-testid="stButtonGroup"] {{
  margin: 0 !important;
}}
div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(> div .v2-primary-nav-mark) div[data-testid="stButtonGroup"] > div {{
  border-color: #0f766e !important;
  background: #ffffff !important;
  flex-wrap: nowrap !important;
}}
div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(> div .v2-primary-nav-mark) div[data-testid="stButtonGroup"] button {{
  min-height: 2.75rem !important;
  font-size: 0.9rem !important;
}}
@media (max-width: 640px) {{
  div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(> div .v2-primary-nav-mark) div[data-testid="stButtonGroup"] > div {{
    flex-wrap: wrap !important;
  }}
  div[data-testid="stButtonGroup"] button {{
    flex: 1 1 calc(50% - 0.35rem) !important;
    font-size: 0.82rem !important;
  }}
}}

/* Radios (e.g. portfolio cutoff): keep labels readable — do not restyle as tabs */
div[data-testid="stRadio"] {{
  margin: 0 0 0.85rem;
}}

.alpha-action-queue {{
  border-left: 4px solid #d97706;
  background: transparent;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.75rem;
  border-radius: 0;
}}
.alpha-banner-muted {{
  border-left: 4px solid #94a3b8;
  background: #f8fafc;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.75rem;
  color: #475569;
}}
.alpha-banner-danger {{
  border-left: 4px solid #ef4444;
  background: #fef2f2;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.75rem;
  color: #991b1b;
}}
.alpha-action-item {{
  padding: 0.5rem 0;
  font-size: 0.95rem;
  line-height: 1.4;
  border-bottom: 1px solid #e2e8f0;
}}
.alpha-empty-queue {{
  border-left: 4px solid #0d9488;
  background: transparent;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.75rem;
  border-radius: 0;
  color: #115e59;
}}
.alpha-card {{
  border: none;
  border-radius: 0;
  padding: 0.65rem 0.75rem;
  margin-bottom: 0.5rem;
  background: transparent;
  border-bottom: 1px solid #e2e8f0;
}}
.alpha-card-ok {{ border-left: 4px solid #0d9488; padding-left: 0.65rem; }}
.alpha-card-warn {{ border-left: 4px solid #d97706; padding-left: 0.65rem; }}
.alpha-card-danger {{ border-left: 4px solid #ef4444; padding-left: 0.65rem; }}
.alpha-card-muted {{ border-left: 4px solid #94a3b8; padding-left: 0.65rem; }}
.alpha-muted-note {{
  color: #64748b;
  font-size: 0.9rem;
  border-left: 2px solid #94a3b8;
  padding: 0.45rem 0.65rem;
  margin: 0.35rem 0;
  background: #f8fafc;
}}
.alpha-badge-warn {{
  display: inline-block;
  background: #fef3c7;
  color: #92400e;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}}
.alpha-badge-danger {{
  display: inline-block;
  background: #fee2e2;
  color: #991b1b;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}}
.alpha-badge-ok {{
  display: inline-block;
  background: #ccfbf1;
  color: #115e59;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}}
.ops-cue {{
  margin-right: 0.25rem;
  vertical-align: middle;
}}

.pf-list {{
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: rgba(255,255,255,0.92);
  padding: 0.15rem 0.65rem 0.25rem;
  margin-bottom: 0.75rem;
}}
.pf-row-main {{
  padding: 0.45rem 0 0.35rem;
}}
.pf-hairline {{
  border-bottom: 1px solid #e2e8f0;
  margin: 0;
}}
.pf-bullet-top {{
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.65rem;
  font-size: 0.92rem;
  margin-bottom: 0.3rem;
}}
.pf-weight-ok {{ color: #115e59; font-weight: 600; }}
.pf-weight-warn {{ color: #92400e; font-weight: 700; }}
.pf-weight-danger {{ color: #991b1b; font-weight: 700; }}
.pf-upside {{ margin-left: auto; font-size: 0.85rem; }}
.pf-tone-accent {{ color: #0f766e; font-weight: 600; }}
.pf-tone-danger {{ color: #991b1b; font-weight: 600; }}
.pf-tone-muted {{ color: #64748b; }}
.muted {{ color: #64748b; }}

.pf-bar-block {{ margin: 0.2rem 0 0.15rem; }}
.pf-bar-caption {{
  font-size: 0.72rem;
  color: #64748b;
  margin-bottom: 0.12rem;
}}
.pf-bar-track {{
  position: relative;
  height: 10px;
  background: #e2e8f0;
  border-radius: 5px;
  overflow: hidden;
}}
.pf-bar-thin {{ height: 6px; }}
.pf-bar-price {{ height: 10px; }}
.pf-bar-fill {{
  position: absolute;
  left: 0; top: 0; bottom: 0;
  border-radius: 5px;
  max-width: 100%;
}}
.pf-fill-accent {{ background: #0f766e; }}
.pf-fill-ok {{ background: #0d9488; }}
.pf-fill-warn {{ background: #d97706; }}
.pf-fill-danger {{ background: #ef4444; }}
.pf-bar-labels {{
  display: flex;
  justify-content: space-between;
  font-size: 0.72rem;
  color: #64748b;
  margin-bottom: 0.1rem;
}}
.pf-missing {{
  color: #991b1b;
  font-size: 0.85rem;
  padding: 0.25rem 0;
}}
.pf-missing-legacy {{
  color: #92400e;
}}

.pf-extend {{
  margin: 0 0 0.15rem;
  padding: 0.55rem 0 0.55rem 0.65rem;
  background: #f1f5f4;
  border-left: 2px solid #0f766e;
  border-radius: 0;
}}
.pf-sec {{ margin: 0.45rem 0 0.55rem; }}
.pf-sec-title {{
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin-bottom: 0.2rem;
  text-transform: none;
}}
.pf-sec-body {{
  font-size: 0.88rem;
  line-height: 1.4;
  color: #0f172a;
  padding: 0;
}}

/* Page titles */
h2, h3, [data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {{
  color: #134e4a !important;
  letter-spacing: -0.015em;
}}

/* Approval page hierarchy */
.ap-page-head {{
  margin: 0 0 0.85rem;
  padding: 0.85rem 0.95rem 0.9rem;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: rgba(255,255,255,0.94);
  border-left: 4px solid #0f766e;
}}
.ap-page-head .v2-section-label {{
  margin: 0 0 0.25rem;
}}
.ap-page-title {{
  margin: 0;
  font-size: 1.45rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #134e4a;
  line-height: 1.2;
}}
.ap-page-lead {{
  margin: 0.4rem 0 0;
  font-size: 0.88rem;
  line-height: 1.45;
  color: #5b6b68;
  font-weight: 500;
}}
.ap-tab-label {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #64748b;
  margin: 0 0 0.35rem;
}}
.ap-panel {{
  margin: 0.35rem 0 1rem;
  padding: 0.85rem 0.95rem 1rem;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: rgba(255,255,255,0.92);
}}
.ap-panel-kicker {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #0f766e;
  margin: 0 0 0.2rem;
}}
.ap-panel-title {{
  margin: 0 0 0.35rem;
  font-size: 1.12rem;
  font-weight: 700;
  color: #134e4a;
  letter-spacing: -0.015em;
}}
.ap-panel-desc {{
  margin: 0 0 0.75rem;
  font-size: 0.84rem;
  line-height: 1.4;
  color: #5b6b68;
}}
.ap-subblock {{
  margin: 0.55rem 0 0.65rem;
  padding: 0.65rem 0.75rem 0.7rem;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: rgba(255,255,255,0.92);
}}
.ap-subblock-title {{
  font-size: 0.95rem;
  font-weight: 700;
  color: #134e4a;
  margin: 0 0 0.35rem;
}}

/* 소분류 단원 — Streamlit border container 얇은 박스 */
div[data-testid="stVerticalBlockBorderWrapper"] {{
  border: 1px solid #d1d5db !important;
  border-radius: 8px !important;
  background: rgba(255,255,255,0.92) !important;
  margin: 0.45rem 0 0.85rem !important;
  box-shadow: none !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"] > div {{
  padding: 0.55rem 0.7rem 0.7rem !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"] h3 {{
  font-size: 1.05rem !important;
  font-weight: 700 !important;
  color: #134e4a !important;
  letter-spacing: -0.015em !important;
  margin: 0 0 0.2rem !important;
  padding: 0 !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] {{
  margin-bottom: 0.45rem !important;
}}

@media (min-width: 768px) {{
  [data-testid="stAppViewContainer"] .main .block-container {{
    max-width: 1120px;
  }}
}}
{compact_css}
</style>
        """,
        unsafe_allow_html=True,
    )


def status_card_class(level: str) -> str:
    return {
        "ok": "alpha-card alpha-card-ok",
        "warn": "alpha-card alpha-card-warn",
        "danger": "alpha-card alpha-card-danger",
        "muted": "alpha-card alpha-card-muted",
    }.get(level, "alpha-card alpha-card-muted")
