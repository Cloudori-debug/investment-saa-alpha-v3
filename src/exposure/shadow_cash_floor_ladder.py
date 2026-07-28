from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.report.io_utils import read_output_json

SHADOW_LADDER_DISCLAIMER = (
    "Shadow reference only — not execution rules. Does not alter target_portfolio, "
    "trade_actions, execution_scope, or trigger_rules.yaml."
)


def _data_dir_for(output_dir: Path, data_dir: Path | None) -> Path:
    if data_dir is not None:
        return data_dir
    candidate = output_dir.parent / "data"
    return candidate if candidate.is_dir() else Path("data")


def load_shadow_cash_floor_ladder(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "shadow_cash_floor_ladder.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _current_cash_short_bond_pct(output_dir: Path) -> float | None:
    exposure = read_output_json(output_dir / "exposure_lookthrough.json")
    if exposure:
        current = (exposure.get("group_weights") or {}).get("current") or {}
        val = current.get("cash_short_bond")
        if val is not None:
            return round(float(val), 2)
    shadow = read_output_json(output_dir / "shadow_diagnostic.json")
    if shadow:
        duration = shadow.get("duration_bond_status") or {}
        val = duration.get("v1_0_2_cash_short_bond_current_pct")
        if val is not None:
            return round(float(val), 2)
    final = read_output_json(output_dir / "final_execution_decision.json")
    if final:
        for g in ((final.get("operating") or {}).get("group_gaps") or []):
            if isinstance(g, dict) and g.get("asset_group") == "cash_short_bond":
                cur = g.get("current")
                if cur is not None:
                    return round(float(cur), 2)
    return None


def _gate_and_dry_run(output_dir: Path) -> tuple[str, int, int]:
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    data_gate = str(final.get("data_gate") or final.get("system_status") or "—")
    dry_run = int(final.get("dry_run_days") or 0)
    required = 10
    health = read_output_json(output_dir / "system_health.json")
    if health:
        for chk in health.get("checks") or []:
            if isinstance(chk, dict) and chk.get("name") == "dry_run":
                required = int(chk.get("required") or required)
                break
    return data_gate, dry_run, required


def _buy_trigger_active(output_dir: Path) -> bool:
    shadow = read_output_json(output_dir / "shadow_diagnostic.json") or {}
    signals = shadow.get("signals") or {}
    if signals.get("buy_trigger_active"):
        return True
    reviews = read_output_json(output_dir / "trigger_reviews.json") or {}
    for item in reviews.get("alerts") or reviews.get("triggers") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("id") or "")
        status = str(item.get("status") or "").lower()
        if "kospi_pullback" in key and status in ("active", "watch"):
            return True
    return False


def build_shadow_cash_floor_ladder_status(
    output_dir: Path,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Compute shadow ladder snapshot from reference yaml + current outputs."""
    data = _data_dir_for(output_dir, data_dir)
    ref = load_shadow_cash_floor_ladder(data)
    floor = float((ref.get("cash_floor_policy") or {}).get("floor_pct") or 55.0)
    buy1 = (ref.get("buy_ladder") or {}).get("buy_1") or {}
    max_from_cash = float(buy1.get("max_from_cash_pct") or 2.5)

    current = _current_cash_short_bond_pct(output_dir)
    deployable = round(max(0.0, (current or 0.0) - floor), 2) if current is not None else None
    buy1_capacity = None
    if deployable is not None:
        buy1_capacity = round(min(deployable, max_from_cash), 2)

    data_gate, dry_run_days, dry_run_required = _gate_and_dry_run(output_dir)
    buy1_ready = (
        data_gate == "GREEN"
        and dry_run_days >= dry_run_required
        and _buy_trigger_active(output_dir)
    )

    abs_mode = bool(ref.get("absolute_return_mode"))
    buy1_label = "Core benchmark ETF" if abs_mode else "KODEX200"
    floor_note = (
        "Buy_2+ funds Core underweights via kr_alpha trim or new cash."
        if abs_mode
        else "Buy_2+ requires kr_alpha trim, new cash, or explicit floor change to 50%."
    )

    summary_line = (
        f"Cash Floor Ladder (shadow): cash_short_bond {current if current is not None else '—'}%, "
        f"floor {floor:.1f}%, cash deployable {deployable if deployable is not None else '—'}%p. "
        f"Buy_1 capacity: {buy1_label} up to {buy1_capacity if buy1_capacity is not None else '—'}%p "
        f"after GREEN + dry-run {dry_run_required}/{dry_run_required}. "
        f"{floor_note}"
    )

    return {
        "mode": "shadow_reference_only",
        "execution_authority": "none",
        "disclaimer": SHADOW_LADDER_DISCLAIMER,
        "reference_file": "data/shadow_cash_floor_ladder.yaml",
        "current_cash_short_bond_pct": current,
        "floor_pct": floor,
        "deployable_from_cash_pct": deployable,
        "buy_1_max_from_cash_pct": buy1_capacity,
        "buy_1_ready": buy1_ready,
        "data_gate": data_gate,
        "dry_run_days": dry_run_days,
        "dry_run_required": dry_run_required,
        "kospi_pullback_signal": _buy_trigger_active(output_dir),
        "buy_2_plus_funding": ["kr_alpha_trim", "new_cash", "explicit_floor_policy_change_to_50"],
        "summary_line": summary_line,
        "constraints": ref.get("constraints") or {},
    }


def write_shadow_cash_floor_ladder_status(
    output_dir: Path,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    status = build_shadow_cash_floor_ladder_status(output_dir, data_dir=data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shadow_cash_floor_ladder_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return status
