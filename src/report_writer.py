from __future__ import annotations



import json

from datetime import datetime, timezone

from pathlib import Path



import pandas as pd



from src.models import DataGate, GapRow, MarketIndicators, TradeAction, TriggerAlert
from src.execution_scope import is_executable_kr_risk_trim, kr_alpha_report_mode
from src.report.io_utils import read_output_json


def build_daily_report_status_summary(
    output_dir: Path | None,
    exposure_lookthrough: dict | None = None,
) -> list[str]:
    """daily_report 상단 — technical / policy_cap / operational / look-through / stale."""
    from src.exposure.look_through import summarize_exposure_concentration
    from src.report.execution_metrics import build_execution_authority_lines

    if output_dir is None:
        return []
    data_dir = output_dir.parent / "data"
    from src.report.authoritative_status import build_authoritative_status_snapshot

    auth = build_authoritative_status_snapshot(data_dir, output_dir)
    final_path = output_dir / "final_execution_decision.json"
    if not final_path.exists():
        return []
    final = json.loads(final_path.read_text(encoding="utf-8"))
    gpt_path = output_dir / "gpt_context.json"
    policy_config_gate = final.get("data_gate", "—")
    if gpt_path.exists():
        gpt = json.loads(gpt_path.read_text(encoding="utf-8"))
        policy_config_gate = gpt.get("policy_gate") or policy_config_gate
    tech_status = auth.get("technical_status") or "—"
    tech_scope = auth.get("execution_scope") or "—"
    cap = final.get("policy_cap") or {}
    cap_active = bool(cap.get("active"))
    cap_label = str(cap.get("cap_regime") or ("inactive" if not cap_active else "—"))
    capped_scope = cap.get("capped_execution_scope") or auth.get("execution_scope") or final.get("execution_scope", "—")
    op_status = auth.get("operational_status") or "—"
    op_scope = auth.get("execution_scope") or "—"
    cap_line = (
        f"- **Policy execution cap**: `{'ACTIVE' if cap_active else 'inactive'}`"
        + (f" · capped scope `{capped_scope}`" if cap_active else "")
    )
    exposure_line = summarize_exposure_concentration(exposure_lookthrough)

    stale_line = "—"
    target_guard_line = ""
    core_gate_status = "pass"
    cov_path = output_dir / "price_coverage_report.json"
    if cov_path.exists():
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
        stale = (cov.get("core_price_gate") or {}).get("stale_core") or []
        if stale:
            parts = [
                f"{s.get('ticker')} ({s.get('last_price_date')}, {s.get('price_age_business_days')}영업일)"
                for s in stale[:5]
            ]
            stale_line = ", ".join(parts) + (" …" if len(stale) > 5 else "")
            core_gate_status = str((cov.get("core_price_gate") or {}).get("status", "pass"))

    core_critical_stale: list[dict] = []
    legacy_stale: list[dict] = []
    executable_stale: list[dict] = []
    sh_path = output_dir / "system_health.json"
    if sh_path.exists():
        sh = json.loads(sh_path.read_text(encoding="utf-8"))
        for chk in sh.get("checks") or []:
            if not isinstance(chk, dict):
                continue
            if chk.get("name") == "core_price_gate":
                core_gate_status = str(chk.get("status", core_gate_status))
                detail = chk.get("detail") or {}
                stale = detail.get("stale_core") or []
                core_critical_stale = detail.get("stale_core_critical") or []
                legacy_stale = detail.get("stale_legacy_holding") or []
                executable_stale = detail.get("stale_executable_actions") or []
                if stale:
                    parts = [
                        f"{s.get('ticker')} ({s.get('last_price_date')}, {s.get('price_age_business_days')}영업일)"
                        for s in stale[:5]
                    ]
                    stale_line = ", ".join(parts) + (" …" if len(stale) > 5 else "")
            if chk.get("name") == "target_portfolio_guard":
                detail = chk.get("detail") or {}
                target_guard_line = (
                    f"status `{detail.get('target_portfolio_guard_status', detail.get('status', '—'))}` · "
                    f"severity `{detail.get('target_portfolio_guard_severity', detail.get('severity', '—'))}` · "
                    f"prev `{str(detail.get('previous_hash', ''))[:12]}` → "
                    f"curr `{str(detail.get('current_hash', ''))[:12]}` · "
                    f"approval_flag `{detail.get('approval_flag', False)}` · "
                    f"changed_rows `{detail.get('changed_rows', 0)}` · "
                    f"fail_reasons `{detail.get('fail_reasons_count', 0)}` · "
                    f"proposal_leak `{detail.get('system_proposal_leak_count', 0)}` · "
                    f"material `{detail.get('unknown_material_count', 0)}`"
                )

    lines = build_execution_authority_lines(final, output_dir)
    try:
        from src.validation.alpha_gate_diagnostics import (
            build_alpha_gate_diagnostics,
            format_alpha_gate_report_lines,
        )

        alpha_diag = build_alpha_gate_diagnostics(data_dir, output_dir)
        lines.extend(format_alpha_gate_report_lines(alpha_diag))
        from src.validation.alpha_shortlist_diagnostics import format_alpha_shortlist_report_lines

        shortlist_summary = read_output_json(output_dir / "alpha_shortlist_summary.json") or {}
        if shortlist_summary:
            lines.extend(format_alpha_shortlist_report_lines(shortlist_summary))
        from src.validation.policy_cap_counterfactual import format_policy_cap_counterfactual_report_lines

        cf_doc = read_output_json(output_dir / "policy_cap_counterfactual.json") or {}
        if cf_doc:
            lines.extend(format_policy_cap_counterfactual_report_lines(cf_doc))
        from src.validation.core_etf_permission_diagnostics import format_core_etf_report_lines

        etf_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
        if etf_doc:
            lines.extend(format_core_etf_report_lines(etf_doc))
        from src.validation.data_gate_diagnostics import format_data_gate_report_lines

        dg_doc = read_output_json(output_dir / "data_gate_diagnostics.json") or {}
        if dg_doc:
            lines.extend(format_data_gate_report_lines(dg_doc))
        from src.validation.market_indicator_schema_diagnostics import format_market_schema_report_lines

        ms_doc = read_output_json(output_dir / "market_indicator_schema_diagnostics.json") or {}
        if ms_doc:
            lines.extend(format_market_schema_report_lines(ms_doc))
        from src.validation.pmi_kr_source_policy import (
            format_pmi_kr_preflight_report_lines,
            write_pmi_kr_source_policy,
        )
        from src.validation.data_gate_green_preflight import write_data_gate_green_preflight

        policy_doc = read_output_json(output_dir / "pmi_kr_source_policy.json") or write_pmi_kr_source_policy(
            data_dir, output_dir
        )
        preflight_doc = read_output_json(output_dir / "data_gate_green_preflight.json") or write_data_gate_green_preflight(
            data_dir, output_dir
        )
        if policy_doc:
            lines.extend(format_pmi_kr_preflight_report_lines(policy_doc, preflight_doc))
        from src.validation.pmi_kr_manual_verified_reevaluation import (
            format_pmi_kr_reevaluation_report_lines,
        )

        reeval_doc = read_output_json(output_dir / "pmi_kr_manual_verified_reevaluation.json") or {}
        if reeval_doc:
            lines.extend(format_pmi_kr_reevaluation_report_lines(reeval_doc))
    except Exception:
        pass
    lines.extend([
        "## 운용 상태 요약",
        f"- **Policy config gate**: `{policy_config_gate}`",
        cap_line,
        f"- **technical_status**: `{tech_status}` · scope `{tech_scope}`",
        f"- **operational_status**: `{op_status}` · scope `{op_scope}`",
        f"- **core_price_gate**: `{core_gate_status}`",
        f"- **look-through 편중**: {exposure_line}",
        f"- **core_price stale**: {stale_line}",
        (
            f"- **core_critical_stale_tickers**: "
            + (", ".join(str(x.get("ticker")) for x in core_critical_stale[:10]) if core_critical_stale else "—")
        ),
        (
            f"- **legacy_holding_stale_tickers**: "
            + (", ".join(str(x.get("ticker")) for x in legacy_stale[:10]) if legacy_stale else "—")
        ),
        (
            f"- **executable_action_stale_tickers**: "
            + (", ".join(str(x.get("ticker")) for x in executable_stale[:10]) if executable_stale else "—")
        ),
        (f"- **target_portfolio_guard**: {target_guard_line}" if target_guard_line else ""),
    ])
    if sh_path.exists():
        try:
            sh = json.loads(sh_path.read_text(encoding="utf-8"))
            for chk in sh.get("checks") or []:
                if isinstance(chk, dict) and chk.get("name") == "target_portfolio_guard":
                    detail = chk.get("detail") or {}
                    rec = detail.get("recommended_action")
                    if rec and rec != "none":
                        lines.append(f"- **target_guard_recommended_action**: {rec}")
                    recovery = detail.get("recovery_guide")
                    if recovery:
                        lines.append(f"- **target_guard_recovery**: {recovery}")
                    break
        except Exception:
            pass
    lines.append("")
    diff_path = output_dir / "target_portfolio_guard_diff.csv"
    if diff_path.exists():
        try:
            diff_df = pd.read_csv(diff_path, dtype=str).fillna("")
            if not diff_df.empty:
                preview = diff_df.head(10).to_dict(orient="records")
                lines.append("- **target_guard_changed_rows_top10**:")
                for r in preview:
                    lines.append(
                        f"  - {r.get('ticker')} {r.get('name')} | "
                        f"{r.get('previous_weight')} -> {r.get('current_weight')} | {r.get('reason')}"
                    )
                lines.append("")
        except Exception:
            pass
    return lines


def _policy_cap_active(output_dir: Path) -> bool:
    path = output_dir / "final_execution_decision.json"
    if not path.exists():
        return False
    final = json.loads(path.read_text(encoding="utf-8"))
    return bool((final.get("policy_cap") or {}).get("active"))


def write_current_vs_target(rows: list[GapRow], path: Path) -> None:

    df = pd.DataFrame([

        {

            "ticker": r.ticker,

            "name": r.name,

            "asset_group": r.asset_group,

            "current_weight": r.current_weight,

            "target_weight": r.target_weight,

            "gap": r.gap,

            "status": r.status,

        }

        for r in rows

    ])

    path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(path, index=False)





def write_trade_actions(actions: list[TradeAction], path: Path) -> None:

    df = pd.DataFrame([a.model_dump() for a in actions])

    path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(path, index=False)





def write_trigger_alerts(
    path: Path,
    alerts: list[TriggerAlert],
    actions: list[TradeAction],
    *,
    review_actions: list[TradeAction] | None = None,
    execution_scope: str | None = None,
    gap_rows: list[GapRow] | None = None,
    asset_group_gaps: dict[str, dict[str, float]] | None = None,
    data_gate: str | None = None,
    dry_run_days: int | None = None,
    alpha_position_action: str | None = None,
    execution_policy: dict | None = None,
) -> None:
    from src.report.execution_metrics import count_executable_actions
    from src.trigger_metrics import list_risk_reduce_active_triggers, list_suppressed_signals, list_watch_triggers

    kr_tickers = {
        r.ticker for r in (gap_rows or []) if r.asset_group == "kr_alpha"
    }
    lines = ["# Trigger Alerts", ""]
    if execution_scope:
        lines.extend([f"**Execution Scope**: `{execution_scope}`", ""])

    buy_exec = 0
    final_path = path.parent / "final_execution_decision.json"
    if final_path.exists():
        final = json.loads(final_path.read_text(encoding="utf-8"))
        buy_exec = count_executable_actions(final)["actual_buy_allowed_count"]
    else:
        buy_exec = sum(
            1 for a in actions
            if a.ticker != "PORTFOLIO" and a.action in {"Buy", "Buy-allowed", "BuyCandidate"}
            and float(a.allowed_size_pct or 0) > 0
        )
    watch_triggers = list_watch_triggers(alerts, asset_group_gaps)
    suppressed = list_suppressed_signals(alerts)
    risk_reduce = list_risk_reduce_active_triggers(alerts)
    if watch_triggers or buy_exec == 0:
        gate_note = f"data_gate={data_gate or '—'}"
        if dry_run_days is not None:
            gate_note += f", dry-run {dry_run_days}/10"
        lines.extend([
            "> **Watch Signal ≠ Actual Buy Allowed**",
            "> - **Watch Signal** = 매수 후보 조건 충족 (관찰·준비)",
            "> - **Actual Buy Allowed** = data_gate·dry-run·scope·hard stop 통과 후 실제 매수 가능",
            f"> - **Watch Signals**: {len(watch_triggers)} · **Actual Buy Allowed**: {buy_exec} · "
            f"**Risk-reduce Signals**: {len(risk_reduce)} ({gate_note})",
        ])
        if suppressed:
            lines.append(f"> - **Suppressed Signals**: {', '.join(suppressed)}")
        lines.append("")

    kr_mode = kr_alpha_report_mode(execution_scope)
    review_only = kr_mode == "review_only"

    lines.extend(["## Today", ""])
    for alert in alerts:
        icon = {"active": "🟢", "inactive": "⚪", "watch": "🟡", "risk": "🔴"}.get(alert.status.value, "•")
        lines.append(f"- {icon} **{alert.label}**: {alert.detail}")

    lines.extend(["", "## Action Summary", ""])

    final_doc = None
    final_path = path.parent / "final_execution_decision.json"
    if final_path.exists():
        final_doc = json.loads(final_path.read_text(encoding="utf-8"))

    from src.report.execution_metrics import build_action_summary_section_lines, list_risk_reduce_candidates

    lines.extend(build_action_summary_section_lines(final_doc))

    risk_reduce_tickers = {c.get("ticker") for c in list_risk_reduce_candidates(final_doc)}

    lines.append("### Planner / gap actions (not executable today)")
    by_action: dict[str, list[str]] = {}
    for act in actions:
        if act.ticker == "PORTFOLIO":
            lines.append(f"- **Portfolio**: {act.action} — {act.reason}")
            continue
        if act.ticker in risk_reduce_tickers:
            continue
        if act.action == "Review-only" or act.ticker in kr_tickers:
            continue
        by_action.setdefault(act.action, []).append(f"{act.name} ({act.ticker})")
    if by_action:
        for action, names in sorted(by_action.items()):
            lines.append(f"- **{action}**: {', '.join(names)}")
    else:
        lines.append("- _해당 없음 (Wait/Hold/Park 위주)_")

    kr_risk_trims = [
        a for a in actions
        if a.ticker != "PORTFOLIO"
        and a.ticker in kr_tickers
        and is_executable_kr_risk_trim(a, execution_policy)
        and a.ticker not in risk_reduce_tickers
    ]
    if kr_risk_trims:
        lines.extend(["", "### Allowed non-buy risk-reduce candidates (trade_actions cross-check)", ""])
        for act in kr_risk_trims:
            step = abs(float(act.allowed_size_pct or 0))
            lines.append(
                f"- **Trim**: {act.name} ({act.ticker})"
                + (f" → **{step:.1f}%p**" if step > 0 else "")
                + f" — {act.reason}"
            )

    review_pool = list(review_actions or [])
    for act in actions:
        if act.ticker == "PORTFOLIO":
            continue
        if is_executable_kr_risk_trim(act, execution_policy):
            continue
        if act.action == "Review-only" or act.ticker in kr_tickers:
            review_pool.append(act)
    if review_pool:
        title = "### Review-only — kr_alpha (실행 금지)"
        if alpha_position_action == "RISK_REDUCE_ONLY":
            title = "### Review-only — kr_alpha (Replace·신규매수 금지, Trim은 위 risk-reduce candidates 참조)"
        elif not review_only:
            title = "### kr_alpha — 참고 (theoretical)"
        lines.extend(["", title, ""])
        review_map: dict[str, list[str]] = {}
        seen: set[str] = set()
        for act in review_pool:
            if act.ticker in seen:
                continue
            seen.add(act.ticker)
            if is_executable_kr_risk_trim(act, execution_policy):
                continue
            if "Replace" in act.action or "Replace" in act.reason:
                label = "theoretical Replace [매도금지]"
            elif "Trim" in act.action or "Trim" in act.reason:
                label = "theoretical Trim [매도금지]"
            elif act.action == "Review-only":
                label = "Review-only"
            else:
                label = f"theoretical {act.action}"
            review_map.setdefault(label, []).append(f"{act.name} ({act.ticker})")
        for action, names in sorted(review_map.items()):
            lines.append(f"- **{action}**: {', '.join(names)}")



    lines.extend([
        "",
        "## Allowed Action",
        "",
        "- ETF·현금·단기채: scope 허용 범위 내 Hold/Trim/Buy-allowed만 검토.",
    ])
    if review_only:
        if alpha_position_action == "RISK_REDUCE_ONLY":
            lines.extend([
                "> **kr_alpha: Replace·신규매수 실행 금지.**",
                "> **리스크 축소 Trim만** `trade_actions.csv` Executable — 사람 승인·1회·소액.",
                "> 그 외 kr_alpha는 `kr_alpha_review_actions.csv` / theoretical 참고.",
                "",
            ])
        else:
            lines.extend([
                "- kr_alpha: Review-only — `kr_alpha_review_actions.csv` / theoretical 참고.",
            ])
    else:
        lines.extend([
            "- kr_alpha: Executable — 트리거·holdings_review·본인 승인 후 소액만.",
        ])
    lines.extend([
        "- 실제 Buy는 트리거 active + scope 허용 시에만.",
        "",
    ])

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text("\n".join(lines), encoding="utf-8")





def write_daily_report(

    path: Path,

    *,

    data_gate: DataGate,

    market: MarketIndicators,

    gap_rows: list[GapRow],

    alerts: list[TriggerAlert],

    actions: list[TradeAction],

    execution_level: int,

    policy_gate: DataGate | None = None,

    health_gate: DataGate | None = None,

    theoretical_actions: list[TradeAction] | None = None,

    review_actions: list[TradeAction] | None = None,

    health_overall: str | None = None,

    execution_scope: str | None = None,

    alpha_trade_permission: str | None = None,

    alpha_position_action: str | None = None,

    data_dir: Path | None = None,

    output_dir: Path | None = None,

    hard_stops_detail: dict | None = None,

    exposure_lookthrough: dict | None = None,

    daily_brief: dict | None = None,

) -> None:

    lines = [

        "# Daily Portfolio Execution Report",

        "",

        f"- Date: {market.date}",

        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",

        "",

    ]

    lines.extend(build_daily_report_status_summary(output_dir, exposure_lookthrough))

    if output_dir is not None:
        saa_md_path = output_dir / "saa_restart_readiness_report.md"
        if saa_md_path.exists():
            lines.append(saa_md_path.read_text(encoding="utf-8"))

    if daily_brief:
        from src.report.export_daily_brief import build_daily_report_v2_sections

        lines.extend(build_daily_report_v2_sections(daily_brief))
        if output_dir is not None:
            from src.alpha_v2_gate import (
                build_daily_report_alpha_v2_section,
                build_daily_report_flow_section,
            )

            lines.extend(build_daily_report_alpha_v2_section(output_dir))
            lines.extend(build_daily_report_flow_section(output_dir))
        from src.shadow.history_ledger import build_daily_report_shadow_history_lines

        shadow = (daily_brief or {}).get("shadow_history")
        lines.extend(build_daily_report_shadow_history_lines(shadow))
    elif output_dir is not None:
        brief_path = output_dir / "daily_brief.json"
        if brief_path.exists():
            from src.report.export_daily_brief import build_daily_report_v2_sections

            lines.extend(build_daily_report_v2_sections(json.loads(brief_path.read_text(encoding="utf-8"))))

    lines.extend([

        "## 1. 실행 범위 · 게이트",

        f"- **Execution Scope**: `{execution_scope or '—'}`",

        f"- **Executable Data Gate**: **{data_gate}** · 실행 레벨 **{execution_level}**",

    ])

    if alpha_trade_permission:

        lines.append(f"- **Alpha Trade Permission**: `{alpha_trade_permission}`")

    if alpha_position_action:

        lines.append(f"- **Alpha Position Action**: `{alpha_position_action}`")

    if output_dir is not None:
        vf_path = output_dir / "validation_findings.json"
        final_path = output_dir / "final_execution_decision.json"
        if final_path.exists():
            final_doc = json.loads(final_path.read_text(encoding="utf-8"))
            perms = final_doc.get("execution_permissions") or {}
            if perms.get("core_etf_permission"):
                lines.append(
                    f"- **Core ETF permission**: **{perms.get('core_etf_permission')}** · "
                    f"**Alpha auto-buy**: **{perms.get('alpha_auto_buy_permission', '—')}** · "
                    f"**Alpha research**: **{perms.get('alpha_research_permission', '—')}**"
                )
            if perms.get("alpha_sector_data_gate"):
                lines.append(f"- **Alpha sector data gate**: `{perms.get('alpha_sector_data_gate')}`")
        if vf_path.exists():
            vf = json.loads(vf_path.read_text(encoding="utf-8"))
            lines.append(
                f"- **AI validation status**: `{vf.get('ai_validation_status', '—')}` · "
                f"findings {vf.get('finding_count', 0)}"
            )

    lines.append("")

    if market.regime_expires_date:
        from src.operational_checklist import regime_expiry_check

        exp_status, exp_detail = regime_expiry_check(
            market.date,
            market.regime_expires_date,
            regime=market.regime,
        )
        lines.append(f"- **수동 레짐**: `{market.regime}` · 만료 `{market.regime_expires_date}`")
        override_active = False
        if output_dir is not None:
            regime_path = output_dir / "compass_regime.json"
            if regime_path.exists():
                reg = json.loads(regime_path.read_text(encoding="utf-8"))
                override_active = bool((reg.get("override") or {}).get("active"))
        if market.regime_override_reason:
            label = "Override 사유" if override_active else "Regime memo (수동 레짐 메모)"
            lines.append(f"- **{label}**: {market.regime_override_reason}")
        if market.regime_set_date:
            lines.append(f"- **설정일**: {market.regime_set_date}")
        if exp_status == "fail":
            lines.extend([
                "",
                "> ⚠️ **Manual regime expired** — 갱신 전까지 computed regime 사용 또는 execution 제한 유지.",
                f"> {exp_detail}",
            ])
        elif exp_status == "warn":
            lines.extend([
                "",
                "> ⚠️ **Manual regime expires soon** — 다음 실행 전 갱신 권장.",
                f"> {exp_detail}",
            ])
        lines.append("")

    if hard_stops_detail:
        lines.extend(["### Hard stops · Policy guards", ""])
        for item in hard_stops_detail.get("risk_hard_stops", []):
            lines.append(
                f"- **리스크** `{item['code']}` "
                f"({item.get('ticker') or 'portfolio'}): {item['detail']}"
            )
        for g in hard_stops_detail.get("policy_guards", []):
            lines.append(f"- **정책** `{g}`")
        lines.append(f"- _{hard_stops_detail.get('note', '')}_")
        lines.append("")

    if policy_gate or health_gate:

        system_health_overall = health_overall
        if output_dir is not None:
            sh_path = output_dir / "system_health.json"
            if sh_path.exists():
                sh_doc = json.loads(sh_path.read_text(encoding="utf-8"))
                system_health_overall = sh_doc.get("overall", health_overall)

        from src.report.execution_metrics import build_health_status_lines

        lines.extend([
            f"- **Policy config gate**: **{policy_gate or '—'}**",
            f"- **Policy execution cap**: **{'ACTIVE' if output_dir and _policy_cap_active(output_dir) else 'inactive'}**",
        ])
        lines.extend(build_health_status_lines(
            health_gate=str(health_gate) if health_gate else None,
            system_health_overall=system_health_overall,
        ))


    kr_mode = kr_alpha_report_mode(execution_scope)
    review_only = kr_mode == "review_only"

    if review_only and alpha_position_action == "RISK_REDUCE_ONLY":
        lines.extend([
            "> **kr_alpha: Replace·신규매수 실행 금지.**",
            "> **리스크 축소 Trim만** `trade_actions.csv`에 Executable — 사람 승인·1회·소액.",
            "> 그 외 kr_alpha Replace/Trim은 theoretical · `kr_alpha_review_actions.csv` 참고.",
            "",
        ])
    elif review_only:
        lines.extend([
            "> **kr_alpha 개별주 Replace/Trim은 실행 신호가 아닙니다.**",
            "> `trade_actions.csv`=Executable · `kr_alpha_review_actions.csv`=Review/theoretical",
            "",
        ])
    else:
        lines.extend([
            "> **kr_alpha Executable** — 사람 승인·소액·dry-run 정책 준수.",
            "> holdings_review TRIM/REPLACE와 충돌 시 Buy는 자동 보류됩니다.",
            "",
        ])

    if data_gate == "RED":

        lines.extend([

            "> **오늘 실행 금지** — Executable 액션은 No Trade만 포함합니다.",

            "",

        ])



    lines.extend([

        "## 2. Current Regime",

        f"**{market.regime}**",

        "",

        "## 3. ETF·현금·채권 — Executable Gap Actions",

        "",

        "| Ticker | Name | Group | Current | Target | Gap | Status | Action |",

        "|--------|------|-------|--------:|-------:|----:|--------|--------|",

    ])

    action_map = {a.ticker: a.action for a in actions}

    for row in gap_rows:

        if row.current_weight == 0 and row.target_weight == 0:

            continue

        if row.asset_group == "kr_alpha":

            continue

        lines.append(

            f"| {row.ticker} | {row.name} | {row.asset_group} | {row.current_weight:.1f}% | "

            f"{row.target_weight:.1f}% | {row.gap:+.1f}%p | {row.status} | {action_map.get(row.ticker, '—')} |"

        )



    if data_dir is not None:
        from src.config import load_yaml
        from src.trim_sizing import trim_markdown_lines

        try:
            rules = load_yaml(data_dir / "trigger_rules.yaml")
            lines.extend(trim_markdown_lines(actions, rules=rules))
        except (OSError, ValueError):
            pass

    kr_section = (
        "## 4. kr_alpha — Review Only (실행 금지)"
        if review_only and alpha_position_action != "RISK_REDUCE_ONLY"
        else "## 4. kr_alpha — Risk-Reduce Trim Only (Replace·신규 금지)"
        if review_only
        else "## 4. kr_alpha — Executable (사람 승인 필수)"
    )
    exec_col = (
        "Risk-reduce Trim"
        if alpha_position_action == "RISK_REDUCE_ONLY"
        else "Review-only"
        if review_only
        else "Executable"
    )

    lines.extend([

        "",

        kr_section,

        "",

        "| Ticker | Name | Current | Target | Gap | Status | Theoretical | " + exec_col + " |",

        "|--------|------|--------:|-------:|----:|--------|-------------|------------|",

    ])

    theory_map = {a.ticker: a.action for a in (theoretical_actions or [])}

    for row in gap_rows:

        if row.asset_group != "kr_alpha":

            continue

        if row.current_weight == 0 and row.target_weight == 0:

            continue

        lines.append(

            f"| {row.ticker} | {row.name} | {row.current_weight:.1f}% | "

            f"{row.target_weight:.1f}% | {row.gap:+.1f}%p | {row.status} | "

            f"{theory_map.get(row.ticker, '—')} | {action_map.get(row.ticker, exec_col if review_only else '—')} |"

        )



    lines.extend(["", "## 5. Trigger Status", ""])

    for alert in alerts:

        lines.append(f"- {alert.label}: {alert.status.value} — {alert.detail}")



    lines.extend(["", "## 6. Action Summary", ""])

    final_doc = None
    if output_dir is not None:
        final_path = output_dir / "final_execution_decision.json"
        if final_path.exists():
            final_doc = json.loads(final_path.read_text(encoding="utf-8"))

    from src.report.execution_metrics import build_action_summary_section_lines, list_risk_reduce_candidates

    lines.extend(build_action_summary_section_lines(final_doc))

    risk_reduce_tickers = {c.get("ticker") for c in list_risk_reduce_candidates(final_doc)}

    lines.append("### Planner / gap actions (not executable today)")
    summary: dict[str, list[str]] = {}

    for act in actions:

        if act.ticker == "PORTFOLIO":

            lines.append(f"- **Portfolio**: {act.action} — {act.reason}")

            continue

        if act.ticker in risk_reduce_tickers:
            continue

        row = next((r for r in gap_rows if r.ticker == act.ticker), None)

        if row and row.asset_group == "kr_alpha":
            continue

        summary.setdefault(act.action, []).append(act.name)

    for action, names in sorted(summary.items()):

        lines.append(f"- **{action}**: {', '.join(names) if names else 'None'}")



    if review_actions:

        ref_title = (
            "## 7. kr_alpha Planner Reference (Allowed risk-reduce Trim은 §6·trade_actions)"
            if alpha_position_action == "RISK_REDUCE_ONLY"
            else "## 7. kr_alpha Theoretical Gap (참고용)"
        )
        lines.extend(["", ref_title, ""])

        for act in review_actions:

            if act.ticker == "PORTFOLIO":

                continue

            lines.append(f"- {act.name} ({act.ticker}): **{act.action}** — {act.reason}")



    if exposure_lookthrough:
        from src.exposure.look_through import format_exposure_markdown

        lines.extend(["", format_exposure_markdown(exposure_lookthrough), ""])

    lines.extend([

        "",

        "## 8. Next Trigger",

        "- KOSPI -5% from recent high → buy_1",

        "- S&P500 -5% from recent high → buy_1",

        "- VIX > 25 → stop-buy zone",

        "- VIX > 30 → risk defense",

        "",

        "> MVP v0.1 — execution assistant, not auto-trading.",

    ])

    if data_dir is not None and output_dir is not None:
        from src.operational_checklist import checklist_markdown_section

        next_section = 9
        lines.extend(checklist_markdown_section(data_dir, output_dir, as_of=market.date, section_no=next_section))
        next_section += 1

        from src.hakedaka_gate import write_macro_scenario, write_research_checklist

        write_macro_scenario(data_dir, output_dir)
        macro_path = output_dir / "macro_scenario.json"
        if macro_path.exists():
            import json as _json

            macro = _json.loads(macro_path.read_text(encoding="utf-8"))
            lines.extend([
                "",
                f"## {next_section}. 거시 시나리오 (자동)",
                "",
                f"- **{macro.get('label', '—')}** ({macro.get('scenario_id', '')})",
                f"- {macro.get('ops_hint', '')}",
                f"- drivers: {', '.join(macro.get('drivers', [])[:5])}",
            ])
            next_section += 1

        write_research_checklist(data_dir, output_dir)
        rc_path = output_dir / "research_checklist.md"
        if rc_path.exists():
            lines.extend([f"", f"## {next_section}. Research Checklist", ""])
            lines.append(rc_path.read_text(encoding="utf-8").strip())

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text("\n".join(lines), encoding="utf-8")


