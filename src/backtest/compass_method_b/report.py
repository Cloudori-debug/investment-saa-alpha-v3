"""Write Method B markdown / CSV artifacts under outputs/backtest/."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_method_b_outputs(
    out_dir: Path,
    *,
    panel: pd.DataFrame,
    results: pd.DataFrame,
    path: pd.DataFrame,
    data_notes: dict[str, Any],
    perf_summary: dict[str, Any],
    stats: dict[str, Any],
    judgment_history: list[dict[str, Any]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out_dir / "compass_method_b_input.csv", index=False)
    results.to_csv(out_dir / "compass_method_b_results.csv", index=False)
    path.to_csv(out_dir / "compass_method_b_nav_path.csv", index=False)

    log_path = out_dir / "compass_method_b_judgment_log.jsonl"
    with log_path.open("w", encoding="utf-8") as handle:
        for row in judgment_history:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    meta = {
        "data_notes": data_notes,
        "perf_summary": perf_summary,
        "stats": stats,
    }
    (out_dir / "compass_method_b_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    report = _build_report_md(data_notes, perf_summary, stats)
    (out_dir / "compass_method_b_report.md").write_text(report, encoding="utf-8")


def _pct(x: float) -> str:
    if x != x:  # NaN
        return "n/a"
    return f"{100.0 * x:.2f}%"


def _build_report_md(
    data_notes: dict[str, Any],
    perf: dict[str, Any],
    stats: dict[str, Any],
) -> str:
    taa = perf.get("taa") or {}
    saa = perf.get("saa") or {}
    cycles = stats.get("cycles") or {}
    dsr_ex = stats.get("dsr_excess") or {}
    dsr_taa = stats.get("dsr_taa") or {}
    split = stats.get("is_oos") or {}

    lines = [
        "# Compass Method B — External Long-History Backtest Report",
        "",
        "## 1. Data window & limits",
        "",
        f"- Panel: **{data_notes.get('panel_start')} → {data_notes.get('panel_end')}** ({data_notes.get('panel_rows')} rows)",
        f"- Judgment start (after {data_notes.get('warmup_trading_days')}d warmup): **{data_notes.get('judgment_start')}**",
        f"- Korea 10Y: FRED `{data_notes.get('korea_10y_fred_id')}` ({data_notes.get('korea_10y_status')}, monthly ffill)",
        f"- foreign_flow_3d: **{data_notes.get('foreign_flow_3d')}** (accuracy limited on flow axis)",
        f"- tier2: **{data_notes.get('tier2')}** (`compute_compass(..., tier2=None)`)",
        "",
        "### Group return proxies (not ticker-level)",
        "",
    ]
    for k, v in (perf.get("proxy_notes") or {}).items():
        lines.append(f"- `{k}`: {v}")

    lines.extend(
        [
            "",
            "## 2. Performance — SAA vs SAA+TAA",
            "",
            "| Metric | Static SAA | SAA+TAA (compass) |",
            "|---|---:|---:|",
            f"| Cum return | {_pct(saa.get('cum_return', float('nan')))} | {_pct(taa.get('cum_return', float('nan')))} |",
            f"| CAGR | {_pct(saa.get('cagr', float('nan')))} | {_pct(taa.get('cagr', float('nan')))} |",
            f"| Vol (ann) | {_pct(saa.get('vol', float('nan')))} | {_pct(taa.get('vol', float('nan')))} |",
            f"| Max DD | {_pct(saa.get('mdd', float('nan')))} | {_pct(taa.get('mdd', float('nan')))} |",
            f"| Sharpe (ann) | {saa.get('sharpe', float('nan')):.3f} | {taa.get('sharpe', float('nan')):.3f} |",
            f"| N days | {saa.get('n', 0)} | {taa.get('n', 0)} |",
            "",
            f"- Excess mean (daily): **{perf.get('excess_mean_daily', 0):.6f}** (SE {perf.get('excess_se_daily', 0):.6f})",
            f"- Excess ann (×252): **{_pct(perf.get('excess_ann', 0))}**",
            "",
            "### Excess by applied_regime",
            "",
        ]
    )
    for reg, st in (perf.get("regime_excess") or {}).items():
        lines.append(
            f"- `{reg}`: n={st.get('n')}, mean_daily={st.get('mean_excess_daily'):.6f}, sum={st.get('sum_excess'):.4f}"
        )

    lines.extend(
        [
            "",
            "## 3. Regime cycle count (independence check)",
            "",
            f"- Unique regimes seen: {cycles.get('unique_regimes')}",
            f"- Regime flips: **{cycles.get('regime_flips')}** (≈ half-cycles of transitions)",
            f"- Judgment days: {cycles.get('n_judgment_days')}",
            "",
            "> Independent 'full cycles' over ~11 years are few — do not treat daily N as independent trials.",
            "",
            "## 4. Statistical significance (required)",
            "",
            "### Deflated Sharpe on **excess** returns (TAA − SAA)",
            "",
            f"- n_trials (DOF proxy): **{int(dsr_ex.get('n_trials', 16))}**",
            f"- SR̂ (ann, excess): {dsr_ex.get('sr_hat_ann', float('nan')):.3f}",
            f"- SR* (expected max null, daily): {dsr_ex.get('sr_star_daily', float('nan')):.6f}",
            f"- **DSR (P[SR̂ > SR*]): {dsr_ex.get('dsr', float('nan')):.4f}**",
            f"- PSR vs 0: {dsr_ex.get('psr_vs_0', float('nan')):.4f}",
            "",
            "### Deflated Sharpe on absolute TAA returns",
            "",
            f"- SR̂ (ann): {dsr_taa.get('sr_hat_ann', float('nan')):.3f}",
            f"- DSR: {dsr_taa.get('dsr', float('nan')):.4f}",
            "",
            "### IS / OOS split (PBO-lite)",
            "",
            f"- Split date: **{split.get('split_date')}**",
            f"- IS excess ann: {_pct((split.get('is') or {}).get('excess_ann', 0))} · DSR={(split.get('is') or {}).get('dsr', float('nan')):.4f}",
            f"- OOS excess ann: {_pct((split.get('oos') or {}).get('excess_ann', 0))} · DSR={(split.get('oos') or {}).get('dsr', float('nan')):.4f}",
            f"- Same-sign excess IS→OOS: **{split.get('same_sign_excess')}**",
            "",
            "## 5. Interpretation guardrails",
            "",
            "- Harvey–Liu–Zhu: with ≥15 free parameters, classical t≈2.0 is insufficient; DSR/PSR above are the primary significance readouts.",
            "- **Non-significant DSR is a valid outcome** — report as-is; do not tune `compass_rules.yaml` inside this run.",
            "- Live hysteresis under manual override was not the test subject; replay uses `use_manual_regime=False`.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
