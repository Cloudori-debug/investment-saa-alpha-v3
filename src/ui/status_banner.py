from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from src.ui.helpers import load_output_csv, load_output_json

OVERALL_CLASS = {"GREEN": "pill-green", "YELLOW": "pill-yellow", "RED": "pill-red"}
SCOPE_HINT = {
    "NO_TRADE": "매매 보류",
    "ETF_ONLY": "ETF·현금만",
    "ETF_ONLY_ALPHA_REVIEW": "ETF + 알파 검토",
    "ETF_AND_BETA": "베타 포함",
    "FULL_WITH_ALPHA": "알파 포함",
}


def _market_as_of(data_dir: Path) -> str:
    path = data_dir / "market_indicators.csv"
    if not path.exists():
        return "—"
    import pandas as pd

    df = pd.read_csv(path, dtype=str, nrows=1)
    if df.empty:
        return "—"
    return str(df.iloc[0].get("date", "—")) or "—"


def _run_label(output_dir: Path) -> str:
    manifest = load_output_json(output_dir, "run_manifest.json")
    if not manifest:
        return "미실행"
    gen = str(manifest.get("generated_at", ""))[:10]
    if gen == date.today().isoformat():
        return "오늘 ✓"
    return gen or "—"


def render_operational_status(
    data_dir: Path,
    output_dir: Path,
    *,
    compact: bool = False,
) -> None:
    """운용 스냅샷 — 대시보드·사이드바·종합 포트 상단."""
    final = load_output_json(output_dir, "final_execution_decision.json") or {}
    ac = load_output_json(output_dir, "acceptance_report.json") or {}
    compass = load_output_json(output_dir, "compass_regime.json") or {}
    macro = load_output_json(output_dir, "macro_scenario.json") or {}

    overall = str(final.get("system_status") or ac.get("overall", "—"))
    scope = str(final.get("execution_scope") or ac.get("execution_scope", "—"))
    dry = int(final.get("dry_run_days") or ac.get("dry_run_days", 0))
    gate = str(compass.get("data_gate", "—"))
    market = _market_as_of(data_dir)
    run_lbl = _run_label(output_dir)
    macro_lbl = macro.get("label", "")

    pill = OVERALL_CLASS.get(overall, "pill-muted")

    if compact:
        st.markdown(
            f"""<div class="ops-status-card">
            <span class="ops-pill {pill}">{overall}</span>
            <span class="ops-pill pill-muted">{scope}</span><br>
            <strong>dry-run</strong> {dry}/10 · <strong>Gate</strong> {gate}<br>
            시장 {market} · 분석 {run_lbl}
            </div>""",
            unsafe_allow_html=True,
        )
        return

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("운용", overall, delta=SCOPE_HINT.get(scope, scope))
    c2.metric("Data Gate", gate)
    c3.metric("dry-run", f"{dry}/10")
    c4.metric("시장 기준일", market)
    c5.metric("분석", run_lbl)
    if macro_lbl:
        c6.metric("거시", macro_lbl[:12] + ("…" if len(macro_lbl) > 12 else ""))
    else:
        c6.metric("거시", "—")

    trade = load_output_csv(output_dir, "trade_actions.csv")
    if trade is not None and not trade.empty:
        buys = trade[trade["action"].isin(["Buy-allowed", "Add"])]
        if not buys.empty:
            names = ", ".join(
                f"{r.get('name', r.get('ticker', ''))}" for _, r in buys.head(3).iterrows()
            )
            st.caption(f"💡 Executable 매수 후보: {names}" + (" …" if len(buys) > 3 else ""))


def render_sidebar_status(data_dir: Path, output_dir: Path) -> None:
    st.markdown("**오늘 상태**")
    render_operational_status(data_dir, output_dir, compact=True)
