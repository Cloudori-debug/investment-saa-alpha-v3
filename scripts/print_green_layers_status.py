#!/usr/bin/env python3
"""Print GREEN layer status after pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
OUT = ROOT / "outputs"


def main() -> int:
    from src.validation.green_layers import evaluate_green_layers, format_green_layer_table_lines

    green = evaluate_green_layers(DATA, OUT)
    print("\n| Layer | Status |")
    print("|-------|--------|")
    for layer in ("technical", "operational", "market", "full"):
        print(f"| {layer.capitalize()} | {green.get(f'{layer}_status')} |")

    print(f"\nActual Buy Allowed: {green.get('actual_buy_allowed')}")
    print(f"risk_reduce_only: {green.get('risk_reduce_only')}")
    print(f"execution_scope: {green.get('execution_scope')}")
    print(f"execution_scope_explanation: {green.get('execution_scope_explanation')}")
    print(f"acceptance_overall: {green.get('acceptance_overall')}")
    print(f"target_write_audit_status: {green.get('target_write_audit_status')}")
    print(f"saa_restart_readiness: {green.get('saa_restart_readiness')}")
    print(f"kr_alpha_restart_readiness: {green.get('kr_alpha_restart_readiness')}")

    if green.get("market_blockers"):
        print("\nmarket_blockers (all):")
        for b in green["market_blockers"]:
            print(f"  - {b}")
    if green.get("market_unknowns"):
        print("\nmarket_unknowns:")
        for u in green["market_unknowns"]:
            print(f"  - {u}")
    if green.get("operational_blockers"):
        print("\noperational_blockers:")
        for b in green["operational_blockers"]:
            print(f"  - {b}")

    print("\n--- daily_report table preview ---")
    print("\n".join(format_green_layer_table_lines(green)))

    acc = OUT / "acceptance_report.json"
    if acc.exists():
        doc = json.loads(acc.read_text(encoding="utf-8"))
        print("\nacceptance_report green fields:", doc.get("technical_status"), doc.get("full_status"))
        print(f"saa_restart_readiness_verdict: {doc.get('saa_restart_readiness_verdict', '—')}")

    saa_path = OUT / "saa_restart_readiness_report.json"
    if saa_path.exists():
        saa = json.loads(saa_path.read_text(encoding="utf-8"))
        print(f"\nSAA Restart Readiness: {saa.get('verdict')}")
        print(f"Next allowed action: {saa.get('next_allowed_action')}")
        print(f"First eligible if Buy>0: {saa.get('first_eligible_asset_class_if_buy_allowed')}")
        if saa.get("blockers_to_clear"):
            print("\nBlockers to clear:")
            for b in saa["blockers_to_clear"]:
                print(f"  - {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
