"""Final execution authority metrics for reports — single source: final_execution_decision.json."""
from __future__ import annotations

from typing import Any

_BUY_ACTIONS = frozenset({"Buy", "Buy-allowed", "Add", "BuyCandidate"})
_RISK_REDUCE_ACTIONS = frozenset({"Trim", "Reduce", "Risk-reduce"})


def count_executable_actions(final: dict[str, Any] | None) -> dict[str, Any]:
    """Derive buy vs risk-reduce counts from final_execution_decision only."""
    if not final:
        return {
            "actual_buy_allowed_count": 0,
            "executable_buy_count": 0,
            "risk_reduce_trim_count": 0,
            "allowed_risk_reduce_action_count": 0,
            "executable_action_count": 0,
            "risk_reduce_trims": [],
        }
    allowed = final.get("allowed_actions") or []
    final_trades = final.get("final_trade_list") or []
    perms = final.get("execution_permissions") or {}

    actual_buys = [
        r for r in final_trades
        if r.get("action") in _BUY_ACTIONS
        and float(r.get("allowed_size_pct") or 0) > 0
    ]
    risk_trims = [
        r for r in allowed
        if r.get("action") in _RISK_REDUCE_ACTIONS
        and float(r.get("allowed_size_pct") or 0) != 0
    ]
    buy_count = len(actual_buys)
    trim_count = len(risk_trims)
    return {
        "actual_buy_allowed_count": buy_count,
        "executable_buy_count": buy_count,
        "risk_reduce_trim_count": trim_count,
        "allowed_risk_reduce_action_count": trim_count,
        "executable_action_count": buy_count,
        "risk_reduce_trims": risk_trims,
        "alpha_new_buy": perms.get("alpha_auto_buy_permission") or perms.get("kr_alpha_new_buy", "BLOCKED"),
        "alpha_replace": perms.get("kr_alpha_replace", "BLOCKED"),
    }


def list_buy_candidates(final: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Buy / add actions only — never Trim or Reduce."""
    if not final:
        return []
    buys: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in final.get("final_trade_list") or []:
        if row.get("action") not in _BUY_ACTIONS:
            continue
        if float(row.get("allowed_size_pct") or 0) <= 0:
            continue
        tk = str(row.get("ticker", ""))
        if tk in seen:
            continue
        seen.add(tk)
        buys.append(row)
    if buys:
        return buys
    for row in final.get("allowed_actions") or []:
        if row.get("action") not in _BUY_ACTIONS:
            continue
        if float(row.get("allowed_size_pct") or 0) <= 0:
            continue
        tk = str(row.get("ticker", ""))
        if tk in seen:
            continue
        seen.add(tk)
        buys.append(row)
    return buys


def list_risk_reduce_candidates(final: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Non-buy risk-reduce actions (Trim / Reduce) with non-zero allowed_size_pct."""
    if not final:
        return []
    return [
        a for a in (final.get("allowed_actions") or [])
        if a.get("action") in _RISK_REDUCE_ACTIONS
        and float(a.get("allowed_size_pct") or 0) != 0
    ]


def list_execution_candidates(final: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Deprecated alias — prefer list_buy_candidates / list_risk_reduce_candidates."""
    return list_buy_candidates(final) + list_risk_reduce_candidates(final)


def _format_candidate_line(row: dict[str, Any]) -> str:
    step = abs(float(row.get("allowed_size_pct") or 0))
    return (
        f"- **{row.get('name')}** ({row.get('ticker')}): **{row.get('action')}**"
        f" → {step:.1f}%p — {row.get('reason', '')}"
    )


def build_action_summary_section_lines(final: dict[str, Any] | None) -> list[str]:
    """§6 / trigger Action Summary — buy vs risk-reduce clearly separated."""
    metrics = count_executable_actions(final)
    buy_rows = list_buy_candidates(final)
    trim_rows = list_risk_reduce_candidates(final)

    lines = [
        "> **Planner actions (Park / Replace / Wait) are NOT executable unless "
        "`allowed_size_pct ≠ 0` in `final_execution_decision`.**",
        "",
        f"> **Actual Buy Allowed**: {metrics['actual_buy_allowed_count']} · "
        f"**Buy candidates today**: {metrics['executable_buy_count']} · "
        f"**Allowed risk-reduce candidates**: {metrics['allowed_risk_reduce_action_count']}",
        "",
        "### Buy candidates today (`final_execution_decision`)",
    ]
    if buy_rows:
        lines.extend(_format_candidate_line(r) for r in buy_rows)
    else:
        lines.append("- _None — 신규매수 없음 (Actual Buy Allowed 0)_")

    lines.extend(["", "### Allowed non-buy risk-reduce candidates (`final_execution_decision`)"])
    if trim_rows:
        lines.extend(_format_candidate_line(r) for r in trim_rows)
        if metrics["actual_buy_allowed_count"] == 0:
            lines.extend([
                "",
                "> **Trim proceeds**: 재매수 불가 (Actual Buy Allowed 0) — 현금 또는 파킹 유지.",
            ])
    else:
        lines.append("- _None_")
    lines.append("")
    return lines


def build_health_status_lines(
    *,
    health_gate: str | None,
    system_health_overall: str | None,
) -> list[str]:
    gate = health_gate or "—"
    overall = str(system_health_overall or "—").upper()
    lines = [
        f"- **Health gate**: **{gate}**",
        f"- **system_health_overall**: **{overall}**",
    ]
    if gate == "GREEN" and overall in {"WARN", "FAIL"}:
        lines.append(
            "- _health_gate GREEN = critical fail 없음 · "
            f"system_health_overall {overall} = non-critical warning 또는 점검 항목 존재_"
        )
    elif gate != "GREEN" or overall not in {"PASS", "GREEN"}:
        lines.append(
            "- _health_gate = critical fail 기준 실행 게이트 · "
            "system_health_overall = system_health.json overall_"
        )
    lines.append("")
    return lines


def sync_daily_report_system_health_overall(output_dir: Path) -> bool:
    """Align daily_report system_health_overall lines with system_health.json."""
    import json
    from pathlib import Path

    out = Path(output_dir)
    report_path = out / "daily_report.md"
    sh_path = out / "system_health.json"
    if not report_path.exists() or not sh_path.exists():
        return False
    sh_doc = json.loads(sh_path.read_text(encoding="utf-8"))
    expected = str(sh_doc.get("overall") or "").upper()
    if not expected:
        return False

    text = report_path.read_text(encoding="utf-8")
    marker = "**system_health_overall**:"
    if marker not in text:
        return False

    new_line = f"- **system_health_overall**: **{expected}**"
    lines = text.splitlines()
    changed = False
    for idx, line in enumerate(lines):
        if marker in line and line.strip() != new_line:
            lines[idx] = new_line
            changed = True
    if not changed:
        return False
    report_path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return True


def build_execution_authority_lines(final: dict[str, Any] | None, output_dir: Path | None = None) -> list[str]:
    """Top-of-report authoritative execution summary."""
    if not final:
        return []
    from src.alpha.target_write_audit import get_last_target_write_audit

    metrics = count_executable_actions(final)
    perms = final.get("execution_permissions") or {}
    dry = final.get("dry_run_days", 0)
    required = (final.get("operating") or {}).get("dry_run_required", 10)
    if not required:
        required = 10

    if (final or {}).get("target_guard_conflict_detected"):
        metrics["actual_buy_allowed_count"] = 0
        metrics["executable_buy_count"] = 0
        metrics["executable_action_count"] = 0

    write_audit = get_last_target_write_audit(output_dir) if output_dir else {}
    audit_status = final.get("target_write_audit_status") or (
        "blocked" if write_audit.get("target_write_allowed") is False else (
            "ok" if write_audit else "no_write_this_run"
        )
    )
    last_write_source = final.get("last_target_write_source") or write_audit.get("target_write_source", "—")
    last_write_allowed = final.get("last_target_write_allowed")
    if last_write_allowed is None:
        last_write_allowed = write_audit.get("target_write_allowed", "—")

    alpha_new = perms.get("alpha_auto_buy_permission") or perms.get("kr_alpha_new_buy", "BLOCKED")
    alpha_replace = perms.get("kr_alpha_replace", "BLOCKED")
    core_etf = perms.get("core_etf_permission", "—")
    alpha_research = perms.get("alpha_research_permission", "—")
    main_block = perms.get("main_block_reason", "—")
    sector_cov = perms.get("sector_coverage") or {}
    alpha_sector_gate = perms.get("alpha_sector_data_gate", "—")
    manual_review = perms.get("manual_review_required", False)
    ai_status = "—"
    vf_path_note = ""
    trims = metrics["risk_reduce_trims"]
    trim_line = "none"
    if trims:
        t = trims[0]
        trim_line = (
            f"{t.get('ticker')} only, max {abs(float(t.get('allowed_size_pct') or 0)):.1f}%p, "
            f"human approval required"
        )

    live_note = "live approval not yet granted" if dry < required else "dry-run complete"

    from src.validation.green_layers import evaluate_green_layers, format_green_layer_table_lines
    from src.report.authoritative_status import (
        ETF_ONLY_DISPLAY_NOTE,
        NO_TRADE_USER_LABEL,
        resolve_authoritative_execution,
    )

    green: dict[str, Any] = {}
    auth_exec: dict[str, Any] = {}
    if output_dir:
        data_dir = output_dir.parent / "data"
        green = evaluate_green_layers(data_dir, output_dir, final_doc=final)
        auth_exec = resolve_authoritative_execution(
            data_dir, output_dir, final_doc=final, green=green,
        )

    scope = auth_exec.get("execution_scope") or final.get("execution_scope", "—")
    display_scope = auth_exec.get("display_execution_scope") or final.get("execution_scope", "—")
    op_status = auth_exec.get("full_status") or green.get("full_status") or final.get("system_status", "—")

    lines = [
        "## 최종 실행 권위 (authoritative)",
        f"- **target_write_audit_status**: `{audit_status}`",
        f"- **last_target_write_source**: `{last_write_source}`",
        f"- **last_target_write_allowed**: {last_write_allowed}",
    ]
    if scope == "NO_TRADE" or metrics["actual_buy_allowed_count"] == 0:
        lines.append(f"- **Authoritative scope**: **{NO_TRADE_USER_LABEL}**")
        if display_scope and str(display_scope) != "NO_TRADE":
            lines.append(f"- **Policy/display scope**: `{display_scope}` — {ETF_ONLY_DISPLAY_NOTE}")
        lines.append(f"- **Execution permission**: **NO_TRADE**")
    if (final or {}).get("target_guard_conflict_detected"):
        lines.append("- **target_guard_conflict_detected**: **True** — system_health vs acceptance 불일치 또는 guard FAIL")
        lines.append("- **Actual Buy Allowed**: **0** (guard conflict lock)")
    else:
        lines.append(f"- **Actual Buy Allowed**: {metrics['actual_buy_allowed_count']}")
    lines.extend([
        f"- **Core ETF permission**: **{core_etf}**",
        f"- **Alpha auto-buy permission**: **{alpha_new}**",
        f"- **Alpha research permission**: **{alpha_research}**",
        f"- **Main block reason**: {main_block}",
        f"- **Alpha sector data gate**: `{alpha_sector_gate}` · "
        f"shortlist {sector_cov.get('candidate_sector_coverage_pct', '—')}% · "
        f"top10 {sector_cov.get('top10_sector_coverage_pct', '—')}% · "
        f"holdings {sector_cov.get('holdings_sector_coverage_pct', '—')}%",
        f"- **Manual review required**: **{'yes' if manual_review else 'no'}**",
        f"- **Buy candidates today**: {metrics['executable_buy_count']}",
        f"- **Allowed risk-reduce candidates**: {metrics['allowed_risk_reduce_action_count']}",
        f"- **Alpha Replace**: {alpha_replace}",
        f"- **Risk-reduce Trim Candidates**: {metrics['risk_reduce_trim_count']}"
        + (f" ({trim_line})" if trims else ""),
        f"- **Dry-run**: {dry}/{required}, {live_note}",
        f"- **Scope**: `{scope}` · operational `{op_status}`",
    ])
    if scope == "ETF_ONLY" and metrics["actual_buy_allowed_count"] == 0:
        lines.append(
            "- **ETF buy permission**: **none** (ETF_ONLY scope ≠ ETF 매수 허용 · Actual Buy Allowed=0)"
        )
    elif scope == "NO_TRADE":
        lines.append(
            "- **Execution mode**: **NO_TRADE** — acceptance/gate RED · 신규매수·ETF 매수·리밸런싱 실행 금지"
        )
    if trims and metrics["actual_buy_allowed_count"] == 0:
        lines.append(
            "- **Trim proceeds**: 재매수 불가 — 현금 또는 파킹 유지 (Actual Buy Allowed 0)"
        )
    if (final or {}).get("target_restore_occurred"):
        lines.append(
            "- **target_restore_occurred**: **True** — restore occurred, GREEN prohibited · Actual Buy 0 · risk-reduce human approval only"
        )
    if green:
        lines.extend(format_green_layer_table_lines(green))
    else:
        lines.append(
            "> **ETF_ONLY ≠ ETF 매수 허용** — scope는 ETF만 검토 가능 범위이며, Actual Buy Allowed가 0이면 ETF 신규매수도 금지입니다."
        )
        lines.append("")
    if output_dir:
        from src.validation.alpha_export_lists import build_alpha_screening_summary_lines

        lines.extend(build_alpha_screening_summary_lines(output_dir))
    return lines


def validate_report_clarity(
    output_dir: Any,
    *,
    final: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Post-pipeline clarity checks — returns pass/fail with detail lines."""
    from pathlib import Path

    import json

    out = Path(output_dir)
    failures: list[str] = []
    warnings: list[str] = []

    final_path = out / "final_execution_decision.json"
    final_doc = final
    if final_doc is None and final_path.exists():
        final_doc = json.loads(final_path.read_text(encoding="utf-8"))

    metrics = count_executable_actions(final_doc)
    authority_lines = build_execution_authority_lines(final_doc, out)

    report_path = out / "daily_report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""

    if report_text:
        if "None%" in report_text:
            failures.append("daily_report.md contains None% — use N/A or insufficient sample")
        if "pilot_entry_" in report_text and "shadow_pilot_candidate" not in report_text:
            failures.append("daily_report shows pilot_entry_ without shadow_pilot_candidate label")
        if "## 6. Executable Action Summary" in report_text:
            failures.append("daily_report still uses legacy 'Executable Action Summary' heading")
        if "### Execution candidates today" in report_text:
            failures.append("daily_report still uses legacy 'Execution candidates today' heading")
        if metrics["actual_buy_allowed_count"] == 0:
            buy_sec = _section_after(report_text, "### Buy candidates today")
            if buy_sec and "005440" in buy_sec and "Trim" in buy_sec:
                failures.append("Trim appears under Buy candidates when Actual Buy Allowed=0")
            if buy_sec and "_None" not in buy_sec and buy_sec.strip() not in {"", "- _None — 신규매수 없음 (Actual Buy Allowed 0)_"}:
                non_none = [ln for ln in buy_sec.splitlines() if ln.startswith("- **") and "_None" not in ln]
                if non_none:
                    failures.append("Buy candidates section lists rows while Actual Buy Allowed=0")
        trim_sec = _section_after(report_text, "### Allowed non-buy risk-reduce candidates")
        buy_sec_full = _section_after(report_text, "### Buy candidates today")
        if trim_sec and buy_sec_full:
            for ln in trim_sec.splitlines():
                if ln.startswith("- **") and ln in buy_sec_full:
                    failures.append("risk-reduce Trim duplicated under Buy candidates section")

        sh_path = out / "system_health.json"
        if sh_path.exists() and report_text:
            sh_doc = json.loads(sh_path.read_text(encoding="utf-8"))
            expected_overall = str(sh_doc.get("overall", "")).upper()
            if expected_overall:
                marker = "**system_health_overall**:"
                if marker not in report_text:
                    failures.append("daily_report missing system_health_overall")
                elif expected_overall not in report_text.split(marker, 1)[1][:40].upper():
                    failures.append(
                        f"daily_report system_health_overall != system_health.json ({expected_overall})"
                    )
                if (
                    "**health_gate**: **GREEN**" in report_text
                    and expected_overall == "WARN"
                    and "non-critical" not in report_text
                    and "critical fail" not in report_text.lower()
                ):
                    warnings.append(
                        "health_gate vs system_health_overall differ but explanation missing"
                    )
        auth_idx = report_text.find("## 최종 실행 권위")
        if auth_idx < 0:
            failures.append("daily_report.md missing authoritative block")
        else:
            pre_section1 = report_text.split("\n## 1.")[0] if "\n## 1." in report_text else report_text
            for needle in (
                "**Actual Buy Allowed**:",
                "**Core ETF permission**:",
                "**Alpha auto-buy permission**:",
                "**Risk-reduce Trim Candidates**:",
                "### GREEN Layer Status",
            ):
                if needle not in pre_section1:
                    failures.append(f"daily_report top block missing {needle}")
            first_section = report_text.find("## ", auth_idx + 1)
            if ops_idx := report_text.find("## 운용 상태 요약"):
                if ops_idx < auth_idx:
                    failures.append("authoritative block must appear before 운용 상태 요약")
            elif first_section > 0 and first_section < auth_idx:
                failures.append("authoritative block ordering invalid")

    brief_path = out / "daily_brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else {}
    exec_b = brief.get("execution") or {}
    if exec_b.get("actual_buy_allowed_count") != metrics["actual_buy_allowed_count"]:
        failures.append("daily_brief actual_buy_allowed_count != final_execution_decision")
    if exec_b.get("executable_action_count") != metrics["executable_buy_count"]:
        failures.append("daily_brief executable_action_count includes trim or mismatches final")
    if exec_b.get("allowed_risk_reduce_action_count", exec_b.get("risk_reduce_trim_count")) != metrics[
        "allowed_risk_reduce_action_count"
    ]:
        failures.append("daily_brief allowed_risk_reduce_action_count mismatches final")

    trigger_path = out / "trigger_alerts.md"
    trig = trigger_path.read_text(encoding="utf-8") if trigger_path.exists() else ""

    if trig:
        watch_n = brief.get("market", {}).get("watch_trigger_count")
        if watch_n is not None and f"**Watch Signals**: {watch_n}" not in trig:
            failures.append("trigger_alerts watch count != daily_brief watch_trigger_count")
        if trig and "**Replace**:" in trig and "Planner / gap actions" not in trig:
            failures.append("trigger_alerts lists Replace under executable-style summary")
        if "🟢 **domestic_beta buy signal**" in trig:
            failures.append("domestic_beta buy still ACTIVE in trigger_alerts")
        if "🟢 **domestic_beta watch signal**" in trig and "suppressed" not in trig.lower():
            failures.append("domestic_beta watch still ACTIVE (should be suppressed/watch-only)")
            if "suppressed" not in trig.lower() and "watch signal suppressed" not in trig:
                failures.append("domestic_beta watch still ACTIVE in trigger_alerts")

    for name in ("compass_report.md", "portfolio_actions.md"):
        p = out / name
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if "| **Buy** |" in text or "| Buy |" in text.split("## 5.")[-1] if "## 5." in text else "| Buy |" in text:
                if "**Buy**" in text or "Theoretical Demand" in text and "**Buy**" in text:
                    pass
            # Fail on raw Buy action label in gap table rows
            for line in text.splitlines():
                if line.startswith("|") and "| **Buy** |" in line:
                    failures.append(f"{name} still shows raw Buy in action column")
                if line.startswith("|") and "| **BuyCandidate** |" in line:
                    failures.append(f"{name} still shows BuyCandidate in action column")

    opp_path = out / "opportunity_analytics.json"
    if opp_path.exists():
        opp = json.loads(opp_path.read_text(encoding="utf-8"))
        if int(opp.get("closed_signals") or 0) < 30:
            if not opp.get("statistics_validated") is False:
                warnings.append("opportunity_analytics should mark statistics_validated=false")
            report_opp = report_text
            if report_opp and "heuristic" not in report_opp.lower() and "Opportunity Analytics" in report_opp:
                failures.append("Opportunity section missing heuristic warning when closed < 30")

    if brief.get("market", {}).get("watch_triggers") and "asset_buy_domestic_beta" in brief["market"]["watch_triggers"]:
        failures.append("domestic_beta in watch_triggers despite target 0")

    sys_status = brief.get("system_status") or {}
    acceptance = json.loads((out / "acceptance_report.json").read_text(encoding="utf-8")) if (out / "acceptance_report.json").exists() else {}

    from src.report.authoritative_status import (
        ETF_ONLY_DISPLAY_NOTE,
        NO_TRADE_USER_LABEL,
        resolve_authoritative_execution,
        sync_acceptance_authoritative_scope_fields,
    )

    data_dir = out.parent / "data"
    if data_dir.exists():
        sync_acceptance_authoritative_scope_fields(data_dir, out)
        acceptance = json.loads((out / "acceptance_report.json").read_text(encoding="utf-8")) if (out / "acceptance_report.json").exists() else {}

    auth = resolve_authoritative_execution(
        data_dir, out, final_doc=final_doc, acceptance_doc=acceptance,
    ) if data_dir.exists() else {}
    auth_scope = str(auth.get("execution_scope") or acceptance.get("authoritative_execution_scope") or "")
    display_scope = str(
        auth.get("display_execution_scope")
        or acceptance.get("display_execution_scope")
        or acceptance.get("execution_scope")
        or (final_doc or {}).get("execution_scope")
        or "",
    )
    scope_explanation = str(
        acceptance.get("execution_scope_explanation")
        or auth.get("execution_scope_explanation")
        or sys_status.get("execution_scope_explanation")
        or "",
    )

    brief_scope = str(sys_status.get("execution_scope") or exec_b.get("execution_scope") or "")
    if auth_scope and brief_scope and auth_scope != brief_scope:
        failures.append(
            f"daily_brief authoritative scope ({brief_scope}) != resolved authoritative ({auth_scope})"
        )

    if auth_scope and display_scope and auth_scope != display_scope:
        if not scope_explanation:
            failures.append(
                f"dual scope without explanation: authoritative={auth_scope}, display={display_scope}"
            )
        if report_text and auth_scope == "NO_TRADE":
            header = report_text.split("\n## 1.")[0] if "\n## 1." in report_text else report_text
            if NO_TRADE_USER_LABEL not in header and "NO_TRADE" not in header:
                failures.append("daily_report missing authoritative NO_TRADE label in top block")
            if display_scope == "ETF_ONLY" and not (
                ETF_ONLY_DISPLAY_NOTE in header
                or "ETF 매수 허가가 아님" in header
                or ("ETF 매수" in header and "≠" in header)
            ):
                failures.append("daily_report missing ETF_ONLY is not buy permission disclaimer")

    if report_text and metrics["actual_buy_allowed_count"] == 0:
        header = report_text.split("\n## 1.")[0] if "\n## 1." in report_text else report_text
        if "Actual Buy Allowed**: 0" not in header and "Actual Buy Allowed**: **0**" not in header:
            failures.append("daily_report missing Actual Buy Allowed=0 in authoritative block")
        if "신규매수 없음" not in header and "신규매수 없음" not in report_text[:2000]:
            if auth_scope == "NO_TRADE" and "NO_TRADE" not in header:
                failures.append("daily_report missing 신규매수 없음 when authoritative NO_TRADE")

    v2_path = out / "alpha_v2_summary.json"
    if v2_path.exists() and auth_scope:
        v2 = json.loads(v2_path.read_text(encoding="utf-8"))
        v2_scope = str((v2.get("execution_context") or {}).get("execution_scope") or "")
        if v2_scope and v2_scope != auth_scope:
            failures.append(
                f"alpha_v2_summary.execution_scope ({v2_scope}) != authoritative ({auth_scope})"
            )

    if auth_scope == "NO_TRADE" or str(sys_status.get("full_status") or "").upper() == "RED":
        op_verdict = str(exec_b.get("operational_verdict") or "")
        if (
            brief_scope == auth_scope
            and "NO_TRADE" not in op_verdict
            and NO_TRADE_USER_LABEL not in op_verdict
            and scope_explanation
        ):
            warnings.append(
                "operational_verdict text uses display scope wording; authoritative fields aligned"
            )
        elif brief_scope == "ETF_ONLY" and auth_scope == "NO_TRADE" and not scope_explanation:
            failures.append("RED/NO_TRADE: daily_brief.system_status still ETF_ONLY without scope explanation")

    return {
        "pass": len(failures) == 0,
        "failures": failures,
        "warnings": warnings,
        "metrics": metrics,
        "authority_preview": authority_lines[:8],
    }


def _section_after(text: str, heading: str) -> str:
    idx = text.find(heading)
    if idx < 0:
        return ""
    rest = text[idx + len(heading):]
    nxt = rest.find("\n### ")
    if nxt < 0:
        nxt = rest.find("\n## ")
    return rest[:nxt] if nxt >= 0 else rest
