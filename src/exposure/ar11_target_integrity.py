"""Phase AR-1.1 — domestic_beta orphan fix and target sum integrity."""
from __future__ import annotations

from typing import Any

from src.compass.models import GroupAllocation, PortfolioAllocation
from src.compass.profile_aliases import resolve_profile_name
from src.models import TargetRow

CORE_REDISTRIBUTE_GROUPS = frozenset({
    "global_beta",
    "income_alt",
    "hedge_alt",
    "cash_short_bond",
})


def get_locked_tilt_groups(profiles: dict[str, Any], profile_name: str | None) -> frozenset[str]:
    name = resolve_profile_name(profiles, profile_name)
    profile = (profiles.get("profiles") or {}).get(name) or {}
    locked = profile.get("locked_tilt_groups") or []
    return frozenset(str(g) for g in locked)


def zero_tilts_for_locked_groups(
    tilts: dict[str, float],
    locked: frozenset[str],
) -> dict[str, float]:
    if not locked:
        return tilts
    return {k: (0.0 if k in locked else v) for k, v in tilts.items()}


def redistribute_orphan_group_targets(
    allocation: PortfolioAllocation,
    template: list[TargetRow],
    *,
    redistribute_groups: frozenset[str] = CORE_REDISTRIBUTE_GROUPS,
) -> tuple[PortfolioAllocation, float, list[str]]:
    """Move final_target from groups with no template rows into Core redistribute sleeves."""
    template_groups = {r.asset_group for r in template}
    orphan_total = round(
        sum(g.final_target for g in allocation.groups if g.asset_group not in template_groups),
        2,
    )
    notes: list[str] = []
    if orphan_total <= 0:
        return allocation, 0.0, notes

    orphan_names = [
        g.asset_group for g in allocation.groups
        if g.asset_group not in template_groups and g.final_target > 0
    ]
    notes.append(
        f"orphan groups {orphan_names}: {orphan_total:.2f}%p → proportional redistribute to "
        f"{sorted(redistribute_groups)}"
    )

    recipients = [
        g for g in allocation.groups
        if g.asset_group in redistribute_groups and g.asset_group in template_groups
    ]
    recv_sum = sum(g.final_target for g in recipients)
    if recv_sum <= 0:
        return allocation, orphan_total, notes + ["redistribute skipped: no recipient weight"]

    updated_groups: list[GroupAllocation] = []
    for g in allocation.groups:
        if g.asset_group not in template_groups:
            updated_groups.append(g.model_copy(update={"final_target": 0.0, "raw_target": 0.0}))
            continue
        if g.asset_group in redistribute_groups:
            share = g.final_target / recv_sum
            updated_groups.append(
                g.model_copy(update={
                    "final_target": round(g.final_target + orphan_total * share, 2),
                })
            )
        else:
            updated_groups.append(g)

    total = round(sum(g.final_target for g in updated_groups), 2)
    drift = round(100.0 - total, 2)
    if drift != 0:
        idx = max(
            range(len(updated_groups)),
            key=lambda i: updated_groups[i].final_target
            if updated_groups[i].asset_group in redistribute_groups
            else -1,
        )
        g = updated_groups[idx]
        updated_groups[idx] = g.model_copy(update={"final_target": round(g.final_target + drift, 2)})

    new_alloc = allocation.model_copy(update={
        "groups": updated_groups,
        "total_weight": round(sum(g.final_target for g in updated_groups), 2),
        "notes": list(allocation.notes) + notes,
    })
    return new_alloc, orphan_total, notes


def ensure_decomposed_sum_100(rows: list[TargetRow]) -> list[TargetRow]:
    """Fix rounding drift on decomposed security targets."""
    if not rows:
        return rows
    total = round(sum(r.target_weight for r in rows), 2)
    drift = round(100.0 - total, 2)
    if drift == 0:
        return rows
    idx = max(range(len(rows)), key=lambda i: rows[i].target_weight)
    row = rows[idx]
    rows[idx] = row.model_copy(update={"target_weight": round(row.target_weight + drift, 2)})
    return rows


def compute_target_integrity(
    *,
    security_targets: list[TargetRow] | None,
    allocation: PortfolioAllocation | None,
    template: list[TargetRow] | None,
) -> dict[str, Any]:
    sec_sum = round(sum(r.target_weight for r in (security_targets or [])), 2)
    group_sum = round(sum(g.final_target for g in (allocation.groups if allocation else [])), 2)
    if allocation is None and security_targets:
        group_sum = sec_sum
    template_groups = {r.asset_group for r in (template or [])}
    orphan = round(
        sum(
            g.final_target for g in (allocation.groups if allocation else [])
            if g.asset_group not in template_groups
        ),
        2,
    )
    domestic = next(
        (g.final_target for g in (allocation.groups if allocation else []) if g.asset_group == "domestic_beta"),
        0.0,
    )
    by_group_sec: dict[str, float] = {}
    for row in security_targets or []:
        by_group_sec[row.asset_group] = round(by_group_sec.get(row.asset_group, 0) + row.target_weight, 2)
    group_mismatch = round(group_sum - sec_sum, 2) if allocation and security_targets else 0.0

    return {
        "security_target_sum_pct": sec_sum,
        "asset_group_target_sum_pct": group_sum,
        "unallocated_target_pct": orphan,
        "domestic_beta_final_pct": round(float(domestic), 2),
        "asset_group_vs_security_gap_pct": group_mismatch,
        "security_targets_by_group": by_group_sec,
    }
