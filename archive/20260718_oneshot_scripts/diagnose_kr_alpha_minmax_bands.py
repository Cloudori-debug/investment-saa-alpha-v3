"""Diagnose kr_alpha min/max band vs holdings count (read-only)."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_kr_alpha(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if str(r.get("asset_group", "")).strip() == "kr_alpha":
                rows.append(dict(r))
    return rows


def main() -> None:
    for label, path in [
        ("target_portfolio", ROOT / "data" / "target_portfolio.csv"),
        ("user_target", ROOT / "data" / "user_target_portfolio.csv"),
    ]:
        rows = load_kr_alpha(path)
        print(f"=== {label} n={len(rows)} ===")
        by_min: dict[str, list[str]] = defaultdict(list)
        for r in sorted(rows, key=lambda x: -float(x.get("target_weight") or 0)):
            tw = float(r.get("target_weight") or 0)
            mn = float(r.get("min_weight") or 0)
            mx = float(r.get("max_weight") or 0)
            below = tw < mn - 1e-9
            print(
                f"{r.get('ticker')} tw={tw} min={mn} max={mx} "
                f"role={r.get('role')} tier={r.get('tier')} below_min={below}"
            )
            by_min[str(r.get("min_weight"))].append(str(r.get("ticker")))
        print("min clusters:", {k: v for k, v in by_min.items()})
        print("sum tw", round(sum(float(r.get("target_weight") or 0) for r in rows), 4))

    draft = ROOT / "alpha_portfolio" / "data" / "output" / "target_draft.csv"
    if draft.exists():
        with draft.open(encoding="utf-8-sig", newline="") as f:
            drows = list(csv.DictReader(f))
        print(f"=== target_draft n={len(drows)} ===")
        for r in drows:
            print(
                f"{r.get('ticker')} tw={r.get('target_weight')} min={r.get('min_weight')} "
                f"max={r.get('max_weight')} role={r.get('role')} tier={r.get('tier')} "
                f"action={r.get('matrix_action')} sleeve={r.get('sleeve_weight')}"
            )

    # validator warnings mirror
    from src.config import load_portfolio_policy
    from src.data_loader import load_positions, load_target_portfolio
    from src.validators import validate_inputs

    data = ROOT / "data"
    v = validate_inputs(
        load_positions(data / "positions.csv"),
        load_target_portfolio(data / "target_portfolio.csv"),
        load_portfolio_policy(data / "portfolio_policy.yaml"),
    )
    print("=== validate_inputs ===")
    print("gate", v.data_gate)
    for w in v.warnings:
        print(" warn:", w)


if __name__ == "__main__":
    main()
