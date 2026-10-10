"""Mobile-first Streamlit styles — v2 shell + semantic status colors."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_WIDGET_OVERRIDES = """
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
  background-color: var(--saa-bg) !important;
  color: var(--saa-fg) !important;
}
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stWidgetLabel"] p,
[data-testid="stText"] {
  color: var(--saa-fg);
}
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
  color: var(--saa-muted) !important;
}
div[data-baseweb="input"],
div[data-baseweb="textarea"],
div[data-baseweb="select"] > div {
  background-color: var(--saa-input-bg) !important;
  color: var(--saa-fg) !important;
  border-color: var(--saa-border) !important;
}
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea,
div[data-baseweb="select"] input {
  color: var(--saa-fg) !important;
  -webkit-text-fill-color: var(--saa-fg) !important;
  caret-color: var(--saa-fg) !important;
}
[data-testid="stExpander"],
[data-testid="stExpanderDetails"] {
  background: var(--saa-card) !important;
  border-color: var(--saa-border) !important;
  color: var(--saa-fg) !important;
}
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"],
[data-testid="stMetricDelta"] {
  color: var(--saa-fg) !important;
}
[data-testid="stDataFrame"],
[data-testid="stTable"] {
  color: var(--saa-fg);
}
hr, [data-testid="stDivider"] hr {
  border-color: var(--saa-border) !important;
}
.stApp div[data-testid="stButton"] > button[kind="primary"],
.stApp div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] {
  background: var(--saa-accent) !important;
  border-color: var(--saa-accent) !important;
  color: var(--saa-on-accent) !important;
}
.stApp div[data-testid="stButton"] > button[kind="secondary"],
.stApp div[data-testid="stButton"] > button[data-testid="stBaseButton-secondary"] {
  background: var(--saa-surface) !important;
  border: 1px solid var(--saa-border) !important;
  color: var(--saa-fg) !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] {
  background: var(--saa-fg) !important;
  border-color: var(--saa-fg) !important;
  color: var(--saa-surface) !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="stBaseButton-secondary"] {
  background: var(--saa-surface) !important;
  border: 1px solid var(--saa-border) !important;
  color: var(--saa-fg) !important;
}
[data-testid="stTabs"] button {
  color: var(--saa-muted) !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
  color: var(--saa-fg) !important;
}
div[data-testid="stRadio"] label p,
div[data-testid="stCheckbox"] label p {
  color: var(--saa-fg) !important;
}
/* Button / tab labels inherit the control color — do not paint them as body text. */
div[data-testid="stButton"] [data-testid="stMarkdownContainer"] p,
div[data-testid="stButton"] [data-testid="stMarkdownContainer"] span,
div[data-testid="stButtonGroup"] [data-testid="stMarkdownContainer"] p,
div[data-testid="stButtonGroup"] [data-testid="stMarkdownContainer"] span,
div[data-testid="stButtonGroup"] button p,
div[data-testid="stButtonGroup"] button span,
[data-testid="stTabs"] button p,
[data-testid="stTabs"] button span {
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
  opacity: 1 !important;
}
div[data-testid="stButtonGroup"] > div {
  background: var(--saa-card) !important;
  border-color: var(--saa-border) !important;
}
div[data-testid="stButtonGroup"] button {
  background: var(--saa-surface) !important;
  border-color: var(--saa-border-strong) !important;
  color: var(--saa-fg) !important;
}
div[data-testid="stButtonGroup"] button[kind="primary"],
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"],
div[data-testid="stButtonGroup"] button[kind="pillsActive"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"],
div[data-testid="stButtonGroup"] button[aria-checked="true"],
div[data-testid="stButtonGroup"] button[aria-pressed="true"] {
  background: var(--saa-accent) !important;
  border-color: var(--saa-accent) !important;
  color: var(--saa-on-accent) !important;
}
div[data-testid="stButtonGroup"] button[kind="primary"] p,
div[data-testid="stButtonGroup"] button[kind="primary"] span,
div[data-testid="stButtonGroup"] button[kind="primary"] div,
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] p,
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] span,
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] div,
div[data-testid="stButtonGroup"] button[kind="pillsActive"] p,
div[data-testid="stButtonGroup"] button[kind="pillsActive"] span,
div[data-testid="stButtonGroup"] button[kind="pillsActive"] div,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"] p,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"] span,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"] div,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] p,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] span,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] div,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"] p,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"] span,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"] div,
div[data-testid="stButtonGroup"] button[aria-checked="true"] p,
div[data-testid="stButtonGroup"] button[aria-checked="true"] span,
div[data-testid="stButtonGroup"] button[aria-checked="true"] div,
div[data-testid="stButtonGroup"] button[aria-pressed="true"] p,
div[data-testid="stButtonGroup"] button[aria-pressed="true"] span,
div[data-testid="stButtonGroup"] button[aria-pressed="true"] div {
  color: var(--saa-on-accent) !important;
  -webkit-text-fill-color: var(--saa-on-accent) !important;
}
.stApp div[data-testid="stButton"] > button[kind="primary"] p,
.stApp div[data-testid="stButton"] > button[kind="primary"] span,
.stApp div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] p,
.stApp div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] span {
  color: var(--saa-on-accent) !important;
  -webkit-text-fill-color: var(--saa-on-accent) !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] p,
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] span,
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] p,
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] span {
  color: var(--saa-bg) !important;
  -webkit-text-fill-color: var(--saa-bg) !important;
}
[data-testid="stTabs"] button[aria-selected="true"] p,
[data-testid="stTabs"] button[aria-selected="true"] span {
  color: var(--saa-fg) !important;
  -webkit-text-fill-color: var(--saa-fg) !important;
}
div[data-testid="stAlert"] {
  background: var(--saa-card) !important;
  color: var(--saa-fg) !important;
  border-color: var(--saa-border) !important;
}
code, pre, [data-testid="stCode"] {
  background: var(--saa-input-bg) !important;
  color: var(--saa-ink) !important;
}
.eco-hero { margin: 0.1rem 0 0.7rem; }
.eco-card {
  background: var(--saa-card);
  border: 1px solid var(--saa-border);
  border-radius: 10px;
  padding: 0.9rem 1rem 0.95rem;
}
.eco-card.eco-now { border-color: var(--saa-accent); }
.eco-kicker {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--saa-muted);
  margin: 0 0 0.15rem;
}
.eco-title {
  font-size: 1.22rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--saa-fg);
  margin: 0 0 0.7rem;
}
.eco-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem;
  margin: 0 0 0.65rem;
}
.eco-split > div {
  padding: 0.45rem 0.55rem 0.5rem;
  background: var(--saa-muted-bg);
  border-radius: 8px;
}
.eco-pct {
  display: block;
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: -0.04em;
  color: var(--saa-fg);
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
}
.eco-pct-label {
  display: block;
  margin-top: 0.18rem;
  font-size: 0.78rem;
  color: var(--saa-muted);
}
.eco-why, .eco-when {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.4;
  color: var(--saa-muted);
}
.eco-when { margin-top: 0.3rem; }
.eco-sec {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--saa-muted);
  margin: 0.15rem 0 0.4rem;
}
.eco-steps {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.35rem;
  margin: 0 0 0.95rem;
}
.eco-step {
  min-width: 0;
  border: 1px solid var(--saa-border);
  border-radius: 8px;
  background: var(--saa-card);
  padding: 0.42rem 0.28rem 0.48rem;
  text-align: center;
}
.eco-step.is-now {
  border-color: var(--saa-accent);
  background: var(--saa-ok-bg);
}
.eco-step-n {
  font-size: 0.66rem;
  font-weight: 700;
  color: var(--saa-muted);
}
.eco-step-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--saa-fg);
  margin-top: 0.08rem;
}
.eco-step-split {
  font-size: 0.7rem;
  color: var(--saa-muted);
  margin-top: 0.12rem;
  font-variant-numeric: tabular-nums;
}
.eco-step-now {
  margin-top: 0.18rem;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--saa-accent);
}
.eco-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.5rem;
  margin: 0 0 0.9rem;
}
@media (min-width: 720px) {
  .eco-grid { grid-template-columns: 1fr 1fr; }
}
.eco-metric {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto auto auto;
  column-gap: 0.55rem;
  row-gap: 0.12rem;
  align-items: start;
  background: var(--saa-card);
  border: 1px solid var(--saa-border);
  border-radius: 8px;
  padding: 0.7rem 0.8rem 0.72rem;
}
.eco-m-title {
  font-weight: 700;
  color: var(--saa-fg);
  font-size: 0.9rem;
}
.eco-val {
  grid-column: 1;
  font-size: 1.18rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  color: var(--saa-fg);
}
.eco-m-hint {
  grid-column: 1 / -1;
  font-size: 0.74rem;
  color: var(--saa-muted);
  line-height: 1.35;
}
.eco-slide {
  grid-column: 1 / -1;
  margin: 0.42rem 0 0.08rem;
}
.eco-slide-track {
  position: relative;
  display: flex;
  height: 9px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--saa-muted-bg, #e8e8e8);
}
.eco-slide-seg {
  display: block;
  height: 100%;
  flex: 0 0 auto;
}
.eco-slide-seg.eco-ok { background: color-mix(in srgb, var(--saa-ok-bg, #c8e6c9) 85%, #fff); }
.eco-slide-seg.eco-wait { background: color-mix(in srgb, var(--saa-warn-chip, #ffe0b2) 90%, #fff); }
.eco-slide-seg.eco-bad { background: color-mix(in srgb, var(--saa-danger-chip, #ffcdd2) 90%, #fff); }
.eco-slide-mark {
  position: absolute;
  top: 50%;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: #fff;
  border: 2.5px solid var(--saa-fg, #222);
  box-shadow: 0 0 0 1px rgba(0,0,0,0.06);
  z-index: 2;
  pointer-events: none;
}
.eco-slide-mark.eco-ok { border-color: #2e7d32; }
.eco-slide-mark.eco-wait { border-color: #ef6c00; }
.eco-slide-mark.eco-bad { border-color: #c62828; }
.eco-slide-mark.eco-off { border-color: var(--saa-muted, #888); }
.eco-slide-ticks {
  position: relative;
  height: 1.55rem;
  margin-top: 0.15rem;
}
.eco-slide-tick {
  position: absolute;
  transform: translateX(-50%);
  text-align: center;
  line-height: 1.1;
}
.eco-slide-tick-mark {
  display: block;
  width: 1px;
  height: 5px;
  margin: 0 auto 2px;
  background: var(--saa-border, #ccc);
}
.eco-slide-tick-lab {
  font-size: 0.68rem;
  color: var(--saa-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.eco-slide.is-clamp .eco-slide-mark {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--saa-warn-chip, #ffe0b2) 70%, transparent);
}
.eco-m-read {
  grid-column: 1 / -1;
  margin-top: 0.18rem;
  padding-top: 0.35rem;
  border-top: 1px solid var(--saa-border);
  font-size: 0.8rem;
  color: var(--saa-fg);
  line-height: 1.45;
}
.eco-todo {
  border: 1px solid var(--saa-border);
  border-radius: 8px;
  padding: 0.7rem 0.75rem 0.65rem;
  margin: 0 0 0.55rem;
  background: var(--saa-card);
}
.eco-todo-wait {
  border-color: color-mix(in srgb, var(--saa-warn-chip, #ffe0b2) 80%, var(--saa-border));
  background: color-mix(in srgb, var(--saa-warn-chip, #fff8e8) 28%, var(--saa-card));
}
.eco-todo-bad {
  border-color: color-mix(in srgb, var(--saa-danger-chip, #ffcdd2) 80%, var(--saa-border));
  background: color-mix(in srgb, var(--saa-danger-chip, #ffebee) 24%, var(--saa-card));
}
.eco-todo-ok {
  border-color: color-mix(in srgb, var(--saa-ok-bg, #c8e6c9) 70%, var(--saa-border));
}
.eco-todo-forest {
  border-style: dashed;
}
.eco-todo-head { margin-bottom: 0.55rem; }
.eco-todo-title {
  font-weight: 700;
  font-size: 0.98rem;
  color: var(--saa-fg);
  letter-spacing: -0.02em;
}
.eco-todo-sub {
  margin-top: 0.15rem;
  font-size: 0.8rem;
  color: var(--saa-muted);
  font-variant-numeric: tabular-nums;
}
.eco-todo-bar {
  display: flex;
  width: 100%;
  height: 1.55rem;
  margin-top: 0.45rem;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--saa-border) 80%, transparent);
  background: var(--saa-bg, #f5f5f5);
}
.eco-todo-bar-eq {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  background: color-mix(in srgb, var(--saa-accent, #3d6e8f) 42%, #fff);
}
.eco-todo-bar-cash {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  background: color-mix(in srgb, var(--saa-ok-bg, #c8e6c9) 75%, #fff);
}
.eco-todo-bar-lab {
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--saa-fg);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 0.25rem;
  font-variant-numeric: tabular-nums;
}
.eco-todo-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.45rem;
}
@media (min-width: 720px) {
  .eco-todo-grid { grid-template-columns: 1fr 1fr; }
}
.eco-todo-card {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 0.5rem;
  row-gap: 0.1rem;
  align-items: start;
  background: var(--saa-card);
  border: 1px solid var(--saa-border);
  border-radius: 8px;
  padding: 0.55rem 0.65rem 0.58rem;
}
.eco-todo-n {
  grid-row: 1 / span 2;
  align-self: center;
  font-size: 0.72rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--saa-muted);
  min-width: 1.4rem;
}
.eco-todo-label {
  font-weight: 700;
  font-size: 0.84rem;
  color: var(--saa-fg);
  letter-spacing: -0.01em;
}
.eco-todo-body {
  font-size: 0.78rem;
  line-height: 1.4;
  color: var(--saa-muted);
}
.eco-gap-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.5rem;
  margin: 0 0 0.7rem;
}
@media (min-width: 900px) {
  .eco-gap-grid { grid-template-columns: 1fr 1fr 1fr; }
}
.eco-gap-card {
  border: 1px solid var(--saa-border);
  border-radius: 8px;
  padding: 0.65rem 0.75rem;
  background: var(--saa-card);
}
.eco-gap-out { border-left: 3px solid #c62828; }
.eco-gap-in { border-left: 3px solid #ef6c00; }
.eco-gap-ok { border-left: 3px solid #2e7d32; }
.eco-gap-h {
  font-weight: 700;
  font-size: 0.86rem;
  color: var(--saa-fg);
}
.eco-gap-hint {
  margin-top: 0.12rem;
  font-size: 0.72rem;
  color: var(--saa-muted);
}
.eco-gap-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-top: 0.45rem;
}
.eco-gap-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 0.25rem;
  font-size: 0.78rem;
  padding: 0.18rem 0.4rem;
  border-radius: 4px;
  background: var(--saa-muted-bg, #f3f3f3);
  color: var(--saa-fg);
}
.eco-gap-tk {
  font-size: 0.7rem;
  color: var(--saa-muted);
  font-variant-numeric: tabular-nums;
}
.eco-gap-empty {
  font-size: 0.78rem;
  color: var(--saa-muted);
}
.eco-date {
  grid-column: 2;
  grid-row: 2;
  font-size: 0.74rem;
  color: var(--saa-muted);
  white-space: nowrap;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.eco-div {
  margin: 0 0 0.55rem;
  padding: 0.65rem 0.8rem;
  border-radius: 8px;
  border: 1px solid var(--saa-border-strong);
  background: #f8fafc;
}
.eco-div-favor {
  border-color: #c5d4c8;
  background: #f4f7f4;
}
.eco-div-caution {
  border-color: #f0c36a;
  background: #fffbeb;
}
.eco-div-neutral {
  border-color: #cbd5e1;
  background: #f8fafc;
}
.eco-div-title {
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #1c1a16;
  margin-bottom: 0.25rem;
}
.eco-div-favor .eco-div-title { color: #2d4a3c; }
.eco-div-caution .eco-div-title { color: #92400e; }
.eco-div-body {
  font-size: 0.84rem;
  line-height: 1.45;
  color: #475569;
}
.eco-div-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
  margin: 0.35rem 0 0.85rem;
}
.eco-div-table th,
.eco-div-table td {
  padding: 0.35rem 0.45rem;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  text-align: left;
}
.eco-div-table th {
  font-size: 0.72rem;
  font-weight: 700;
  color: #64748b;
}
.eco-div-table td:nth-child(3),
.eco-div-table td:nth-child(4),
.eco-div-table td:nth-child(5) {
  font-variant-numeric: tabular-nums;
}
.eco-stress {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 0.1rem 0.42rem;
  border-radius: 999px;
  justify-self: end;
}
.eco-stress.eco-ok { background: var(--saa-ok-bg); color: var(--saa-fg); }
.eco-stress.eco-wait { background: var(--saa-warn-chip); color: var(--saa-warn-fg); }
.eco-stress.eco-bad { background: var(--saa-danger-chip); color: var(--saa-danger-fg); }
.eco-stress.eco-off { background: var(--saa-muted-bg); color: var(--saa-muted); }
.eco-compass-block {
  margin: 0.35rem 0 0.85rem;
}
.eco-compass-empty, .eco-compass-alpha, .eco-compass-warn, .eco-kr-link {
  font-size: 0.86rem;
  line-height: 1.45;
  color: var(--saa-fg);
  margin: 0 0 0.45rem;
}
.eco-compass-warn {
  padding: 0.45rem 0.6rem;
  border-radius: 6px;
  background: color-mix(in srgb, var(--saa-warn-chip, #ffe0b2) 70%, #fff);
  border-left: 3px solid #ef6c00;
}
.eco-compass-alpha { color: var(--saa-muted); }
.eco-sleeve-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.45rem;
}
@media (min-width: 900px) {
  .eco-sleeve-grid { grid-template-columns: repeat(4, 1fr); }
}
.eco-sleeve {
  background: var(--saa-card);
  border: 1px solid var(--saa-border);
  border-radius: 8px;
  padding: 0.55rem 0.65rem 0.6rem;
  border-top: 3px solid var(--saa-border);
}
.eco-sleeve-up { border-top-color: #2e7d32; }
.eco-sleeve-down { border-top-color: #c62828; }
.eco-sleeve-flat { border-top-color: #78909c; }
.eco-sleeve-k {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--saa-muted);
  letter-spacing: 0.02em;
}
.eco-sleeve-pct {
  font-size: 1.35rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  margin: 0.15rem 0 0.1rem;
}
.eco-sleeve-act {
  font-size: 0.78rem;
  font-weight: 700;
  margin-bottom: 0.25rem;
}
.eco-sleeve-up .eco-sleeve-act { color: #2e7d32; }
.eco-sleeve-down .eco-sleeve-act { color: #c62828; }
.eco-sleeve-why {
  font-size: 0.78rem;
  line-height: 1.4;
  color: var(--saa-muted);
}
.eco-hist-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
  margin: 0.2rem 0 0.4rem;
}
.eco-hist-table th,
.eco-hist-table td {
  border-bottom: 1px solid var(--saa-border);
  padding: 0.35rem 0.4rem;
  text-align: left;
}
.eco-hist-table th {
  font-size: 0.72rem;
  color: var(--saa-muted);
  font-weight: 700;
}
.eco-hist-table .eco-num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.eco-hist-note {
  font-size: 0.74rem;
  color: var(--saa-muted);
  line-height: 1.4;
}
.eco-m-sleeve-v {
  margin-top: 0.35rem;
  font-size: 0.78rem;
  line-height: 1.4;
  color: var(--saa-fg);
  padding-top: 0.3rem;
  border-top: 1px dashed var(--saa-border);
}
.eco-m-sleeve-list { margin: 0.35rem 0 0.7rem; }
.eco-m-sleeve {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--saa-border);
  font-size: 0.8rem;
}
.eco-m-sleeve-k { font-weight: 700; color: var(--saa-muted); }
.pc-sec {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--saa-muted);
  margin: 0.55rem 0 0.35rem;
}
.pc-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.45rem;
  margin: 0.4rem 0 0.85rem;
}
@media (min-width: 720px) {
  .pc-grid { grid-template-columns: 1fr 1fr; }
}
.pc-card {
  background: var(--saa-card);
  border: 1px solid var(--saa-border);
  border-radius: 8px;
  padding: 0.65rem 0.75rem 0.7rem;
}
.pc-card .eco-val { margin: 0.15rem 0 0.35rem; }
.pc-chips { display: flex; flex-wrap: wrap; gap: 0.28rem; }
.pc-card .eco-m-hint { margin-top: 0.35rem; }
"""


def inject_dashboard_styles(root: Path | None = None) -> None:
    from alpha_system.ui.services.ui_copy import copy_get
    from alpha_system.ui.theme_prefs import (
        THEME_DARK,
        THEME_LIGHT,
        apply_color_tokens,
        css_variables,
        load_ui_theme,
    )

    theme = load_ui_theme(root)
    try:
        dark_l = copy_get("display", "theme_dark", default="다크")
        light_l = copy_get("display", "theme_light", default="일반")
        for key in ("saa_theme_sidebar", "saa_theme_settings"):
            label = st.session_state.get(key)
            if label == dark_l:
                theme = THEME_DARK
                break
            if label == light_l:
                theme = THEME_LIGHT
                break
        st.session_state["saa_ui_theme"] = theme
    except Exception:
        pass
    css = f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

html, body, [data-testid="stAppViewContainer"], .stMarkdown, .stText, .stCaption {{
  font-family: Pretendard, "Noto Sans KR", sans-serif;
}}

[data-testid="stAppViewContainer"] {{
  background: #f3efe6;
}}
[data-testid="stHeader"] {{
  background: #f3efe6;
}}
section[data-testid="stSidebar"] {{
  background: #faf7f1 !important;
  border-right: 1px solid #dcd4c6;
}}
section[data-testid="stSidebar"] > div {{
  background: #faf7f1 !important;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] {{
  background: #1c1a16 !important;
  border-color: #1c1a16 !important;
  color: #faf7f1 !important;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="stBaseButton-secondary"] {{
  background: #faf7f1 !important;
  border: 1px solid #dcd4c6 !important;
  color: #1c1a16 !important;
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
  color: #1c1a16;
  line-height: 1.2;
}}
.v2-side-nav-sub {{
  margin-top: 0.15rem;
  font-size: 0.8rem;
  color: #6f6a60;
  font-weight: 500;
}}
.v2-side-nav-ver {{
  margin-top: 0.28rem;
  font-size: 0.72rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  color: #2d4a3c;
}}
.v2-side-nav-label {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #2d4a3c;
  margin: 0 0 0.45rem;
}}
.v2-nav-card-hint {{
  margin: -0.15rem 0 0.7rem;
  padding: 0 0.15rem;
  font-size: 0.75rem;
  color: #6f6a60;
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
  justify-content: flex-end;
  padding: 0 0 0.45rem;
  margin: 0 0 0.15rem;
  border-bottom: none;
}}
.v2-shell-page {{
  font-size: 1.15rem;
  font-weight: 700;
  color: #1c1a16;
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
  border-bottom: 1px solid #dcd4c6;
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
  background: #2d4a3c;
  color: #faf7f1;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}}
.v2-title {{
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #1c1a16;
  line-height: 1.15;
}}
.v2-subtitle {{
  margin-top: 0.1rem;
  font-size: 0.78rem;
  color: #6f6a60;
  font-weight: 500;
}}
.v2-asof {{
  font-size: 0.78rem;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}}
.v2-section-label {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #2d4a3c;
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
  border: 1px solid #dcd4c6 !important;
  border-radius: 8px !important;
  background: rgba(255, 255, 255, 0.95) !important;
  box-sizing: border-box !important;
}}
div[data-testid="stButtonGroup"] button {{
  flex: 1 1 0 !important;
  min-width: 0 !important;
  min-height: 2.6rem !important;
  justify-content: center !important;
  font-family: Pretendard, "Noto Sans KR", sans-serif !important;
  font-size: 0.875rem !important;
  font-weight: 600 !important;
  line-height: 1.25 !important;
  letter-spacing: -0.01em !important;
  white-space: normal !important;
  border: 1px solid #d1d5db !important;
  border-radius: 6px !important;
  background: #faf7f1 !important;
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
  border-color: #2d4a3c !important;
  color: #1c1a16 !important;
  background: #faf7f1 !important;
}}
div[data-testid="stButtonGroup"] button[kind="primary"],
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"],
div[data-testid="stButtonGroup"] button[kind="pillsActive"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"],
div[data-testid="stButtonGroup"] button[aria-checked="true"],
div[data-testid="stButtonGroup"] button[aria-pressed="true"] {{
  background: var(--saa-accent) !important;
  border-color: var(--saa-accent) !important;
  color: var(--saa-on-accent) !important;
}}
div[data-testid="stButtonGroup"] button[kind="primary"] p,
div[data-testid="stButtonGroup"] button[kind="primary"] span,
div[data-testid="stButtonGroup"] button[kind="primary"] div,
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] p,
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] span,
div[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] div,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"] p,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-primary"] span,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] p,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] span,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] div {{
  color: var(--saa-on-accent) !important;
  -webkit-text-fill-color: var(--saa-on-accent) !important;
}}

/* Primary nav sticky: stretch segments */
div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(> div .v2-primary-nav-mark) div[data-testid="stButtonGroup"] {{
  margin: 0 !important;
}}
div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(> div .v2-primary-nav-mark) div[data-testid="stButtonGroup"] > div {{
  border-color: #2d4a3c !important;
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
  border-left: 4px solid #2d4a3c;
  background: transparent;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.75rem;
  border-radius: 0;
  color: #2d4a3c;
}}
.alpha-card {{
  border: none;
  border-radius: 0;
  padding: 0.65rem 0.75rem;
  margin-bottom: 0.5rem;
  background: transparent;
  border-bottom: 1px solid #e2e8f0;
}}
.alpha-card-ok {{ border-left: 4px solid #2d4a3c; padding-left: 0.65rem; }}
.alpha-card-warn {{ border-left: 4px solid #d97706; padding-left: 0.65rem; }}
.alpha-card-danger {{ border-left: 4px solid #ef4444; padding-left: 0.65rem; }}
.alpha-card-muted {{ border-left: 4px solid #94a3b8; padding-left: 0.65rem; }}
.alpha-quad {{
  border-radius: 8px;
  padding: 0.7rem 0.8rem;
  min-height: 5.4rem;
  background: #faf7f1;
  border: 1px solid #dcd4c6;
  margin-bottom: 0.45rem;
  color: #64748b;
}}
.alpha-quad-active {{
  background: #faf7f1;
  border-color: #2d4a3c;
  color: #1c1a16;
}}
.alpha-quad-body {{
  display: block;
  margin-top: 0.28rem;
  font-size: 0.82rem;
  color: #6f6a60;
  line-height: 1.4;
}}
.alpha-quad:not(.alpha-quad-active) .alpha-quad-body {{
  color: #6f6a60;
}}
.alpha-flow-row {{
  display: flex;
  gap: 0.55rem;
  align-items: flex-start;
  padding: 0.45rem 0;
  border-bottom: 1px solid #e2e8f0;
  font-size: 0.92rem;
  line-height: 1.4;
}}
.alpha-flow-asset {{
  min-width: 7.2rem;
  font-weight: 600;
  color: #1c1a16;
}}
.home-kicker {{
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.015em;
  color: #1c1a16;
  margin: 0 0 0.35rem;
}}
.home-kicker-tight {{
  margin-top: 0;
  margin-bottom: 0.35rem;
}}
.home-hero {{
  margin: 0.15rem 0 0.85rem;
}}
.home-hero-title {{
  font-size: 1.28rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #1c1a16;
  line-height: 1.3;
  margin: 0.08rem 0 0.28rem;
}}
.home-hero-sub {{
  font-size: 0.82rem;
  color: #6f6a60;
  line-height: 1.4;
  margin: 0.15rem 0 0;
}}
.home-para {{
  font-size: 0.95rem;
  line-height: 1.55;
  color: #1e293b;
  margin: 0 0 0.55rem;
}}
.home-levels {{
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 0.5rem;
  margin: 0.1rem 0 0.25rem;
}}
@media (max-width: 640px) {{
  .home-levels {{ grid-template-columns: 1fr; }}
}}
.home-level {{
  border-radius: 8px;
  padding: 0.7rem 0.8rem;
  background: #faf7f1;
  border: 1px solid #dcd4c6;
}}
.home-level-warn {{
  background: #fffbeb;
  border-color: #f0d9a8;
}}
.home-level-value {{
  font-size: 1.12rem;
  font-weight: 700;
  color: #1c1a16;
  letter-spacing: -0.02em;
}}
.home-level-label {{
  margin-top: 0.2rem;
  font-size: 0.78rem;
  color: #6f6a60;
  line-height: 1.35;
}}
.home-flow-row {{
  display: grid;
  grid-template-columns: minmax(6.4rem, 7.6rem) 4.4rem 1fr;
  gap: 0.55rem;
  align-items: start;
  padding: 0.5rem 0;
  border-bottom: 1px solid #e2e8f0;
  font-size: 0.9rem;
  line-height: 1.4;
}}
@media (max-width: 640px) {{
  .home-flow-row {{
    grid-template-columns: 1fr;
    gap: 0.15rem;
  }}
}}
.home-flow-asset {{
  font-weight: 600;
  color: #1c1a16;
}}
.home-flow-dir {{
  font-weight: 700;
  font-size: 0.82rem;
}}
.home-flow-dir-ok {{ color: #2d4a3c; }}
.home-flow-dir-danger {{ color: #b45309; }}
.home-flow-dir-muted {{ color: #64748b; }}
.home-flow-why {{
  color: #6f6a60;
}}
.home-note {{
  border-left: 3px solid #d97706;
  padding: 0.5rem 0.7rem;
  margin: 0.35rem 0 0.55rem;
  background: #fffbeb;
  color: #78350f;
  font-size: 0.88rem;
  line-height: 1.45;
  border-radius: 0 6px 6px 0;
}}
.home-usage {{
  margin: 0.1rem 0 0.35rem;
}}
.home-usage-meta {{
  font-size: 0.86rem;
  color: #1c1a16;
  line-height: 1.45;
  margin-bottom: 0.4rem;
}}
.home-usage-track {{
  height: 7px;
  background: #e2e8f0;
  border-radius: 99px;
  overflow: hidden;
}}
.home-usage-fill {{
  height: 100%;
  background: #2d4a3c;
  border-radius: 99px;
}}
.home-usage-fill-warn {{ background: #d97706; }}
.home-usage-fill-danger {{ background: #dc2626; }}
.home-foot {{
  margin-top: 0.85rem;
  padding-top: 0.75rem;
  border-top: 1px solid #dcd4c6;
}}
.home-foot-line {{
  font-size: 0.82rem;
  color: #6f6a60;
  line-height: 1.45;
  margin-bottom: 0.55rem;
}}
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
  background: #e4ebe4;
  color: #2d4a3c;
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
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
  padding: 0.1rem 0.7rem 0.35rem;
  margin-bottom: 0.75rem;
}}
.pf-row-main {{
  padding: 0.7rem 0 0.55rem;
}}
.pf-hairline {{
  border-bottom: 1px solid #e2e8f0;
  margin: 0;
}}
.pf-bullet-top {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem 0.55rem;
  margin-bottom: 0.45rem;
}}
.pf-id {{
  font-size: 1.05rem;
  letter-spacing: -0.02em;
  color: #0f172a;
}}
.pf-id strong {{
  font-weight: 700;
}}
.pf-chart-hint {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 1.75rem;
  min-width: 2.75rem;
  padding: 0.2rem 0.6rem;
  margin: 0 0.2rem 0 0.28rem;
  border-radius: 6px;
  border: 1px solid #8fa0b3;
  background: #eef3f8;
  color: #1e3a5f;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1;
  text-decoration: none;
  white-space: nowrap;
  vertical-align: middle;
  box-sizing: border-box;
}}
.pf-chart-hint:hover {{
  background: #1e3a5f;
  color: #faf7f1;
  border-color: #1e3a5f;
  text-decoration: none;
}}
.pf-ticker {{
  font-size: 0.78rem;
  font-weight: 500;
  color: #64748b;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}}
.pf-wchip {{
  font-size: 0.8rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
.pf-spot {{
  font-size: 0.95rem;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
  color: #1c1a16;
  letter-spacing: -0.02em;
}}
.pf-chart-read {{
  margin: 0.15rem 0 0.4rem;
  padding: 0.42rem 0.55rem;
  border-radius: 6px;
  font-size: 0.92rem;
  font-weight: 700;
  line-height: 1.4;
  color: #1c1a16;
  background: #efe8d8;
  border: 1px solid #b7a88a;
}}
.pf-chart-read.pf-chart-hot {{
  background: #f3ddb0;
  border-color: #c9a227;
  color: #4a3200;
}}
.pf-chart-read.pf-chart-weak {{
  background: #dce6f0;
  border-color: #7b93ab;
  color: #1a334d;
}}
.pf-chart-read.pf-chart-ok {{
  background: #dce8dc;
  border-color: #6a8a72;
  color: #1c3324;
}}
.pf-signal {{
  margin: 0.2rem 0 0.45rem;
  padding: 0.5rem 0.6rem 0.45rem;
  border-radius: 8px;
  border: 1px solid #b7a88a;
  background: #efe8d8;
  color: #1c1a16;
}}
.pf-signal.pf-signal-hot {{
  background: #f3ddb0;
  border-color: #c9a227;
  color: #4a3200;
}}
.pf-signal.pf-signal-weak {{
  background: #dce6f0;
  border-color: #7b93ab;
  color: #1a334d;
}}
.pf-signal.pf-signal-ok {{
  background: #dce8dc;
  border-color: #6a8a72;
  color: #1c3324;
}}
.pf-signal-headline {{
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.35;
  margin-bottom: 0.28rem;
}}
.pf-signal-why {{
  font-size: 0.86rem;
  font-weight: 500;
  line-height: 1.45;
  margin-bottom: 0.38rem;
  opacity: 0.95;
}}
.pf-signal-evidence {{
  font-size: 0.8rem;
  line-height: 1.5;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  padding-top: 0.32rem;
  margin-bottom: 0.15rem;
}}
.pf-signal-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 0.5rem;
  margin-bottom: 0.12rem;
}}
.pf-signal-lbl {{
  flex: 0 0 2.1rem;
  font-weight: 700;
  color: #64748b;
  font-size: 0.75rem;
  text-transform: none;
}}
.pf-signal-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.35rem;
  margin-top: 0.35rem;
  padding-top: 0.28rem;
  border-top: 1px dashed rgba(0, 0, 0, 0.1);
}}
.pf-signal-chip {{
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.08rem 0.4rem;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(0, 0, 0, 0.12);
  color: inherit;
  font-variant-numeric: tabular-nums;
}}
.pf-weight-ok {{ color: #2d4a3c; font-weight: 600; }}
.pf-weight-warn {{ color: #92400e; font-weight: 700; }}
.pf-weight-danger {{ color: #991b1b; font-weight: 700; }}
.pf-weight-muted {{ color: #64748b; font-weight: 600; }}
.pf-upside {{
  margin-left: auto;
  font-size: 0.92rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
.pf-tone-accent {{ color: #2d4a3c; font-weight: 600; }}
.pf-tone-warn {{ color: #b45309; font-weight: 700; }}
.pf-tone-danger {{ color: #991b1b; font-weight: 600; }}
.pf-tone-muted {{ color: #64748b; }}
.muted {{ color: #64748b; }}

.pf-ladder {{
  margin: 0.15rem 0 0.35rem;
}}
.pf-bar-block {{ margin: 0.15rem 0 0.1rem; }}
.pf-bar-caption {{
  font-size: 0.72rem;
  color: #64748b;
  margin-bottom: 0.12rem;
}}
.pf-quant-note {{
  margin-top: 0.2rem;
  font-size: 0.7rem;
  color: #94a3b8;
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
.pf-bar-ladder {{
  overflow: visible;
  height: 14px;
  margin: 0.15rem 0 0.2rem;
}}
.pf-bar-fill {{
  position: absolute;
  left: 0; top: 0; bottom: 0;
  border-radius: 5px;
  max-width: 100%;
}}
.pf-fill-accent {{ background: #2d4a3c; }}
.pf-fill-ok {{ background: #2d4a3c; }}
.pf-fill-warn {{ background: #d97706; }}
.pf-fill-danger {{ background: #ef4444; }}
.pf-bar-tick {{
  position: absolute;
  top: -3px;
  width: 2px;
  height: 20px;
  background: #94a3b8;
  transform: translateX(-1px);
  z-index: 2;
  pointer-events: none;
}}
.pf-bar-tick-0, .pf-bar-tick-4 {{
  background: #475569;
  height: 22px;
}}
.pf-bar-now {{
  position: absolute;
  top: -6px;
  width: 3px;
  height: 26px;
  background: #1c1a16;
  transform: translateX(-1.5px);
  z-index: 3;
  border-radius: 1px;
  pointer-events: none;
}}
.pf-ladder-axis {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 0.4rem;
  margin-bottom: 0.28rem;
}}
.pf-ladder-axis > span {{
  display: flex;
  flex-direction: column;
  min-width: 0;
}}
.pf-ladder-axis > span:nth-child(2) {{
  align-items: center;
  text-align: center;
}}
.pf-ladder-axis > span:last-child {{
  align-items: flex-end;
  text-align: right;
}}
.pf-kicker {{
  display: block;
  font-size: 0.68rem;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.01em;
  margin-bottom: 0.06rem;
}}
.pf-num {{
  display: block;
  font-size: 0.92rem;
  font-weight: 700;
  color: #1e293b;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
  line-height: 1.15;
}}
.pf-axis-now .pf-kicker {{
  color: #2d4a3c;
}}
.pf-axis-now .pf-num {{
  font-size: 1.12rem;
  color: #2d4a3c;
}}
.pf-ladder-rungs {{
  display: flex;
  justify-content: space-between;
  gap: 0.2rem;
  margin: 0.4rem 0 0.1rem;
  line-height: 1.2;
}}
.pf-ladder-rungs > span {{
  flex: 1 1 0;
  min-width: 0;
  text-align: center;
  padding: 0.28rem 0.1rem 0.32rem;
  border-radius: 6px;
  border: 1px solid transparent;
}}
.pf-ladder-rung-name {{
  display: block;
  font-size: 0.72rem;
  font-weight: 700;
  color: #475569;
  margin-bottom: 0.08rem;
}}
.pf-ladder-rung-px {{
  display: block;
  font-size: 0.78rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
  color: #334155;
}}
.pf-rung-past .pf-ladder-rung-name,
.pf-rung-past .pf-ladder-rung-px {{
  color: #64748b;
}}
.pf-rung-now {{
  background: #e4ebe4;
  border-color: #9bb5a6;
}}
.pf-rung-now .pf-ladder-rung-name {{
  color: #2d4a3c;
}}
.pf-rung-now .pf-ladder-rung-px {{
  color: #1c1a16;
  font-size: 0.82rem;
  font-weight: 800;
}}
.pf-rung-next .pf-ladder-rung-name,
.pf-rung-next .pf-ladder-rung-px {{
  color: #94a3b8;
}}
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
  background: #f3efe6;
  border-left: 2px solid #2d4a3c;
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
  color: #1c1a16 !important;
  letter-spacing: -0.015em;
}}

/* Shared page identity — every menu */
.ap-page-head {{
  margin: 0 0 0.85rem;
  padding: 0.85rem 0.95rem 0.9rem;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: rgba(255,255,255,0.94);
  border-left: 4px solid #2d4a3c;
}}
.ap-page-kicker {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #2d4a3c;
  margin: 0 0 0.22rem;
}}
.ap-page-head .v2-section-label {{
  margin: 0 0 0.25rem;
}}
.ap-page-title {{
  margin: 0;
  font-size: 1.32rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #1c1a16;
  line-height: 1.25;
}}
.ap-page-lead {{
  margin: 0.4rem 0 0;
  font-size: 0.88rem;
  line-height: 1.45;
  color: #6f6a60;
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
  color: #2d4a3c;
  margin: 0 0 0.2rem;
}}
.ap-panel-title {{
  margin: 0 0 0.35rem;
  font-size: 1.12rem;
  font-weight: 700;
  color: #1c1a16;
  letter-spacing: -0.015em;
}}
.ap-panel-desc {{
  margin: 0 0 0.75rem;
  font-size: 0.84rem;
  line-height: 1.4;
  color: #6f6a60;
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
  color: #1c1a16;
  margin: 0 0 0.35rem;
}}
.ap-chip-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 0.45rem;
  margin: 0 0 0.75rem;
}}
.ap-chip {{
  display: inline-flex;
  align-items: center;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  padding: 0.18rem 0.55rem;
  border-radius: 999px;
  line-height: 1.3;
}}
.ap-chip-ok {{
  background: #e4ebe4;
  color: #2d4a3c;
}}
.ap-chip-wait {{
  background: #fef3c7;
  color: #92400e;
}}
.ap-chip-off {{
  background: #e2e8f0;
  color: #475569;
}}
.saa-plain-scroll {{
  overflow-x: auto;
  max-width: 100%;
}}
.ap-fresh-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  margin: 0.15rem 0 0.7rem;
}}
.ap-fresh-table th {{
  text-align: left;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #64748b;
  padding: 0.28rem 0.4rem 0.35rem 0;
  border-bottom: 1px solid #d1d5db;
}}
.ap-fresh-table td {{
  padding: 0.4rem 0.4rem 0.4rem 0;
  border-bottom: 1px solid #e5e7eb;
  color: #1e293b;
  vertical-align: top;
}}
.ap-fresh-table .ap-fresh-path {{
  color: #64748b;
  font-size: 0.75rem;
}}
.ap-fresh-ok {{
  background: #e4ebe4;
  color: #2d4a3c;
}}
.ap-fresh-stale {{
  background: #fef3c7;
  color: #92400e;
}}
.ap-fresh-missing {{
  background: #fee2e2;
  color: #991b1b;
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
  color: #1c1a16 !important;
  letter-spacing: -0.015em !important;
  margin: 0 0 0.2rem !important;
  padding: 0 !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] {{
  margin-bottom: 0.45rem !important;
}}

.pf-watch-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1rem;
  font-size: 0.78rem;
  color: var(--saa-muted);
  margin: 0.05rem 0 0.45rem;
  align-items: center;
}}
.pf-swatch {{
  display: inline-block;
  width: 0.72rem;
  height: 0.72rem;
  border-radius: 3px;
  margin-right: 0.32rem;
  vertical-align: -1px;
  border: 1px solid var(--saa-border-strong);
}}
.pf-swatch-proposal {{ background: var(--saa-proposal-row); }}
.pf-swatch-eligible {{ background: var(--saa-eligible-row); }}
.pf-swatch-blocked {{ background: var(--saa-danger-chip); }}
.pf-swatch-watch {{ background: var(--saa-watch-row); }}
.pf-group-kicker {{
  margin: 0.85rem 0 0.35rem;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--saa-fg);
}}
.pf-group-kicker:first-child {{
  margin-top: 0.2rem;
}}

/* Short sleeve vol-budget Review card */
.svb-card {{
  margin: 0.35rem 0 0.75rem;
  padding: 0.75rem 0.9rem 0.7rem;
  border-radius: 8px;
  border: 1px solid var(--saa-border-strong);
  background: #f8fafc;
}}
.svb-card-calm {{
  border-color: #c5d4c8;
  background: #f4f7f4;
}}
.svb-card-elevated {{
  border-color: #f0c36a;
  background: #fffbeb;
}}
.svb-card-extreme {{
  border-color: #f0a8a8;
  background: #fef2f2;
}}
.svb-card-missing {{
  border-color: #cbd5e1;
  background: #f8fafc;
}}
.svb-kicker {{
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #64748b;
  margin-bottom: 0.35rem;
}}
.svb-card-elevated .svb-kicker {{ color: #92400e; }}
.svb-card-extreme .svb-kicker {{ color: #991b1b; }}
.svb-card-calm .svb-kicker {{ color: #3d5a45; }}
.svb-head {{
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.55rem 1.25rem;
  margin-bottom: 0.55rem;
}}
.svb-level {{
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #1c1a16;
  line-height: 1.25;
}}
.svb-card-elevated .svb-level {{ color: #92400e; }}
.svb-card-extreme .svb-level {{ color: #991b1b; }}
.svb-card-calm .svb-level {{ color: #2d4a3c; }}
.svb-scale-wrap {{
  text-align: left;
}}
.svb-scale {{
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.1;
  color: #1c1a16;
}}
.svb-card-elevated .svb-scale {{ color: #b45309; }}
.svb-card-extreme .svb-scale {{ color: #b91c1c; }}
.svb-scale-label {{
  display: block;
  font-size: 0.72rem;
  font-weight: 600;
  color: #64748b;
  margin-top: 0.1rem;
}}
.svb-row {{
  display: grid;
  grid-template-columns: 2.6rem 1fr;
  gap: 0.35rem 0.55rem;
  align-items: start;
  margin: 0.28rem 0;
  font-size: 0.86rem;
  line-height: 1.4;
  color: #1c1a16;
}}
.svb-row-lab {{
  font-size: 0.72rem;
  font-weight: 700;
  color: #64748b;
  padding-top: 0.12rem;
}}
.svb-metrics {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}}
.svb-chip {{
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.06);
  font-size: 0.78rem;
  font-weight: 600;
  color: #334155;
}}
.svb-foot {{
  margin-top: 0.45rem;
  padding-top: 0.4rem;
  border-top: 1px solid rgba(15, 23, 42, 0.08);
  font-size: 0.75rem;
  color: #64748b;
  line-height: 1.4;
}}

@media (min-width: 768px) {{
  [data-testid="stAppViewContainer"] .main .block-container {{
    max-width: 1120px;
  }}
}}
@media (max-width: 640px) {{
  [data-testid="stAppViewContainer"] .main .block-container {{
    max-width: 100% !important;
    padding-left: 0.75rem;
    padding-right: 0.75rem;
  }}
}}
</style>
        """
    inner = css.split("<style>", 1)[-1].rsplit("</style>", 1)[0]
    themed = apply_color_tokens(inner)
    st.markdown(
        f"<style>\n{css_variables(theme)}\n{themed}\n{_WIDGET_OVERRIDES}\n</style>",
        unsafe_allow_html=True,
    )


def status_card_class(level: str) -> str:
    return {
        "ok": "alpha-card alpha-card-ok",
        "warn": "alpha-card alpha-card-warn",
        "danger": "alpha-card alpha-card-danger",
        "muted": "alpha-card alpha-card-muted",
    }.get(level, "alpha-card alpha-card-muted")
