"""Alpha sector mapping diagnostic — read-only, no scoring/target changes."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.alpha.loaders import load_universe, load_fundamentals, load_prices
from src.alpha.universe_filter import filter_universe
from src.alpha.loaders import load_universe_filter_config
from src.field_normalize import normalize_sector


def _read_csv_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    df = pd.read_csv(path, dtype=str, nrows=0)
    full = pd.read_csv(path, dtype=str, keep_default_na=False)
    return {
        "path": str(path),
        "exists": True,
        "rows": len(full),
        "columns": list(df.columns),
        "ticker_samples": full["ticker"].head(20).tolist() if "ticker" in full.columns else [],
    }


def _sector_counts(labels: list[str]) -> dict[str, Any]:
    norm = [normalize_sector(x) for x in labels]
    unknown = sum(1 for s in norm if s == "unknown")
    n = len(norm) or 1
    filled = {s: norm.count(s) for s in sorted(set(norm)) if s != "unknown"}
    return {
        "total": len(norm),
        "unknown_count": unknown,
        "unknown_pct": round(100 * unknown / n, 1),
        "filled_count": n - unknown,
        "filled_pct": round(100 * (n - unknown) / n, 1),
        "by_sector": filled,
    }


def _map_top_from_universe(data_dir: Path, tickers: list[str]) -> list[dict[str, Any]]:
    uni = pd.read_csv(data_dir / "universe.csv", dtype=str, keep_default_na=False)
    out = []
    for t in tickers:
        row = uni[uni["ticker"] == t]
        if row.empty:
            out.append({"ticker": t, "in_universe": False})
            continue
        r = row.iloc[0]
        raw_sector = str(r.get("sector", ""))
        raw_industry = str(r.get("industry", ""))
        out.append(
            {
                "ticker": t,
                "name": r.get("name", ""),
                "in_universe": True,
                "raw_sector": raw_sector,
                "raw_industry": raw_industry,
                "normalized_sector": normalize_sector(raw_sector),
                "mapping_possible_from_source": bool(str(raw_sector).strip() or str(raw_industry).strip()),
            }
        )
    return out


def _pipeline_stage_counts(data_dir: Path, output_dir: Path, as_of: str) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []

    uni_path = data_dir / "universe.csv"
    uni_df = pd.read_csv(uni_path, dtype=str, keep_default_na=False)
    stages.append(
        {
            "stage": "source_universe_csv",
            "row_count": len(uni_df),
            **_sector_counts(uni_df.get("sector", pd.Series(dtype=str)).tolist()),
        }
    )

    universe = load_universe(uni_path)
    stages.append(
        {
            "stage": "after_load_universe (UniverseRecord)",
            "row_count": len(universe),
            **_sector_counts([u.sector for u in universe]),
        }
    )

    cfg = load_universe_filter_config(data_dir / "universe_filter.yaml")
    prices = {p.ticker: p for p in load_prices(data_dir / "prices.csv", as_of=as_of)}
    passed, _excluded = filter_universe(universe, prices, cfg, as_of)
    stages.append(
        {
            "stage": "after_universe_filter (passed)",
            "row_count": len(passed),
            **_sector_counts([u.sector for u in passed]),
        }
    )

    cand_path = output_dir / "alpha_candidates.csv"
    if cand_path.exists():
        cand = pd.read_csv(cand_path, dtype=str, keep_default_na=False)
        stages.append(
            {
                "stage": "alpha_candidates_csv (top output)",
                "row_count": len(cand),
                **_sector_counts(cand.get("sector", pd.Series(dtype=str)).tolist()),
            }
        )

    sl_path = output_dir / "alpha_shortlist.csv"
    if sl_path.exists():
        sl = pd.read_csv(sl_path, dtype=str, keep_default_na=False)
        stages.append(
            {
                "stage": "alpha_shortlist_csv",
                "row_count": len(sl),
                **_sector_counts(sl.get("sector", pd.Series(dtype=str)).tolist()),
            }
        )

    return stages


def _evaluate_gate(data: dict[str, Any]) -> dict[str, Any]:
    top = data.get("top14_mapping") or []
    unknown_pct = 100.0
    if top:
        unknown_pct = 100 * sum(1 for r in top if r.get("normalized_sector") == "unknown") / len(top)

    target_sw = data.get("target_portfolio_kr_alpha_sector_weights") or {}
    unknown_in_targets = float(target_sw.get("unknown", 0))
    candidate_unknown = unknown_pct

    recommendation = "KEEP_GREEN_WITH_EXECUTION_BLOCK"
    if candidate_unknown >= 50:
        recommendation = "YELLOW_DATA_LIMITED_RECOMMENDED"
    if candidate_unknown >= 100:
        recommendation = "YELLOW_DATA_LIMITED_STRONGLY_RECOMMENDED"

    return {
        "shortlist_unknown_pct": unknown_pct,
        "target_portfolio_unknown_weight_pct": unknown_in_targets,
        "current_alpha_gate": data.get("acceptance", {}).get("alpha_gate", "—"),
        "current_execution_block": "BLOCK_NEW_BUY (unchanged by this diagnostic)",
        "why_gate_stays_green": (
            "adjust_gate_for_sector_coverage() uses kr_meta.sector_weights from "
            "target_portfolio.csv kr_alpha rows (named sectors), not alpha candidate sectors. "
            f"Candidate unknown share ({candidate_unknown:.0f}%) is therefore invisible to that check."
        ),
        "recommendation": recommendation,
        "note": "Execution already blocked; gate downgrade would be conservative labeling only.",
    }


def build_diagnostic(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    as_of = "2026-07-01"
    acc_path = output_dir / "acceptance_report.json"
    acceptance = {}
    if acc_path.exists():
        acceptance = json.loads(acc_path.read_text(encoding="utf-8"))

    cand = pd.read_csv(output_dir / "alpha_candidates.csv", dtype=str, keep_default_na=False)
    top_tickers = cand["ticker"].head(14).tolist()

    target = pd.read_csv(data_dir / "target_portfolio.csv", dtype=str, keep_default_na=False)
    kr = target[target["asset_group"] == "kr_alpha"]
    kr_sectors = {}
    for _, r in kr.iterrows():
        s = normalize_sector(r.get("sector", ""))
        kr_sectors[s] = kr_sectors.get(s, 0) + float(r.get("target_weight") or 0)

    uni_sector_cols = [c for c in pd.read_csv(data_dir / "universe.csv", nrows=0).columns
                       if any(k in c.lower() for k in ("sector", "industry", "업종", "gics"))]

    data: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "bundle_as_of": acceptance.get("as_of", as_of),
        "run_id": acceptance.get("run_id"),
        "root_cause_summary": (
            "universe.csv has a sector column but 0/945 rows are populated. "
            "PyKRX bulk collector writes sector/industry as empty strings. "
            "normalize_sector('') → 'unknown' at load time; no later merge restores sector."
        ),
        "source_files": {
            "universe.csv": _read_csv_meta(data_dir / "universe.csv"),
            "fundamentals.csv": _read_csv_meta(data_dir / "fundamentals.csv"),
            "prices.csv": _read_csv_meta(data_dir / "prices.csv"),
            "alpha_candidates.csv": _read_csv_meta(output_dir / "alpha_candidates.csv"),
        },
        "sector_related_columns": {
            "universe.csv": uni_sector_cols,
            "fundamentals.csv": [],
            "prices.csv": [],
        },
        "universe_sector_fill": _sector_counts(
            pd.read_csv(data_dir / "universe.csv", dtype=str, keep_default_na=False)["sector"].tolist()
        ),
        "pipeline_stages": _pipeline_stage_counts(data_dir, output_dir, as_of),
        "top14_mapping": _map_top_from_universe(data_dir, top_tickers),
        "target_portfolio_kr_alpha_sector_weights": kr_sectors,
        "acceptance": {
            "overall": acceptance.get("overall"),
            "alpha_gate": next(
                (i.get("message") for i in acceptance.get("items", []) if i.get("id") == "AC-04"),
                None,
            ),
            "dry_run": acceptance.get("dry_run_days"),
        },
        "pykrx_collector_note": {
            "file": "src/data_refresh/pykrx_bulk.py",
            "behavior": "build_universe_rows sets sector='' and industry='' explicitly",
            "lines": "144-145",
        },
        "sector_cap_side_effect": (
            "portfolio_selector sector cap counts all candidates as sector 'unknown', "
            "so cap limits count within one bucket — proposal_size=2 may reflect unknown clustering, "
            "not true sector diversification."
        ),
    }
    data["gate_evaluation"] = _evaluate_gate(data)
    return data


def _to_md(data: dict[str, Any]) -> str:
    lines = [
        "# Alpha Sector Mapping Diagnostic",
        "",
        f"- Generated: {data.get('generated_at')}",
        f"- Bundle as_of: {data.get('bundle_as_of')} · run_id: {data.get('run_id')}",
        "",
        "## Root cause",
        "",
        data.get("root_cause_summary", ""),
        "",
        f"PyKRX collector: `{data.get('pykrx_collector_note', {}).get('file')}` "
        f"({data.get('pykrx_collector_note', {}).get('behavior')})",
        "",
        "## Source file sector fill",
        "",
        f"- universe.csv: **{data['universe_sector_fill']['filled_count']}/{data['universe_sector_fill']['total']}** "
        f"({data['universe_sector_fill']['filled_pct']}% filled)",
        "- fundamentals.csv: **no sector column**",
        "- prices.csv: **no sector column**",
        "",
        "## Pipeline stages (sector unknown %)",
        "",
        "| Stage | Rows | unknown % |",
        "|-------|------|-----------|",
    ]
    for st in data.get("pipeline_stages", []):
        lines.append(
            f"| {st['stage']} | {st['row_count']} | {st['unknown_pct']}% |"
        )

    lines.extend(["", "## Top 14 candidates → universe source", "", "| Ticker | Name | raw sector | normalized |", "|--------|------|------------|------------|"])
    for r in data.get("top14_mapping", []):
        lines.append(
            f"| {r.get('ticker')} | {r.get('name', '—')} | `{r.get('raw_sector', '—')}` | "
            f"{r.get('normalized_sector', '—')} |"
        )

    ge = data.get("gate_evaluation", {})
    lines.extend([
        "",
        "## Gate evaluation",
        "",
        f"- Shortlist unknown: **{ge.get('shortlist_unknown_pct')}%**",
        f"- Target portfolio kr_alpha unknown weight: **{ge.get('target_portfolio_unknown_weight_pct')}%**",
        f"- Recommendation: **{ge.get('recommendation')}**",
        "",
        ge.get("why_gate_stays_green", ""),
        "",
        "## Sector cap side effect",
        "",
        data.get("sector_cap_side_effect", ""),
        "",
        "> Diagnostic only — no scoring, target, or execution logic changed.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    data_dir = ROOT / "data"
    output_dir = ROOT / "outputs"
    doc = build_diagnostic(data_dir, output_dir)
    json_path = output_dir / "alpha_sector_mapping_diagnostic.json"
    md_path = output_dir / "alpha_sector_mapping_diagnostic.md"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_to_md(doc), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
