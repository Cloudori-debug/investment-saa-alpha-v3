"""One-shot kr_alpha min/max band resync via decompose (audit path).

Usage:
  python scripts/resync_kr_alpha_bands.py          # dry-run
  python scripts/resync_kr_alpha_bands.py --apply  # write via apply_proposed_target
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Resync kr_alpha min/max bands (band_resync)")
    parser.add_argument("--apply", action="store_true", help="Write via apply_proposed_target")
    args = parser.parse_args()

    from src.alpha.target_bridge import (
        apply_proposed_target,
        build_band_resync_proposal,
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
    before_kr = {
        r.ticker: (r.target_weight, r.min_weight, r.max_weight)
        for r in before
        if r.asset_group == "kr_alpha"
    }

    proposal = build_band_resync_proposal(before)
    write_proposal_outputs(proposal, output_dir)

    after_kr = {
        r.ticker: (r.target_weight, r.min_weight, r.max_weight)
        for r in proposal.rows
        if r.asset_group == "kr_alpha"
    }

    print("=== band_resync diff (kr_alpha) ===")
    for ticker in sorted(set(before_kr) | set(after_kr)):
        b = before_kr.get(ticker)
        a = after_kr.get(ticker)
        print(f"{ticker}: before={b} after={a}")

    policy = load_portfolio_policy(data_dir / "portfolio_policy.yaml")
    positions = load_positions(data_dir / "positions.csv")
    pre = validate_inputs(positions, before, policy)
    post = validate_inputs(positions, proposal.rows, policy)
    band_warn = [w for w in pre.warnings if "outside min/max band" in w]
    band_warn_after = [w for w in post.warnings if "outside min/max band" in w]
    print(f"band warnings before={len(band_warn)} after={len(band_warn_after)}")
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
        write_reason="band_resync",
    )
    written = load_target_portfolio(target_path)
    final = validate_inputs(positions, written, policy)
    print(
        json.dumps(
            {
                "applied": True,
                "write_reason": "band_resync",
                "band_warnings": [w for w in final.warnings if "outside min/max band" in w],
                "input_validation_gate": final.data_gate,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
