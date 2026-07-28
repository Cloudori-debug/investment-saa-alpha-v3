"""AI validation findings schema — classifies blocks/errors, does not grant buy permission."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FINDING_TYPES = frozenset({
    "NORMAL_BLOCK",
    "DATA_DEFECT_BLOCK",
    "OVER_CONSERVATIVE_BLOCK",
    "REPORT_CLARITY_ISSUE",
    "EXECUTION_MISMATCH",
    "MANUAL_REVIEW_REQUIRED",
})

SCHEMA_VERSION = "1.0"


def _finding(
    finding_type: str,
    severity: str,
    summary: str,
    *,
    detail: str = "",
    affected_scope: str = "all",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if finding_type not in FINDING_TYPES:
        raise ValueError(f"invalid finding_type: {finding_type}")
    return {
        "type": finding_type,
        "severity": severity,
        "summary": summary,
        "detail": detail,
        "affected_scope": affected_scope,
        "evidence": evidence or {},
        "grants_buy_permission": False,
    }


def build_validation_findings(
    *,
    run_id: str,
    as_of: str,
    fail_soft: dict[str, Any] | None,
    clarity: dict[str, Any] | None,
    cross_val: dict[str, Any] | None,
    actual_buy_allowed: int,
    execution_scope: str,
    dry_run_days: int,
    dry_run_required: int,
    core_etf_permission: str,
    alpha_auto_buy_permission: str,
) -> dict[str, Any]:
    """Rule-based classification — supplements human/AI cross-validation."""
    findings: list[dict[str, Any]] = []
    cov = (fail_soft or {}).get("sector_coverage") or {}
    shortlist_unknown = float(cov.get("shortlist_unknown_rate") or 0)

    if shortlist_unknown >= 1.0:
        findings.append(
            _finding(
                "DATA_DEFECT_BLOCK",
                "high",
                "Alpha shortlist sector 100% unknown — universe sector not populated",
                detail="Sector cap and alpha auto-buy cannot be trusted until universe.csv sector is filled.",
                affected_scope="alpha_auto_buy",
                evidence={"shortlist_unknown_rate": shortlist_unknown},
            )
        )
    elif shortlist_unknown > 0.30:
        findings.append(
            _finding(
                "DATA_DEFECT_BLOCK",
                "medium",
                f"Alpha shortlist sector unknown {shortlist_unknown:.0%} — auto-buy restricted",
                affected_scope="alpha_auto_buy",
                evidence=cov,
            )
        )

    if actual_buy_allowed == 0 and dry_run_days < dry_run_required:
        findings.append(
            _finding(
                "NORMAL_BLOCK",
                "info",
                f"Dry-run incomplete ({dry_run_days}/{dry_run_required}) — live buy blocked",
                affected_scope="execution",
            )
        )
    elif actual_buy_allowed == 0 and execution_scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW"}:
        findings.append(
            _finding(
                "NORMAL_BLOCK",
                "info",
                f"execution_scope={execution_scope} — kr_alpha new buy blocked by design",
                affected_scope="alpha_auto_buy",
            )
        )

    if (
        core_etf_permission in {"ALLOWED", "RESTRICTED"}
        and alpha_auto_buy_permission == "BLOCKED"
        and shortlist_unknown >= 1.0
        and actual_buy_allowed == 0
    ):
        findings.append(
            _finding(
                "OVER_CONSERVATIVE_BLOCK",
                "low",
                "Portfolio may appear fully blocked while Core ETF path is still RESTRICTED/ALLOWED",
                detail="Report should show Core ETF permission separately from Alpha auto-buy.",
                affected_scope="report",
                evidence={
                    "core_etf_permission": core_etf_permission,
                    "alpha_auto_buy_permission": alpha_auto_buy_permission,
                },
            )
        )

    if fail_soft and fail_soft.get("manual_review_required"):
        findings.append(
            _finding(
                "MANUAL_REVIEW_REQUIRED",
                "medium",
                "Alpha research allowed but auto-buy blocked — manual sector verification recommended",
                affected_scope="alpha_research",
            )
        )

    if clarity and not clarity.get("pass", True):
        for msg in clarity.get("failures") or []:
            findings.append(
                _finding(
                    "REPORT_CLARITY_ISSUE",
                    "medium",
                    msg,
                    affected_scope="report",
                )
            )

    if cross_val and not cross_val.get("pass", True):
        for issue in cross_val.get("issues") or cross_val.get("failures") or []:
            text = issue if isinstance(issue, str) else str(issue)
            findings.append(
                _finding(
                    "EXECUTION_MISMATCH",
                    "medium",
                    text,
                    affected_scope="execution",
                )
            )

    manual_required = any(f["type"] == "MANUAL_REVIEW_REQUIRED" for f in findings)
    data_defects = sum(1 for f in findings if f["type"] == "DATA_DEFECT_BLOCK")
    normal_blocks = sum(1 for f in findings if f["type"] == "NORMAL_BLOCK")

    return {
        "schema_version": SCHEMA_VERSION,
        "patch_version": "v1.0.3",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "run_id": run_id,
        "as_of": as_of,
        "ai_validation_status": "PENDING_HUMAN_REVIEW" if manual_required else "AUTO_CLASSIFIED",
        "manual_review_required": manual_required,
        "finding_count": len(findings),
        "summary": {
            "data_defect_blocks": data_defects,
            "normal_blocks": normal_blocks,
            "report_clarity_issues": sum(1 for f in findings if f["type"] == "REPORT_CLARITY_ISSUE"),
        },
        "findings": findings,
        "disclaimer": "Findings classify block reasons only — they do not grant buy permission.",
    }


def write_validation_findings(doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_validation_findings(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
