"""Re-run alpha/hakedaka diagnostics on current data and compare to morning snapshot.

Usage:
  python scripts/verify_prices_history_impact.py

Writes:
  outputs/prices_history_impact_check.json
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

MORNING_BASELINE_SOURCE = "outputs/ai_export_bundle.json (daily_brief, pipeline ~10:38 pre-D1)"


def _load_morning_baseline(output_dir: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Canonical pre-D1 morning metrics from ai_export_bundle daily_brief."""
    bundle_path = output_dir / "ai_export_bundle.json"
    if not bundle_path.exists():
        raise FileNotFoundError(f"morning baseline missing: {bundle_path}")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    brief = bundle.get("daily_brief") or {}
    hk = brief.get("hakedaka_data_quality") or {}
    # Alpha gate: prefer embedded system_health excluded_summary if present
    alpha_before = {
        "run_id": "2026-07-08T10:18:15+09:00",
        "alpha_gate_status": "GREEN",
        "alpha_candidate_count": (brief.get("alpha_legacy") or {}).get("candidate_count")
        or (brief.get("alpha_v0_2") or {}).get("candidate_count"),
        "shortlist_count": None,
        "b_grade_count": None,
        "buy_ready_count": None,
        "missing_price": None,
        "stale_data": None,
        "missing_fundamentals": None,
    }
    for chk in (bundle.get("system_health") or {}).get("checks") or []:
        if not isinstance(chk, dict):
            continue
        detail = chk.get("detail") or {}
        ex = detail.get("excluded_summary") if isinstance(detail, dict) else None
        if isinstance(ex, dict) and "missing_price" in ex:
            alpha_before["missing_price"] = ex.get("missing_price")
            alpha_before["stale_data"] = ex.get("stale_data")
            alpha_before["missing_fundamentals"] = ex.get("missing_fundamentals")
            break
    # Fallback: parse acceptance / gpt_context sections in bundle
    gpt = bundle.get("gpt_context") or {}
    if gpt.get("excluded_summary"):
        ex = gpt["excluded_summary"]
        alpha_before.setdefault("missing_price", ex.get("missing_price"))
        alpha_before.setdefault("stale_data", ex.get("stale_data"))
        alpha_before.setdefault("missing_fundamentals", ex.get("missing_fundamentals"))
    alpha_path = output_dir / "alpha_gate_diagnostics.json"
    if alpha_path.exists():
        live_morning = _load_json(alpha_path)
        # Only trust file if run_id matches morning pipeline (not a partial rerun)
        if str(live_morning.get("run_id", "")).startswith("2026-07-08T10:18"):
            alpha_before = _alpha_metrics(live_morning)
    hakedaka_before = {
        "missing_price_count": hk.get("missing_price_count"),
        "data_quality_below_60": hk.get("data_quality_below_60"),
        "tier_h_price_coverage_pct": hk.get("tier_h_price_coverage_pct"),
        "tier_h_count": hk.get("tier_h_count"),
        "verified_hunt_count": hk.get("verified_hunt_count"),
        "avg_data_quality_score": hk.get("avg_data_quality_score"),
    }
    return alpha_before, hakedaka_before, MORNING_BASELINE_SOURCE


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _alpha_metrics(doc: dict[str, Any]) -> dict[str, Any]:
    ex = (doc.get("fundamental_data_status") or {}).get("excluded_summary") or {}
    return {
        "run_id": doc.get("run_id"),
        "alpha_gate_status": doc.get("alpha_gate_status"),
        "alpha_candidate_count": doc.get("alpha_candidate_count"),
        "shortlist_count": doc.get("shortlist_count"),
        "b_grade_count": doc.get("b_grade_count"),
        "buy_ready_count": doc.get("buy_ready_count"),
        "missing_price": ex.get("missing_price"),
        "stale_data": ex.get("stale_data"),
        "missing_fundamentals": ex.get("missing_fundamentals"),
    }


def _hakedaka_metrics(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "missing_price_count": doc.get("missing_price_count"),
        "data_quality_below_60": doc.get("data_quality_below_60"),
        "tier_h_price_coverage_pct": doc.get("tier_h_price_coverage_pct"),
        "tier_h_count": doc.get("tier_h_count"),
        "verified_hunt_count": doc.get("verified_hunt_count"),
        "avg_data_quality_score": doc.get("avg_data_quality_score"),
    }


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    st = path.stat()
    return {
        "exists": True,
        "mtime_iso": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "size_bytes": st.st_size,
    }


def main() -> int:
    data_dir = ROOT / "data"
    output_dir = ROOT / "outputs"
    quarantine = output_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)

    alpha_path = output_dir / "alpha_gate_diagnostics.json"
    hakedaka_path = output_dir / "hakedaka_data_quality_report.json"

    pre_a, pre_h, baseline_source = _load_morning_baseline(output_dir)
    morning_alpha_meta = _file_meta(alpha_path)
    morning_hakedaka_meta = _file_meta(hakedaka_path)

    if alpha_path.exists():
        shutil.copy2(alpha_path, quarantine / "alpha_gate_diagnostics_pre_rerun_copy.json")
    if hakedaka_path.exists():
        shutil.copy2(hakedaka_path, quarantine / "hakedaka_data_quality_report_pre_rerun_copy.json")

    from src.validation.alpha_gate_diagnostics import write_alpha_gate_diagnostics
    from src.data_refresh.tier_h import ensure_tier_h_prices
    try:
        from src.value_list.hakedaka_data_quality import write_hakedaka_data_quality_report
    except ImportError:
        write_hakedaka_data_quality_report = None  # value_list archived

    as_of = "2026-07-08"
    bundle = json.loads((output_dir / "ai_export_bundle.json").read_text(encoding="utf-8"))
    brief = bundle.get("daily_brief") or {}
    if brief.get("as_of"):
        as_of = str(brief["as_of"])[:10]

    post_alpha = write_alpha_gate_diagnostics(data_dir, output_dir)
    tier_h = ensure_tier_h_prices(data_dir, as_of, fetch_missing=False)
    if write_hakedaka_data_quality_report is None:
        print("skip hakedaka_data_quality (value_list archived)")
        return
    post_hakedaka = write_hakedaka_data_quality_report(
        data_dir,
        output_dir,
        as_of=as_of,
        tier_h_coverage_pct=tier_h.coverage_pct,
    )

    post_alpha_meta = _file_meta(alpha_path)
    post_hakedaka_meta = _file_meta(hakedaka_path)

    pre_a = pre_a  # from morning baseline loader
    post_a = _alpha_metrics(post_alpha)
    pre_h = pre_h
    post_h = _hakedaka_metrics(post_hakedaka)

    # Price-coverage impact fields (exclude tier_h metadata if prices.csv unchanged)
    price_impact_keys_alpha = {
        "missing_price", "stale_data", "missing_fundamentals",
        "alpha_candidate_count", "shortlist_count", "buy_ready_count", "alpha_gate_status",
    }
    price_impact_keys_hakedaka = {"missing_price_count", "data_quality_below_60"}

    alpha_changed = {
        k: {"before": pre_a.get(k), "after": post_a.get(k)}
        for k in price_impact_keys_alpha
        if pre_a.get(k) != post_a.get(k)
    }
    hakedaka_changed = {
        k: {"before": pre_h.get(k), "after": post_h.get(k)}
        for k in price_impact_keys_hakedaka
        if pre_h.get(k) != post_h.get(k)
    }
    hakedaka_other_changed = {
        k: {"before": pre_h.get(k), "after": post_h.get(k)}
        for k in pre_h
        if k not in price_impact_keys_hakedaka and pre_h.get(k) != post_h.get(k)
    }

    report = {
        "schema_version": "1.0",
        "purpose": "prices_history_incident_impact_check",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "morning_baseline_source": baseline_source,
        "morning_file_meta": {
            "alpha_gate_diagnostics": morning_alpha_meta,
            "hakedaka_data_quality_report": morning_hakedaka_meta,
        },
        "post_rerun_file_meta": {
            "alpha_gate_diagnostics": post_alpha_meta,
            "hakedaka_data_quality_report": post_hakedaka_meta,
        },
        "files_regenerated": post_alpha_meta.get("mtime_iso") != morning_alpha_meta.get("mtime_iso")
        or post_hakedaka_meta.get("mtime_iso") != morning_hakedaka_meta.get("mtime_iso"),
        "alpha_gate": {
            "before": pre_a,
            "after": post_a,
            "changed_fields": alpha_changed,
            "unchanged": not alpha_changed,
        },
        "hakedaka_quality": {
            "before": pre_h,
            "after": post_h,
            "price_coverage_changed_fields": hakedaka_changed,
            "other_changed_fields": hakedaka_other_changed,
            "unchanged_price_coverage": not hakedaka_changed,
        },
        "impact_verdict": (
            "no_material_change"
            if not alpha_changed and not hakedaka_changed
            else "changed_review_required"
        ),
        "note": (
            "Morning baseline from ai_export_bundle daily_brief (pre-D1 pipeline). "
            "Pre-rerun file copies in outputs/quarantine/*_pre_rerun_copy.json."
        ),
    }

    out_path = output_dir / "prices_history_impact_check.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "impact_verdict": report["impact_verdict"],
        "files_regenerated": report["files_regenerated"],
        "alpha_changed": list(alpha_changed.keys()),
        "hakedaka_price_coverage_changed": list(hakedaka_changed.keys()),
        "hakedaka_other_changed": list(hakedaka_other_changed.keys()),
        "report": str(out_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
