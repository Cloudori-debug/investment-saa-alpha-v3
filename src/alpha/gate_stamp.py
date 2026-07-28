from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

AlphaExecutionStatus = Literal["BLOCKED", "RESEARCH_ONLY", "RISK_REDUCE_ONLY", "EXECUTABLE"]


def build_alpha_execution_status(
    *,
    data_gate: str,
    alpha_data_gate: str | None,
    execution_scope: str,
    alpha_trade_permission: str,
    alpha_position_action: str,
) -> dict[str, Any]:
    if execution_scope == "NO_TRADE" or data_gate == "RED":
        status: AlphaExecutionStatus = "BLOCKED"
        usage = "research_only"
    elif alpha_position_action == "RISK_REDUCE_ONLY":
        status = "RISK_REDUCE_ONLY"
        usage = "risk_reduce_trim_only"
    elif (
        alpha_position_action == "REVIEW_ONLY"
        or execution_scope != "FULL_WITH_ALPHA"
        or alpha_trade_permission != "ALLOW_NEW"
    ):
        status = "RESEARCH_ONLY"
        usage = "research_only"
    else:
        status = "EXECUTABLE"
        usage = "human_approval_required"

    return {
        "schema_version": "1.0",
        "alpha_execution_status": status,
        "usage": usage,
        "reason": (
            f"data_gate={data_gate}, alpha_gate={alpha_data_gate or '—'}, "
            f"execution_scope={execution_scope}, "
            f"alpha_trade_permission={alpha_trade_permission}, "
            f"alpha_position_action={alpha_position_action}"
        ),
        "banner": (
            "ALPHA_EXECUTION_STATUS: "
            f"{status} | USAGE: {usage} | "
            f"REASON: alpha_gate={alpha_data_gate or '—'}, execution_scope={execution_scope}"
        ),
    }


def write_alpha_gate_stamp(output_dir: Path, status: dict[str, Any]) -> Path:
    path = output_dir / "alpha_execution_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = output_dir / "alpha_report.md"
    if report.exists():
        banner = f"> **{status['banner']}**\n\n"
        existing = report.read_text(encoding="utf-8")
        if status["banner"] not in existing:
            report.write_text(banner + existing, encoding="utf-8")
    return path
