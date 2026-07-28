from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src.data_refresh.external_market import business_days_between
from src.execution_scope import derive_alpha_approval, derive_execution_scope
from src.operational_gate import CRITICAL_HEALTH_NAMES
from src.validation.system_health import run_system_health

CheckStatus = Literal["pass", "warn", "fail"]
ExecutionScope = Literal["NO_TRADE", "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "ETF_AND_BETA", "FULL_WITH_ALPHA"]
AlphaApproval = Literal["APPROVED", "RESTRICTED", "BLOCKED"]

# Alpha-only AC — FAIL이어도 Overall RED로 격상하지 않음
ALPHA_ONLY_IDS = frozenset({"AC-04", "AC-07"})
# Critical — 하나라도 fail이면 Overall RED + NO_TRADE
CRITICAL_IDS = frozenset({"AC-01", "AC-02", "AC-03", "AC-05", "AC-06"})


@dataclass
class AcceptanceItem:
    id: str
    name: str
    status: CheckStatus
    message: str
    scope: Literal["core", "alpha", "ops"] = "core"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class AcceptanceReport:
    as_of: str
    overall: Literal["GREEN", "YELLOW", "RED"]
    execution_scope: ExecutionScope
    alpha_approval: AlphaApproval
    operational_verdict: str
    items: list[AcceptanceItem] = field(default_factory=list)
    dry_run_days: int = 0
    run_id: str | None = None
    technical_overall: Literal["GREEN", "YELLOW", "RED"] | None = None
    operational_overall: Literal["GREEN", "YELLOW", "RED"] | None = None
    policy_cap_applied: bool = False
    policy_cap_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": "1.1",
            "as_of": self.as_of,
            "overall": self.overall,
            "technical_overall": self.technical_overall or self.overall,
            "operational_overall": self.operational_overall or self.overall,
            "policy_cap_applied": self.policy_cap_applied,
            "policy_cap_reason": self.policy_cap_reason,
            "execution_scope": self.execution_scope,
            "alpha_approval": self.alpha_approval,
            "operational_verdict": self.operational_verdict,
            "dry_run_days": self.dry_run_days,
            "run_id": self.run_id,
            "items": [
                {
                    "id": i.id,
                    "name": i.name,
                    "status": i.status,
                    "scope": i.scope,
                    "message": i.message,
                    "detail": i.detail,
                }
                for i in self.items
            ],
        }
        return out


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _load_decision_log(output_dir: Path) -> dict | None:
    path = output_dir / "decision_log.jsonl"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1]) if lines else None


def _load_run_manifest(output_dir: Path) -> dict | None:
    path = output_dir / "run_manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _check_regime_override(data_dir: Path, output_dir: Path, as_of: str) -> AcceptanceItem:
    from src.data_loader import load_market_indicators
    from src.validation.regime_override_divergence import (
        load_override_age_escalation_days,
        load_override_age_warn_days,
    )

    mi_path = data_dir / "market_indicators.csv"
    if not mi_path.exists():
        return AcceptanceItem("AC-05", "manual_regime", "pass", "market_indicators 없음", scope="core")

    market = load_market_indicators(mi_path)
    regime_path = output_dir / "compass_regime.json"
    override_active = False
    if regime_path.exists():
        reg = json.loads(regime_path.read_text(encoding="utf-8"))
        override_active = bool((reg.get("override") or {}).get("active"))

    expires = getattr(market, "regime_expires_date", None)
    reason = (market.regime_override_reason or "").strip()
    set_date = getattr(market, "regime_set_date", None)
    manual = market.regime.upper() not in ("", "NEUTRAL", "AUTO")

    if not override_active and not manual:
        return AcceptanceItem("AC-05", "manual_regime", "pass", "수동 override 없음", scope="core")

    as_dt = _parse_date(as_of)
    exp_dt = _parse_date(expires)
    set_dt = _parse_date(set_date)

    if exp_dt and as_dt and as_dt > exp_dt and override_active:
        return AcceptanceItem(
            "AC-05", "manual_regime", "fail",
            f"만료({expires}) 후 override仍 적용",
            scope="core",
            detail={"regime": market.regime},
        )

    if manual and override_active and not reason:
        return AcceptanceItem("AC-05", "manual_regime", "fail", "regime_override_reason 필수", scope="core")

    if set_dt and as_dt:
        age = business_days_between(set_date or "", as_of)
        warn_days = load_override_age_warn_days()
        esc_days = load_override_age_escalation_days()
        if age > esc_days:
            return AcceptanceItem(
                "AC-05", "manual_regime", "warn",
                f"override {age}영업일 경과 — 장기 미검토, 재검토 시급(자동 해제 없음)",
                scope="core",
                detail={
                    "set_date": set_date,
                    "age_business_days": age,
                    "escalation_threshold_days": esc_days,
                    "escalated": True,
                },
            )
        if age > warn_days:
            return AcceptanceItem(
                "AC-05", "manual_regime", "warn",
                f"override {age}영업일 경과 — 갱신 또는 만료 설정 권장",
                scope="core",
                detail={"set_date": set_date, "age_business_days": age},
            )

    if exp_dt and as_dt and 0 < (exp_dt - as_dt).days <= 2:
        return AcceptanceItem(
            "AC-05", "manual_regime", "warn",
            f"만료 {(exp_dt - as_dt).days}일 전",
            scope="core",
        )

    if manual and override_active:
        return AcceptanceItem(
            "AC-05", "manual_regime", "pass",
            f"유효 override ({market.regime})",
            scope="core",
            detail={"reason": reason, "expires": expires},
        )
    return AcceptanceItem("AC-05", "manual_regime", "pass", "override 정책 충족", scope="core")


def _check_regime_early_review(data_dir: Path, output_dir: Path) -> AcceptanceItem:
    """AC-05c — 설정일 대비 낙폭 악화/회복 조기 재검토 알림. 자동 완화·해제 없음."""
    from src.data_loader import load_market_indicators
    from src.validation.regime_override_divergence import assess_early_regime_review_from_data

    mi_path = data_dir / "market_indicators.csv"
    if not mi_path.exists():
        return AcceptanceItem(
            "AC-05c", "regime_early_review", "pass", "market_indicators 없음", scope="core",
        )

    market = load_market_indicators(mi_path)
    override_active = False
    regime_path = output_dir / "compass_regime.json"
    if regime_path.exists():
        override_active = bool(
            (json.loads(regime_path.read_text(encoding="utf-8")).get("override") or {}).get("active")
        )
    set_date = getattr(market, "regime_set_date", None)
    assessment = assess_early_regime_review_from_data(
        data_dir,
        override_active=override_active,
        regime_set_date=str(set_date) if set_date else None,
        kospi=getattr(market, "kospi", None),
        kospi_recent_high=getattr(market, "kospi_recent_high", None),
    )
    # AcceptanceItem은 pass|warn|fail만 — info는 pass + detail로 표시
    status: CheckStatus = "warn" if assessment.status == "warn" else "pass"
    return AcceptanceItem(
        "AC-05c",
        "regime_early_review",
        status,
        assessment.message,
        scope="core",
        detail={**assessment.detail, "level": assessment.status, "trigger": assessment.trigger},
    )


def _check_regime_override_divergence(data_dir: Path, output_dir: Path) -> AcceptanceItem:
    """AC-05b — 산출 vs 적용 레짐 격차(크기). 시간 기반 AC-05와 분리. 자동 해제 없음."""
    from src.validation.regime_override_divergence import assess_regime_divergence_from_outputs

    assessment = assess_regime_divergence_from_outputs(data_dir, output_dir)
    if assessment is None:
        return AcceptanceItem(
            "AC-05b",
            "regime_override_divergence",
            "pass",
            "compass_regime.json 없음",
            scope="core",
        )

    return AcceptanceItem(
        "AC-05b",
        "regime_override_divergence",
        assessment.status,  # type: ignore[arg-type]
        assessment.message,
        scope="core",
        detail=assessment.detail,
    )


def _check_provenance(data_dir: Path) -> AcceptanceItem:
    from src.data_provenance import audit_market_data_consistency

    audit = audit_market_data_consistency(data_dir)
    path = data_dir / "market_data_provenance.json"
    if not path.exists():
        return AcceptanceItem(
            "AC-06", "external_data_stale", "fail",
            "provenance 없음 — 시장 지표 갱신 필요",
            scope="core",
            detail=audit,
        )
    prov = json.loads(path.read_text(encoding="utf-8"))
    fields = prov.get("fields") or {}
    if not fields:
        return AcceptanceItem("AC-06", "external_data_stale", "fail", "provenance 비어 있음", scope="core", detail=audit)

    max_stale = max(int(m.get("stale_business_days", 99)) for m in fields.values())
    stale_list = [k for k, m in fields.items() if int(m.get("stale_business_days", 99)) > 2]
    issues = audit.get("issues") or []

    if max_stale > 5:
        msg = f"stale>{max_stale}d: {', '.join(stale_list[:5])}"
        if issues:
            msg += f" · {issues[0]}"
        return AcceptanceItem(
            "AC-06", "external_data_stale", "fail",
            msg,
            scope="core",
            detail=audit,
        )
    if max_stale > 2 or issues:
        msg = f"stale 3~5d: {', '.join(stale_list)}" if max_stale > 2 else issues[0]
        return AcceptanceItem(
            "AC-06", "external_data_stale", "warn",
            msg,
            scope="core",
            detail=audit,
        )
    return AcceptanceItem("AC-06", "external_data_stale", "pass", f"max stale {max_stale}d", scope="core", detail=audit)


def _kospi_ma_pct_from_compass(output_dir: Path) -> float | None:
    path = output_dir / "compass_regime.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.get("score_breakdown") or []:
        if item.get("indicator") != "kospi_vs_200ma":
            continue
        detail = str(item.get("detail") or "")
        match = re.search(r"([+\-]?\d+\.?\d*)%", detail)
        if match:
            return float(match.group(1))
    return None


def _check_market_200ma_coherence(data_dir: Path, output_dir: Path) -> AcceptanceItem:
    from src.data_loader import load_market_indicators_bundle

    mi_path = data_dir / "market_indicators.csv"
    if not mi_path.exists():
        return AcceptanceItem(
            "AC-MKT-01", "kospi_200ma_coherence", "warn",
            "market_indicators.csv 없음", scope="core",
        )

    bundle = load_market_indicators_bundle(mi_path)
    export_pct = bundle.kospi_vs_200ma_pct
    compass_pct = _kospi_ma_pct_from_compass(output_dir)
    raw_pct = bundle.kospi_vs_200ma_pct_raw
    detail = {
        "export_normalized_pct": export_pct,
        "compass_breakdown_pct": compass_pct,
        "raw_csv_pct": raw_pct,
        "repair_applied": bundle.repair_applied,
        "repair_reason": bundle.repair_reason,
    }

    if export_pct is None:
        return AcceptanceItem(
            "AC-MKT-01", "kospi_200ma_coherence", "warn",
            "kospi_vs_200ma_pct 계산 불가", scope="core", detail=detail,
        )

    if compass_pct is not None and abs(export_pct - compass_pct) > 0.15:
        return AcceptanceItem(
            "AC-MKT-01", "kospi_200ma_coherence", "fail",
            f"export {export_pct:.1f}%p vs compass {compass_pct:.1f}%p 불일치",
            scope="core",
            detail=detail,
        )

    if bundle.repair_applied and not bundle.repair_reason:
        return AcceptanceItem(
            "AC-MKT-02", "kospi_200ma_repair_meta", "warn",
            "repair_applied without repair_reason", scope="core", detail=detail,
        )

    if raw_pct is not None and abs(raw_pct) > 35 and not bundle.repair_applied:
        return AcceptanceItem(
            "AC-MKT-03", "kospi_200ma_raw_outlier", "fail",
            f"raw CSV 200MA 비율 {raw_pct:.1f}%p — 보정 없음", scope="core", detail=detail,
        )

    if raw_pct is not None and abs(raw_pct) > 35 and bundle.repair_applied:
        msg = (
            f"raw {raw_pct:.1f}%p → normalized {export_pct:.1f}%p "
            f"({bundle.repair_reason})"
        )
        st: CheckStatus = "warn"
    elif compass_pct is not None:
        msg = f"export·compass 일치 ({export_pct:.1f}%p)"
        st = "pass"
    else:
        msg = f"normalized {export_pct:.1f}%p (compass breakdown 없음)"
        st = "pass"

    return AcceptanceItem(
        "AC-MKT-01", "kospi_200ma_coherence", st, msg, scope="core", detail=detail,
    )


def _check_fomc_calendar(data_dir: Path, as_of: str) -> AcceptanceItem:
    from src.config import load_trigger_rules

    rules = load_trigger_rules(data_dir / "trigger_rules.yaml")
    dates = rules.get("events", {}).get("fomc_dates") or []
    if not dates:
        return AcceptanceItem("AC-10", "fomc_calendar", "fail", "fomc_dates 비어 있음", scope="ops")

    as_dt = _parse_date(as_of) or datetime.now()
    future_90: list[str] = []
    past_only = True
    for d in dates:
        dt = _parse_date(str(d))
        if not dt:
            continue
        if dt >= as_dt and (dt - as_dt).days <= 90:
            future_90.append(str(d)[:10])
            past_only = False

    if future_90:
        return AcceptanceItem(
            "AC-10", "fomc_calendar", "pass",
            f"향후 90일 내 FOMC {len(future_90)}건",
            scope="ops",
            detail={"next_dates": sorted(future_90)[:3]},
        )
    if past_only and dates:
        return AcceptanceItem(
            "AC-10", "fomc_calendar", "warn",
            "과거 일정만 있음 — 향후 FOMC 날짜 갱신 필요",
            scope="ops",
        )
    return AcceptanceItem("AC-10", "fomc_calendar", "fail", "유효 FOMC 일정 없음", scope="ops")


def _check_ai_export(output_dir: Path) -> AcceptanceItem:
    manifest = _load_run_manifest(output_dir)
    bundle_path = output_dir / "ai_export_bundle.json"
    gpt_path = output_dir / "gpt_context.json"
    ac_path = output_dir / "acceptance_report.json"

    if bundle_path.exists() and manifest:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        manifest_rid = manifest.get("run_id")
        bundle_rid = bundle.get("run_id")
        if manifest_rid and bundle_rid == manifest_rid:
            detail = {}
            if not bundle.get("exposure_lookthrough"):
                detail["missing"] = "exposure_lookthrough"
                return AcceptanceItem(
                    "AC-08", "ai_export", "warn",
                    "bundle run_id 일치 · exposure_lookthrough 누락",
                    scope="ops",
                    detail=detail,
                )
            return AcceptanceItem("AC-08", "ai_export", "pass", "bundle run_id 일치", scope="ops")
        embedded = (bundle.get("acceptance") or {}).get("run_id")
        if manifest_rid and embedded == manifest_rid:
            return AcceptanceItem(
                "AC-08", "ai_export", "pass",
                "bundle acceptance run_id 일치 (export 시점 스냅샷)",
                scope="ops",
            )
        if ac_path.exists():
            ac = json.loads(ac_path.read_text(encoding="utf-8"))
            if ac.get("run_id") == manifest_rid:
                return AcceptanceItem(
                    "AC-08", "ai_export", "warn",
                    "bundle run_id 구버전 — 전체 분석 후 AI보내기 재생성 권장",
                    scope="ops",
                )
        return AcceptanceItem(
            "AC-08", "ai_export", "warn",
            "bundle 존재하나 run_id 불일치 — 번들 재생성",
            scope="ops",
        )
    if gpt_path.exists():
        return AcceptanceItem("AC-08", "ai_export", "warn", "gpt_context만 존재 — bundle+run_id 권장", scope="ops")
    return AcceptanceItem("AC-08", "ai_export", "fail", "AI export 없음", scope="ops")


def _count_dry_run_days(output_dir: Path) -> int:
    path = output_dir / "dry_run_log.jsonl"
    if not path.exists():
        return 0
    dates = set()
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        if line.strip():
            dates.add(json.loads(line).get("date", ""))
    return len(dates)


def _check_policy_cap_expiry(market, policy_cap) -> AcceptanceItem:
    if not policy_cap.active:
        return AcceptanceItem("AC-POLICY-EXPIRY", "policy_cap_expiry", "pass", "policy_cap 비활성", scope="ops")
    if policy_cap.expiry_status == "EXPIRED_REVIEW_REQUIRED":
        return AcceptanceItem(
            "AC-POLICY-EXPIRY", "policy_cap_expiry", "warn",
            f"policy_cap 만료({policy_cap.regime_expires_date}) — {policy_cap.expiry_action}, YELLOW 유지",
            scope="ops",
            detail={"expiry_status": policy_cap.expiry_status, "expiry_action": policy_cap.expiry_action},
        )
    days = policy_cap.days_to_expiry
    if days is not None and 0 < days <= 14:
        return AcceptanceItem(
            "AC-POLICY-EXPIRY", "policy_cap_expiry", "warn",
            f"policy_cap 만료 {days}일 전 — 수동 재검토 준비",
            scope="ops",
            detail={"days_to_expiry": days, "expires": policy_cap.regime_expires_date},
        )
    return AcceptanceItem(
        "AC-POLICY-EXPIRY", "policy_cap_expiry", "pass",
        f"policy_cap 유효 (만료 {policy_cap.regime_expires_date or '—'})",
        scope="ops",
    )


def _derive_overall_and_alpha(
    items: list[AcceptanceItem],
    pg: str,
    unified: str,
    ag: str | None,
    *,
    pipeline_scope: str | None = None,
) -> tuple[Literal["GREEN", "YELLOW", "RED"], ExecutionScope, AlphaApproval]:
    """Overall·scope·alpha — scope는 파이프라인 derive_execution_scope 우선."""
    by_id = {i.id: i for i in items}
    critical_fail = any(by_id.get(i, AcceptanceItem(i, "", "pass", "")).status == "fail" for i in CRITICAL_IDS)
    alpha_fail = any(
        by_id.get(i) and by_id[i].status == "fail" for i in ALPHA_ONLY_IDS
    )

    if critical_fail or pg == "RED" or unified == "RED":
        return "RED", "NO_TRADE", "BLOCKED"

    if ag == "RED" or alpha_fail:
        alpha: AlphaApproval = "BLOCKED"
    elif ag == "YELLOW":
        alpha = "RESTRICTED"
    else:
        alpha = "APPROVED"

    has_warn = any(i.status == "warn" for i in items)
    has_fail_non_critical = any(i.status == "fail" for i in items if i.id not in CRITICAL_IDS)

    if has_fail_non_critical or has_warn or unified == "YELLOW" or alpha != "APPROVED":
        overall: Literal["GREEN", "YELLOW", "RED"] = "YELLOW"
    else:
        overall = "GREEN"

    if pipeline_scope in {
        "NO_TRADE", "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "ETF_AND_BETA", "FULL_WITH_ALPHA"
    }:
        scope: ExecutionScope = pipeline_scope  # type: ignore[assignment]
    elif overall == "RED":
        scope = "NO_TRADE"
    elif alpha == "BLOCKED" or alpha == "RESTRICTED":
        scope = "ETF_ONLY"
    elif overall == "GREEN" and alpha == "APPROVED":
        scope = "FULL_WITH_ALPHA"
    else:
        scope = "ETF_AND_BETA" if pg == "GREEN" and unified == "GREEN" else "ETF_ONLY"

    alpha = derive_alpha_approval(ag, scope)
    return overall, scope, alpha


def run_acceptance_check(data_dir: Path, output_dir: Path) -> AcceptanceReport:
    health = run_system_health(data_dir, output_dir)
    as_of = health.as_of
    items: list[AcceptanceItem] = []

    critical_fails = [
        c for c in health.checks if c.status == "fail" and c.name in CRITICAL_HEALTH_NAMES
    ]
    total_fail = health.summary.get("fail", 0)
    items.append(AcceptanceItem(
        "AC-01", "system_health",
        "fail" if critical_fails else "pass",
        f"critical_fail={len(critical_fails)} total_fail={total_fail} warn={health.summary.get('warn', 0)}",
        scope="core",
        detail={"critical_names": [c.name for c in critical_fails]},
    ))
    core_price = next((c for c in health.checks if c.name == "core_price_gate"), None)
    if core_price is not None:
        cp_status: CheckStatus = "pass"
        if core_price.status == "fail":
            cp_status = "fail"
        elif core_price.status == "warn":
            cp_status = "warn"
        items.append(AcceptanceItem(
            "AC-01b", "core_price_gate",
            cp_status,
            core_price.message,
            scope="core",
            detail=core_price.detail,
        ))

    target_guard = next((c for c in health.checks if c.name == "target_portfolio_guard"), None)
    if target_guard is not None:
        tg_status: CheckStatus = "pass"
        if target_guard.status == "fail":
            tg_status = "fail"
        elif target_guard.status == "warn":
            tg_status = "warn"
        items.append(AcceptanceItem(
            "AC-01c", "target_portfolio_guard",
            tg_status,
            target_guard.message,
            scope="core",
            detail=target_guard.detail,
        ))

    log = _load_decision_log(output_dir) or {}
    unified = str(log.get("data_gate", "RED"))
    pg = str(log.get("portfolio_gate", unified))
    ag = log.get("alpha_gate")
    pipeline_scope = log.get("execution_scope")

    from src.validation.gate_detail_builders import (
        build_portfolio_gate_detail,
        build_unified_data_gate_detail,
    )

    unified_detail = build_unified_data_gate_detail(
        gate=unified,
        log=log,
        health=health,
        output_dir=output_dir,
        data_dir=data_dir,
    )
    portfolio_detail = build_portfolio_gate_detail(
        gate=pg,
        log=log,
        health=health,
        output_dir=output_dir,
        data_dir=data_dir,
    )

    for ac_id, name, gate_val, scope, detail in [
        ("AC-02", "unified_data_gate", unified, "core", unified_detail),
        ("AC-03", "portfolio_gate", pg, "core", portfolio_detail),
    ]:
        if gate_val == "RED":
            st: CheckStatus = "fail"
        elif gate_val == "YELLOW":
            st = "warn"
        elif gate_val == "GREEN":
            st = "pass"
        else:
            st = "warn"
        items.append(AcceptanceItem(ac_id, name, st, f"gate={gate_val}", scope=scope, detail=detail))

    from src.validation.alpha_gate_diagnostics import build_ac04_alpha_gate_detail

    ag_str = str(ag or "—")
    alpha_detail = build_ac04_alpha_gate_detail(ag_str, data_dir=data_dir, output_dir=output_dir)
    if ag_str == "RED":
        ag_st: CheckStatus = "fail"
    elif ag_str == "YELLOW":
        ag_st = "warn"
    elif ag_str == "GREEN":
        ag_st = "pass"
    else:
        ag_st = "warn"
    items.append(AcceptanceItem("AC-04", "alpha_gate", ag_st, f"gate={ag_str}", scope="alpha", detail=alpha_detail))

    items.append(_check_regime_override(data_dir, output_dir, as_of))
    items.append(_check_regime_override_divergence(data_dir, output_dir))
    items.append(_check_regime_early_review(data_dir, output_dir))
    items.append(_check_provenance(data_dir))
    items.append(_check_market_200ma_coherence(data_dir, output_dir))

    for c in health.checks:
        if c.name == "fundamentals_coverage":
            st = "pass" if c.status == "pass" else "warn" if c.status == "warn" else "fail"
            items.append(AcceptanceItem("AC-07", "alpha_coverage", st, c.message, scope="alpha"))
            break

    items.append(_check_ai_export(output_dir))

    dry_days = _count_dry_run_days(output_dir)
    if dry_days >= 10:
        items.append(AcceptanceItem("AC-09", "dry_run_days", "pass", f"{dry_days} 영업일", scope="ops"))
    elif dry_days >= 5:
        items.append(AcceptanceItem("AC-09", "dry_run_days", "warn", f"{dry_days}/10", scope="ops"))
    else:
        items.append(AcceptanceItem("AC-09", "dry_run_days", "warn", f"{dry_days}/10 진행 중", scope="ops"))

    items.append(_check_fomc_calendar(data_dir, as_of))

    overall, scope, alpha = _derive_overall_and_alpha(
        items, pg, unified, str(ag) if ag else None, pipeline_scope=pipeline_scope,
    )
    manifest = _load_run_manifest(output_dir)

    from src.data_loader import load_market_indicators
    from src.policy_cap import apply_policy_cap_to_approval, resolve_policy_cap

    mi_path = data_dir / "market_indicators.csv"
    market_for_cap = load_market_indicators(mi_path) if mi_path.exists() else None
    technical_scope_str = str(log.get("technical_execution_scope") or pipeline_scope or "ETF_ONLY")
    computed_for_cap = None
    regime_path = output_dir / "compass_regime.json"
    if regime_path.exists():
        try:
            computed_for_cap = json.loads(regime_path.read_text(encoding="utf-8")).get("computed_regime")
        except Exception:
            computed_for_cap = None
    if market_for_cap is not None:
        policy_cap = resolve_policy_cap(
            market_for_cap,
            technical_scope=technical_scope_str,
            data_gate=unified,
            health_gate=str(log.get("health_gate", "GREEN")),
            computed_regime=str(computed_for_cap) if computed_for_cap else None,
        )
    else:
        from src.models import MarketIndicators as MI
        policy_cap = resolve_policy_cap(
            MI(date=as_of, regime=""),
            technical_scope=technical_scope_str,
            data_gate=unified,
            health_gate=str(log.get("health_gate", "GREEN")),
            computed_regime=str(computed_for_cap) if computed_for_cap else None,
        )

    technical_overall = overall
    overall = apply_policy_cap_to_approval(overall, policy_cap)
    operational_overall = overall

    items.append(_check_policy_cap_expiry(market_for_cap, policy_cap) if market_for_cap else AcceptanceItem(
        "AC-POLICY-EXPIRY", "policy_cap_expiry", "pass", "market_indicators 없음", scope="ops",
    ))

    if dry_days < 10 and overall == "GREEN":
        overall = "YELLOW"

    if overall == "RED":
        verdict = "Overall RED · Execution Scope NO_TRADE — Critical FAIL 또는 core gate RED"
    elif scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW"}:
        verdict = (
            "Overall YELLOW · Scope ETF_ONLY — ETF·자산군 리밸런싱 검토 가능. "
            "kr_alpha 신규매수·교체 실행 금지 (Review-only). 자동매매 금지."
        )
        if scope == "ETF_ONLY_ALPHA_REVIEW":
            verdict = (
                "Overall YELLOW · Scope ETF_ONLY_ALPHA_REVIEW — data GREEN·dry-run 미완. "
                "ETF만 제한 실행, kr_alpha는 Review-only. 자동매매 금지."
            )
    elif overall == "GREEN" and scope == "FULL_WITH_ALPHA":
        verdict = "Overall GREEN · Alpha 포함 검토 가능 (사람 승인 필수). 자동매매 금지."
    else:
        verdict = "Overall YELLOW · 제한 운용. 자동매매 금지."

    if dry_days < 10:
        verdict += f" dry-run {dry_days}/10 — 실운용 승인 전."
    if policy_cap.active:
        verdict += (
            f" Policy cap: {policy_cap.cap_regime} — "
            f"technical scope {policy_cap.technical_execution_scope} → "
            f"{policy_cap.capped_execution_scope}."
        )
        if technical_overall != operational_overall:
            verdict += f" Technical {technical_overall} → operational {operational_overall}."

    return AcceptanceReport(
        as_of=as_of,
        overall=overall,
        technical_overall=technical_overall,
        operational_overall=operational_overall,
        policy_cap_applied=policy_cap.active,
        policy_cap_reason=policy_cap.cap_reason,
        execution_scope=scope,
        alpha_approval=alpha,
        operational_verdict=verdict,
        items=items,
        dry_run_days=dry_days,
        run_id=manifest.get("run_id") if manifest else None,
    )


def write_acceptance_report(report: AcceptanceReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
