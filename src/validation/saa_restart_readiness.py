"""SAA Restart Readiness Report — conditions to resume SAA, not buy authorization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml

from src.report.execution_metrics import list_risk_reduce_candidates
from src.report.io_utils import read_output_json
from src.validation.green_layers import evaluate_green_layers

Verdict = Literal["READY", "WATCH", "NOT_READY"]

SAA_GAP_GROUPS = (
    "global_beta",
    "hedge_alt",
    "income_alt",
    "duration_bond",
    "cash_short_bond",
    "fx_dollar",
)

PRIORITY_A = frozenset({"cash_short_bond", "duration_bond", "hedge_alt"})
PRIORITY_B = frozenset({"global_beta", "income_alt"})
PRIORITY_C = frozenset({"fx_dollar", "domestic_beta", "kr_alpha"})

PROHIBITIONS = [
    "Actual Buy Allowed=0이면 어떤 watch signal도 매수 허가로 변환하지 않는다.",
    "KOSPI pullback watch는 buy permission이 아니다.",
    "ETF_ONLY는 ETF 매수 허가가 아니다.",
    "kr_alpha hard stop 초과 상태에서는 신규 알파 매수 금지.",
    "SAA 재개 판단은 target write를 변경하지 않는다.",
]

RESTART_LEVELS = {
    0: {
        "label": "현재 — 신규매수 금지",
        "summary": "신규매수 금지 · risk-reduce only · SAA 재개 불가",
    },
    1: {
        "label": "관찰 단계",
        "summary": (
            "Technical GREEN 유지 · market_blockers 감소 · USD/KRW watch 해소 또는 안정화 · "
            "policy_cap 완화 후보 발생 · Actual Buy Allowed는 여전히 0일 수 있음"
        ),
    },
    2: {
        "label": "소액 재개 후보",
        "summary": (
            "Operational YELLOW+ · Market YELLOW but improving · Actual Buy Allowed > 0 · "
            "신규매수는 Core SAA ETF에 한정 · kr_alpha 신규매수 금지 유지"
        ),
    },
    3: {
        "label": "정상 재개",
        "summary": (
            "Operational GREEN · Market GREEN · Full GREEN 또는 Full YELLOW+ · "
            "policy_cap 비활성 또는 완화 · data_gate GREEN · Actual Buy Allowed > 0"
        ),
    },
}


def _load_asset_labels(data_dir: Path) -> dict[str, str]:
    path = data_dir / "asset_group_labels.yaml"
    if not path.exists():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: v.get("label", k) for k, v in (doc.get("groups") or {}).items()}


def _group_gap_map(final_doc: dict[str, Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in final_doc.get("group_gaps") or []:
        if not isinstance(row, dict):
            continue
        g = str(row.get("asset_group") or "")
        if not g:
            continue
        try:
            out[g] = {
                "target": float(row.get("target") or 0),
                "current": float(row.get("current") or 0),
                "gap": float(row.get("gap") or 0),
                "action": str(row.get("action") or ""),
                "reason": str(row.get("reason") or ""),
            }
        except (TypeError, ValueError):
            continue
    return out


def _duration_bond_row(
    data_dir: Path,
    output_dir: Path,
    brief: dict[str, Any] | None,
) -> dict[str, Any]:
    sleeve = (brief or {}).get("duration_sleeve") or {}
    kr = float(sleeve.get("kr_duration_pct") or 0)
    gl = float(sleeve.get("global_duration_pct") or 0)
    current = round(kr + gl, 2)

    cfg_path = data_dir / "duration_sleeve_tags.yaml"
    target = 20.0
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        shadows = cfg.get("shadow_targets_pct") or {}
        target = round(
            float((shadows.get("kr_duration_bond") or {}).get("target", 12.5))
            + float((shadows.get("global_duration_bond") or {}).get("target", 7.5)),
            2,
        )

    ref = read_output_json(output_dir / "core_saa_reference_diagnostic.json") or {}
    ref_tgt = (ref.get("sleeve_target_pct") or {}).get("duration_bond")
    if ref_tgt is not None:
        target = round(float(ref_tgt), 2)

    gap = round(target - current, 2)
    return {
        "asset_group": "duration_bond",
        "label": "듀레이션 채권 (국채·글로벌)",
        "target_weight_pct": target,
        "current_weight_pct": current,
        "gap_pct": gap,
        "kr_duration_pct": kr,
        "global_duration_pct": gl,
        "diagnosis": sleeve.get("diagnosis", ""),
        "action_hint": "Buy" if gap >= 1.0 else ("Park" if gap <= -1.0 else "Hold"),
    }


def _priority_for_group(group: str) -> str:
    if group in PRIORITY_A:
        return "A"
    if group in PRIORITY_B:
        return "B"
    return "C"


def _blocker_for_group(
    group: str,
    *,
    gap: float,
    green: dict[str, Any],
    market_blockers: list[str],
    actual_buy: int,
) -> str:
    parts: list[str] = []
    if actual_buy <= 0:
        parts.append("Actual Buy Allowed=0")
    if green.get("operational_status") != "GREEN":
        parts.append(f"Operational={green.get('operational_status')}")
    if green.get("market_status") != "GREEN":
        parts.append(f"Market={green.get('market_status')}")
    if any("policy_cap" in b for b in market_blockers):
        parts.append("policy_cap active")
    if group == "global_beta" and any("usdkrw" in b for b in market_blockers):
        parts.append("USD/KRW watch")
    if group in {"global_beta", "income_alt", "fx_dollar", "duration_bond"}:
        if any("kr_alpha" in b for b in market_blockers):
            parts.append("kr_alpha hard stop — risk budget pressure")
    if group != "cash_short_bond" and gap <= 0:
        parts.append("no underweight gap")
    if any("kospi_pullback" in b or "kospi_drawdown" in b for b in market_blockers):
        parts.append("KOSPI pullback watch (not buy permission)")
    return "; ".join(parts) if parts else "gate clear pending review"


def _restart_condition_for_group(
    group: str,
    *,
    gap: float,
    green: dict[str, Any],
    actual_buy: int,
) -> str:
    if actual_buy <= 0:
        return "Actual Buy Allowed > 0 필요"
    if green.get("market_status") != "GREEN":
        return "Market GREEN + policy_cap inactive"
    if green.get("operational_status") != "GREEN":
        return "Operational GREEN"
    if group in {"global_beta", "income_alt", "fx_dollar"} and any(
        "usdkrw" in b for b in green.get("market_blockers") or []
    ):
        return "USD/KRW watch 해소"
    if gap < 1.0:
        return "목표 대비 underweight gap >= 1%p"
    if group == "duration_bond":
        return "Level 2+ · Core SAA ETF only · duration sleeve underweight"
    if group in PRIORITY_A:
        return "Level 2+ · Core SAA ETF 우선 재개"
    return "Level 3 · 정상 재개 조건 충족"


def _collect_mandatory_blockers(green: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if green.get("actual_buy_allowed", 0) <= 0:
        blockers.append("Actual Buy Allowed=0")
    op = green.get("operational_status")
    if op == "YELLOW":
        blockers.append("Operational YELLOW")
    elif op == "RED":
        blockers.append("Operational RED")
    mkt = green.get("market_status")
    if mkt == "YELLOW":
        blockers.append("Market YELLOW")
    elif mkt == "RED":
        blockers.append("Market RED")
    for b in green.get("market_blockers") or []:
        if "policy_cap" in b and b not in blockers:
            blockers.append(b)
        if "usdkrw" in b and not any("USD/KRW" in x for x in blockers):
            blockers.append(f"USD/KRW watch ({b})")
        if "kospi" in b and "pullback" in b and not any("KOSPI" in x for x in blockers):
            blockers.append("KOSPI drawdown / pullback watch active")
        if "kr_alpha_over_hard_stop" in b:
            blockers.append(f"kr_alpha hard stop ({b}) — 전체 risk budget 압박")
    return list(dict.fromkeys(blockers))


def _determine_restart_level(green: dict[str, Any]) -> int:
    actual_buy = int(green.get("actual_buy_allowed") or 0)
    tech = green.get("technical_status")
    op = green.get("operational_status")
    mkt = green.get("market_status")
    policy_active = any("policy_cap" in b for b in green.get("market_blockers") or [])

    if tech != "GREEN":
        return 0
    if actual_buy <= 0 or op == "RED" or mkt == "RED":
        return 0
    if op == "GREEN" and mkt == "GREEN" and actual_buy > 0 and not policy_active:
        return 3
    if actual_buy > 0 and op in {"GREEN", "YELLOW"} and mkt in {"GREEN", "YELLOW"}:
        return 2
    return 1


def _verdict_from_level(level: int, green: dict[str, Any]) -> Verdict:
    actual_buy = int(green.get("actual_buy_allowed") or 0)
    if level >= 2 and actual_buy > 0:
        return "READY"
    if level == 1:
        return "WATCH"
    return "NOT_READY"


def _first_eligible_asset_class(
    gap_rows: list[dict[str, Any]],
    *,
    actual_buy: int,
    green: dict[str, Any],
) -> str:
    if actual_buy <= 0:
        return "none — Actual Buy Allowed=0"
    if green.get("market_status") != "GREEN":
        return "none — Market not GREEN"
    under = [r for r in gap_rows if float(r.get("gap_pct") or 0) >= 1.0]
    under.sort(key=lambda r: (_priority_for_group(r["asset_group"]), -float(r["gap_pct"])))
    if under:
        top = under[0]
        return (
            f"{top['asset_group']} ({top.get('label', top['asset_group'])}) — "
            f"priority {_priority_for_group(top['asset_group'])}"
        )
    return "none — no material underweight gap"


def build_saa_restart_readiness_report(
    data_dir: Path,
    output_dir: Path,
    *,
    green: dict[str, Any] | None = None,
    final_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build SAA restart readiness analysis — does not change targets or buy logic."""
    final_doc = final_doc or read_output_json(output_dir / "final_execution_decision.json") or {}
    green = green or evaluate_green_layers(data_dir, output_dir, final_doc=final_doc)
    brief = read_output_json(output_dir / "daily_brief.json") or {}
    labels = _load_asset_labels(data_dir)
    gaps = _group_gap_map(final_doc)
    market_blockers = list(green.get("market_blockers") or [])
    actual_buy = int(green.get("actual_buy_allowed") or 0)

    gap_summary: list[dict[str, Any]] = []
    for group in SAA_GAP_GROUPS:
        if group == "duration_bond":
            row = _duration_bond_row(data_dir, output_dir, brief)
            gap = float(row["gap_pct"])
            label = row["label"]
            target = row["target_weight_pct"]
            current = row["current_weight_pct"]
            extra = {k: v for k, v in row.items() if k not in {
                "asset_group", "label", "target_weight_pct", "current_weight_pct", "gap_pct",
            }}
        else:
            g = gaps.get(group, {})
            target = g.get("target", 0.0)
            current = g.get("current", 0.0)
            gap = g.get("gap", 0.0)
            label = labels.get(group, group)
            extra = {}

        gap_summary.append({
            "asset_group": group,
            "label": label,
            "target_weight_pct": target,
            "current_weight_pct": current,
            "gap_pct": gap,
            "priority": _priority_for_group(group),
            "blocker": _blocker_for_group(
                group,
                gap=gap,
                green=green,
                market_blockers=market_blockers,
                actual_buy=actual_buy,
            ),
            "restart_condition": _restart_condition_for_group(
                group,
                gap=gap,
                green=green,
                actual_buy=actual_buy,
            ),
            **extra,
        })

    level = _determine_restart_level(green)
    verdict = _verdict_from_level(level, green)

    mandatory_blockers = _collect_mandatory_blockers(green)
    risk_trims = list_risk_reduce_candidates(final_doc)
    human_required = bool(risk_trims) or bool(
        (final_doc.get("execution_permissions") or {}).get("manual_review_required")
    )

    if actual_buy <= 0:
        next_action = "risk-reduce only — no new SAA buys"
    elif level >= 2:
        next_action = "Core SAA ETF small-lot restart candidate — human review required"
    else:
        next_action = "observe — blockers clearing"

    blockers_to_clear = mandatory_blockers

    return {
        "schema_version": "saa_restart_readiness.v1",
        "as_of": final_doc.get("as_of") or brief.get("as_of", ""),
        "run_id": final_doc.get("run_id", ""),
        "purpose": "SAA 재개 조건 분석 — 매수 허가·target write 변경 아님",
        "verdict": verdict,
        "saa_restart_readiness": verdict,
        "restart_level": level,
        "restart_level_label": RESTART_LEVELS[level]["label"],
        "current_status": {
            "technical_status": green.get("technical_status"),
            "operational_status": green.get("operational_status"),
            "market_status": green.get("market_status"),
            "full_status": green.get("full_status"),
            "actual_buy_allowed": actual_buy,
            "buy_permission_status": green.get("buy_permission_status"),
            "execution_scope": green.get("execution_scope"),
            "risk_reduce_only": green.get("risk_reduce_only"),
            "saa_restart_readiness_gate": green.get("saa_restart_readiness"),
            "kr_alpha_restart_readiness": green.get("kr_alpha_restart_readiness"),
        },
        "saa_gap_summary": gap_summary,
        "restart_blockers": mandatory_blockers,
        "restart_conditions_by_level": RESTART_LEVELS,
        "priority_classification": {
            "A": [r["asset_group"] for r in gap_summary if r["priority"] == "A"],
            "B": [r["asset_group"] for r in gap_summary if r["priority"] == "B"],
            "C": list(PRIORITY_C),
        },
        "prohibitions": PROHIBITIONS,
        "next_allowed_action": next_action,
        "blockers_to_clear": blockers_to_clear,
        "first_eligible_asset_class_if_buy_allowed": _first_eligible_asset_class(
            gap_summary,
            actual_buy=actual_buy,
            green=green,
        ),
        "risk_reduce_candidates": [
            {
                "ticker": t.get("ticker"),
                "name": t.get("name"),
                "action": t.get("action"),
                "allowed_size_pct": t.get("allowed_size_pct"),
                "reason": t.get("reason") or t.get("trim_reason"),
            }
            for t in risk_trims
        ],
        "human_approval_required": human_required,
        "market_blockers": market_blockers,
        "market_unknowns": green.get("market_unknowns", []),
        "operational_blockers": green.get("operational_blockers", []),
    }


def format_saa_restart_readiness_md(report: dict[str, Any]) -> str:
    """Markdown section for daily_report."""
    cs = report.get("current_status") or {}
    lines = [
        "",
        "## SAA Restart Readiness Report",
        "",
        f"- **SAA Restart Readiness**: **{report.get('verdict', 'NOT_READY')}**",
        f"- **Restart Level**: {report.get('restart_level', 0)} — {report.get('restart_level_label', '')}",
        f"- **Next allowed action**: {report.get('next_allowed_action', '—')}",
        f"- **Human approval required**: **{'yes' if report.get('human_approval_required') else 'no'}**",
        "",
        "### Current status",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Technical | **{cs.get('technical_status', '—')}** |",
        f"| Operational | **{cs.get('operational_status', '—')}** |",
        f"| Market | **{cs.get('market_status', '—')}** |",
        f"| Full | **{cs.get('full_status', '—')}** |",
        f"| Actual Buy Allowed | {cs.get('actual_buy_allowed', 0)} |",
        f"| buy_permission_status | {cs.get('buy_permission_status', 'BLOCKED')} |",
        f"| execution_scope | `{cs.get('execution_scope', '—')}` |",
        f"| risk_reduce_only | {cs.get('risk_reduce_only', False)} |",
        f"| saa_restart_readiness (gate) | {cs.get('saa_restart_readiness_gate', 'NOT_READY')} |",
        f"| kr_alpha_restart_readiness | {cs.get('kr_alpha_restart_readiness', 'NOT_READY')} |",
        "",
        "### SAA gap summary",
        "",
        "| Asset group | Target % | Current % | Gap % | Priority | Blocker | Restart condition |",
        "|-------------|----------|-----------|-------|----------|---------|-------------------|",
    ]
    for row in report.get("saa_gap_summary") or []:
        lines.append(
            f"| {row.get('label', row.get('asset_group'))} | "
            f"{row.get('target_weight_pct', 0):.2f} | "
            f"{row.get('current_weight_pct', 0):.2f} | "
            f"{row.get('gap_pct', 0):+.2f} | "
            f"{row.get('priority', '—')} | "
            f"{row.get('blocker', '—')} | "
            f"{row.get('restart_condition', '—')} |"
        )

    lines.extend(["", "### SAA restart blockers", ""])
    for b in report.get("restart_blockers") or []:
        lines.append(f"- {b}")

    duration_doc = report.get("core_etf_blocking_duration")
    if isinstance(duration_doc, dict):
        from src.validation.core_etf_blocking_duration import format_core_etf_blocking_duration_line

        lines.extend([
            "",
            "### Core ETF 미집행 진단 (P5-A)",
            "",
            format_core_etf_blocking_duration_line(duration_doc),
            "",
        ])

    lines.extend(["", "### Blockers to clear", ""])
    for b in report.get("blockers_to_clear") or []:
        lines.append(f"- {b}")

    lines.extend(["", "### Restart conditions (levels)", ""])
    for lvl, meta in sorted((report.get("restart_conditions_by_level") or RESTART_LEVELS).items()):
        lines.append(f"- **Level {lvl}** — {meta.get('label', '')}: {meta.get('summary', '')}")

    pc = report.get("priority_classification") or {}
    lines.extend([
        "",
        "### Priority classification (if Buy Allowed > 0)",
        "",
        f"- **A (first)**: {', '.join(pc.get('A', []))}",
        f"- **B**: {', '.join(pc.get('B', []))}",
        f"- **C (last)**: {', '.join(pc.get('C', []))}",
        "",
        f"- **First eligible asset class if Buy Allowed > 0**: "
        f"{report.get('first_eligible_asset_class_if_buy_allowed', 'none')}",
        "",
        "### Risk-reduce candidates",
        "",
    ])
    trims = report.get("risk_reduce_candidates") or []
    if trims:
        for t in trims:
            lines.append(
                f"- `{t.get('ticker')}` {t.get('name', '')} — {t.get('action')} "
                f"{t.get('allowed_size_pct')}%p ({t.get('reason', '')})"
            )
    else:
        lines.append("- none")

    lines.extend(["", "### Prohibitions", ""])
    for p in report.get("prohibitions") or PROHIBITIONS:
        lines.append(f"> {p}")
    lines.append("")
    return "\n".join(lines)


def write_saa_restart_readiness_report(
    data_dir: Path,
    output_dir: Path,
    *,
    green: dict[str, Any] | None = None,
    final_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write JSON + MD artifacts and return report dict."""
    report = build_saa_restart_readiness_report(
        data_dir,
        output_dir,
        green=green,
        final_doc=final_doc,
    )
    try:
        from src.validation.core_etf_blocking_duration import write_core_etf_blocking_duration

        report["core_etf_blocking_duration"] = write_core_etf_blocking_duration(
            output_dir,
            as_of=str(report.get("as_of") or (final_doc or {}).get("as_of") or ""),
        )
    except Exception:
        pass
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "saa_restart_readiness_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "saa_restart_readiness_report.md").write_text(
        format_saa_restart_readiness_md(report),
        encoding="utf-8",
    )
    return report


def stamp_saa_restart_onto_docs(docs: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    """Merge summary fields into acceptance / final / bundle."""
    summary_keys = (
        "verdict",
        "saa_restart_readiness",
        "restart_level",
        "restart_level_label",
        "next_allowed_action",
        "blockers_to_clear",
        "first_eligible_asset_class_if_buy_allowed",
        "human_approval_required",
        "restart_blockers",
        "saa_gap_summary",
        "priority_classification",
        "prohibitions",
        "risk_reduce_candidates",
    )
    compact = {k: report[k] for k in summary_keys if k in report}
    compact["current_status"] = report.get("current_status")

    for key in ("acceptance", "final", "bundle"):
        doc = docs.get(key)
        if doc is None:
            continue
        doc["saa_restart_readiness_report"] = compact
        doc["saa_restart_readiness_verdict"] = report.get("verdict")
