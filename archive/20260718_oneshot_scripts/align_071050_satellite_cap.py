"""Shrink 071050 to target_matrix satellite sleeve cap (audit path).

Usage:
  python scripts/align_071050_satellite_cap.py          # dry-run
  python scripts/align_071050_satellite_cap.py --apply
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TICKER = "071050"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from src.alpha.portfolio_selector import (
        load_satellite_single_name_sleeve_pct,
        sleeve_pct_to_portfolio,
    )
    from src.alpha.target_bridge import (
        TargetChange,
        TargetProposal,
        apply_proposed_target,
        compute_add_bands,
        kr_alpha_target_sum,
        load_kr_alpha_budget,
        write_proposal_outputs,
    )
    from src.config import load_portfolio_policy
    from src.data_loader import load_positions, load_target_portfolio
    from src.validators import validate_inputs

    data_dir = ROOT / "data"
    output_dir = ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = data_dir / "target_portfolio.csv"

    before = load_target_portfolio(target_path)
    budget = load_kr_alpha_budget(output_dir)
    if budget is None:
        budget = kr_alpha_target_sum(before)
    sleeve = load_satellite_single_name_sleeve_pct()
    cap = sleeve_pct_to_portfolio(sleeve, budget)

    rows = []
    changes = []
    freed = 0.0
    for row in before:
        updated = row.model_copy(deep=True)
        if updated.ticker == TICKER and updated.asset_group == "kr_alpha":
            old = updated.target_weight
            updated.target_weight = cap
            min_w, max_w = compute_add_bands(
                cap, role=updated.role, kr_alpha_budget=budget
            )
            updated.min_weight = min_w
            updated.max_weight = max_w
            freed = round(old - cap, 2)
            changes.append(
                TargetChange(
                    TICKER,
                    updated.name,
                    "adjust",
                    old,
                    cap,
                    "kr_alpha",
                    "satellite_cap_alignment",
                )
            )
            print(f"{TICKER}: {old} → {cap} (sleeve {sleeve}% @ budget {budget:.2f}%)")
        rows.append(updated)

    if not changes:
        raise SystemExit(f"{TICKER} not found in kr_alpha target")

    # 합계 100% 유지: 축소분을 CASH로 (다른 kr_alpha 재배분·정규화로 캡 재초과 방지)
    if freed > 0:
        cash = next((r for r in rows if r.ticker == "CASH"), None)
        if cash is None:
            raise SystemExit("CASH row missing — cannot park freed weight")
        old_cash = cash.target_weight
        cash.target_weight = round(old_cash + freed, 2)
        if cash.target_weight > cash.max_weight:
            cash.max_weight = round(cash.target_weight, 2)
        changes.append(
            TargetChange(
                "CASH",
                cash.name,
                "adjust",
                old_cash,
                cash.target_weight,
                cash.asset_group,
                "satellite_cap_alignment_park_freed_to_cash",
            )
        )
        print(f"CASH: {old_cash} → {cash.target_weight} (+{freed} freed)")

    proposal = TargetProposal(
        rows=rows,
        changes=changes,
        kr_alpha_sum=kr_alpha_target_sum(rows),
        kr_alpha_budget=budget,
        warnings=["satellite_cap_alignment — target only, not an execution order"],
    )
    write_proposal_outputs(proposal, output_dir)

    policy = load_portfolio_policy(data_dir / "portfolio_policy.yaml")
    positions = load_positions(data_dir / "positions.csv")
    pre = validate_inputs(positions, before, policy)
    post = validate_inputs(positions, proposal.rows, policy)
    band_pre = [w for w in pre.warnings if "outside min/max band" in w]
    band_post = [w for w in post.warnings if "outside min/max band" in w]
    print(f"band warnings before={len(band_pre)} after={len(band_post)}")
    print(f"validate_inputs gate before={pre.data_gate} after={post.data_gate}")

    if not args.apply:
        print("dry-run only (pass --apply to write)")
        return

    apply_proposed_target(
        proposal,
        target_path,
        backup_dir=data_dir / "backups",
        approved_by="human",
        data_dir=data_dir,
        output_dir=output_dir,
        write_reason="satellite_cap_alignment",
    )
    written = load_target_portfolio(target_path)
    final = validate_inputs(positions, written, policy)
    row_071 = next(r for r in written if r.ticker == TICKER)
    print(
        json.dumps(
            {
                "applied": True,
                "write_reason": "satellite_cap_alignment",
                "ticker": TICKER,
                "new_target": row_071.target_weight,
                "new_min": row_071.min_weight,
                "new_max": row_071.max_weight,
                "kr_alpha_budget_used": budget,
                "satellite_sleeve_pct": sleeve,
                "band_warnings": [w for w in final.warnings if "outside min/max band" in w],
                "input_validation_gate": final.data_gate,
                "note": (
                    "target_weight change only — not an execution order; "
                    "Actual Buy Allowed remains blocked by policy_cap / ETF_ONLY scope"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
