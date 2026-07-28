"""Remove 030190, normalize targets, run pipeline, export zip, verify."""
from __future__ import annotations

import json
from pathlib import Path

from src.alpha.target_portfolio_guard import evaluate_target_guard, operational_target_path
from src.alpha.target_write_audit import get_last_target_write_audit, write_operational_target
from src.data_loader import load_target_portfolio, normalize_target_weights_to_100, write_target_portfolio
from src.full_pipeline import run_full_pipeline
from src.report.io_utils import read_output_json
from src.validation.ai_export import build_export_zip, prepare_export_bundle
from src.validation.bundle_consistency import verify_bundle_snapshot_alignment
from src.validation.green_layers import evaluate_green_layers


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    out = root / "outputs"

    rows = [r for r in load_target_portfolio(data / "user_target_portfolio.csv") if r.ticker != "030190"]
    scaled, _ = normalize_target_weights_to_100(rows)
    write_target_portfolio(scaled, data / "user_target_portfolio.csv")

    from src.validation.bundle_consistency import resolve_pipeline_run_id

    run_id = resolve_pipeline_run_id(out)
    result = write_operational_target(
        data,
        scaled,
        source="manual_admin_override",
        reason="remove_unintended_030190_reintroduced_by_approval_bridge",
        approved_by_user=True,
        writer_module="scripts.remove_030190_clean_run",
        output_dir=out,
        run_id=run_id,
        sync_user_target=False,
    )
    if not result.success:
        raise SystemExit(f"target write failed: {result.audit}")

    run_full_pipeline(data, out)

    bundle = prepare_export_bundle(data, out)
    zip_path = out / "ai_cross_validation_post_030190_block.zip"
    zip_path.write_bytes(build_export_zip(bundle))

    guard = evaluate_target_guard(data, out)
    align = verify_bundle_snapshot_alignment(out)
    green = evaluate_green_layers(data, out)
    acc = read_output_json(out / "acceptance_report.json") or {}
    brief = bundle.get("daily_brief") or {}
    ss = brief.get("system_status") or {}
    sh = json.loads((out / "system_health.json").read_text(encoding="utf-8"))
    op_tickers: list[str] = []
    for chk in sh.get("checks") or []:
        if chk.get("name") == "fundamentals_coverage":
            op_tickers = list((chk.get("detail") or {}).get("operational_tickers") or [])
            break
    cvt = (bundle.get("tables_summary") or {}).get("current_vs_target") or []
    has_030190_cvt = any(
        isinstance(r, dict) and str(r.get("ticker")) == "030190" for r in cvt
    )
    audit = get_last_target_write_audit(out)
    blocked = json.loads((data / "target_portfolio_write_guard.json").read_text(encoding="utf-8")).get(
        "blocked_reintroductions", {}
    )

    checks = {
        "030190_in_user_target": ss.get("030190_in_user_target"),
        "030190_in_operational_target": ss.get("030190_in_operational_target"),
        "030190_in_operational_tickers": "030190" in op_tickers,
        "030190_in_current_vs_target": has_030190_cvt,
        "target_guard_pass": guard.get("severity") == "PASS",
        "changed_rows": guard.get("changed_rows"),
        "proposal_leak": guard.get("system_proposal_leak_count"),
        "conflict": read_output_json(out / "final_execution_decision.json").get(
            "target_guard_conflict_detected"
        ),
        "export_pass": bundle.get("export_bundle_validation", {}).get("pass"),
        "acceptance_overall": acc.get("overall"),
        "execution_scope": acc.get("execution_scope"),
        "actual_buy_allowed": green.get("actual_buy_allowed"),
        "technical": green.get("technical_status"),
        "blocked_030190": "030190" in blocked,
        "audit_reason": audit.get("target_write_reason"),
        "zip": str(zip_path),
    }
    report_path = out / "remove_030190_verification.json"
    report_path.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    failures = [
        k
        for k, v in checks.items()
        if k.startswith("030190_") and v is True
    ]
    if failures or checks["target_guard_pass"] is not True or checks["export_pass"] is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
