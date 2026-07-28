"""Target portfolio proposal vs user-confirmed — no auto-overwrite of target_portfolio.csv."""
from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any

from src.models import TargetRow


def _read_target_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_target_portfolio_proposal(
    targets: list[TargetRow] | None,
    output_dir: Path,
    *,
    source: str = "compass_pipeline",
) -> Path:
    """System-proposed targets — outputs/proposals only, never operational target."""
    from src.alpha.target_write_audit import proposal_output_dir

    out_dir = proposal_output_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "target_portfolio_proposal.csv"
    rows = targets or []
    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight", "proposal_source",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in rows:
            writer.writerow({
                "ticker": t.ticker,
                "name": t.name,
                "asset_group": t.asset_group,
                "sector": t.sector,
                "role": t.role,
                "target_weight": t.target_weight,
                "min_weight": t.min_weight,
                "max_weight": t.max_weight,
                "proposal_source": source,
            })
    return out


def ensure_user_target_snapshot(data_dir: Path, output_dir: Path) -> Path:
    """Snapshot user-confirmed target — never overwrites data/user_target_portfolio.csv."""
    from src.alpha.target_portfolio_guard import bootstrap_user_target_if_missing, user_target_portfolio_path

    bootstrap_user_target_if_missing(data_dir)
    user_path = user_target_portfolio_path(data_dir)
    dst = output_dir / "user_target_portfolio.csv"
    if user_path.exists():
        shutil.copy2(user_path, dst)
    return dst


def ensure_user_target_in_data_dir(data_dir: Path) -> Path | None:
    from src.alpha.target_portfolio_guard import bootstrap_user_target_if_missing, user_target_portfolio_path

    return bootstrap_user_target_if_missing(data_dir) or (
        user_target_portfolio_path(data_dir) if user_target_portfolio_path(data_dir).exists() else None
    )


def write_target_diff_review(
    data_dir: Path,
    output_dir: Path,
    *,
    proposal_path: Path | None = None,
) -> dict[str, Any]:
    """Compare system proposal vs user-confirmed target."""
    from src.alpha.target_portfolio_guard import bootstrap_user_target_if_missing, user_target_portfolio_path

    proposal_path = proposal_path or (output_dir / "proposals" / "target_portfolio_proposal.csv")
    if not proposal_path.exists():
        proposal_path = output_dir / "target_portfolio_proposal.csv"
    user_path = user_target_portfolio_path(data_dir)
    if not user_path.exists():
        bootstrap_user_target_if_missing(data_dir)

    proposal = {r["ticker"]: r for r in _read_target_csv(proposal_path)}
    user = {r["ticker"]: r for r in _read_target_csv(
        user_path if user_path.exists() else data_dir / "target_portfolio.csv"
    )}

    diffs: list[dict[str, Any]] = []
    all_tickers = sorted(set(proposal) | set(user))
    for tk in all_tickers:
        p = proposal.get(tk)
        u = user.get(tk)
        pw = float((p or {}).get("target_weight") or 0)
        uw = float((u or {}).get("target_weight") or 0)
        if abs(pw - uw) < 0.01 and p and u:
            continue
        diffs.append({
            "ticker": tk,
            "name": (u or p or {}).get("name", ""),
            "user_weight_pct": uw,
            "proposal_weight_pct": pw,
            "delta_pct": round(pw - uw, 2),
            "status": (
                "proposal_only" if u is None else
                "user_only" if p is None else
                "weight_diff"
            ),
        })

    out_path = output_dir / "target_diff_review.csv"
    fieldnames = ["ticker", "name", "user_weight_pct", "proposal_weight_pct", "delta_pct", "status"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diffs)

    return {
        "proposal_rows": len(proposal),
        "user_rows": len(user),
        "diff_count": len(diffs),
        "path": str(out_path),
    }
