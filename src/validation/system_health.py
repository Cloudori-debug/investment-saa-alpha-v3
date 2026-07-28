from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from src.data_loader import load_market_indicators, load_positions, load_target_portfolio
from src.data_refresh.fundamentals_validate import validate_fundamentals
from src.models import MarketIndicators

CheckStatus = Literal["pass", "warn", "fail", "skip"]

# Compass Tier1 — economic_phase.py / regime_engine.py 에서 실제 사용
COMPASS_TIER1_USED = {
    "kospi": "성장·리스크 (200MA·drawdown)",
    "kospi_recent_high": "성장·리스크 (drawdown)",
    "kospi_200ma": "성장·리스크 (200MA)",
    "sp500": "성장·리스크 (글로벌 drawdown)",
    "sp500_recent_high": "성장·리스크 (S&P drawdown)",
    "vix": "유동성·리스크·레짐·금 safe-haven",
    "usdkrw": "인플레이션",
    "korea_10y": "인플레이션·유동성",
    "oil_brent": "인플레이션",
    "gold": "인플레·유동성·리스크 (safe-haven)",
    "foreign_flow_3d": "성장·리스크",
    "regime": "수동 레짐 override (TAA)",
}
COMPASS_TIER1_UNUSED: dict[str, str] = {}

TIER2_FIELDS = [
    "pmi_kr", "pmi_us", "cpi_kr_yoy", "cpi_us_yoy",
    "yield_spread_2y10y", "hy_oas_bp", "real_rate_kr",
]

ALPHA_PRICE_FIELDS = [
    "close", "market_cap", "trading_value_20d", "trading_value_60d",
    "return_1m", "return_3m", "return_6m", "return_12m",
    "high_52w", "distance_from_52w_high", "volatility_60d",
]

REQUIRED_INPUT_FILES = [
    "market_indicators.csv",
    "positions.csv",
    "target_portfolio.csv",
    "compass_rules.yaml",
    "saa_profiles.yaml",
    "portfolio_policy.yaml",
    "trigger_rules.yaml",
]

ALPHA_INPUT_FILES = [
    "universe.csv",
    "fundamentals.csv",
    "prices.csv",
    "universe_filter.yaml",
    "alpha_scoring.yaml",
]

EXPECTED_OUTPUT_FILES = [
    "compass_regime.json",
    "target_asset_allocation.csv",
    "current_vs_target.csv",
    "trade_actions.csv",
    "alpha_candidates.csv",
    "gpt_context.json",
    "decision_log.jsonl",
]


@dataclass
class HealthCheck:
    module: str
    name: str
    status: CheckStatus
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealthReport:
    as_of: str
    overall: CheckStatus
    checks: list[HealthCheck] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.1",
            "as_of": self.as_of,
            "overall": self.overall,
            "summary": self.summary,
            "meta": self.meta,
            "checks": [
                {
                    "module": c.module,
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


def _overall_status(checks: list[HealthCheck]) -> CheckStatus:
    from src.operational_gate import operational_overall_status

    return operational_overall_status(checks)  # type: ignore[return-value]


def _health_report_meta(checks: list[HealthCheck]) -> dict[str, Any]:
    from src.operational_gate import CRITICAL_HEALTH_NAMES, restricted_modes_from_checks

    critical_fails = [c.name for c in checks if c.status == "fail" and c.name in CRITICAL_HEALTH_NAMES]
    non_critical_fails = [c.name for c in checks if c.status == "fail" and c.name not in CRITICAL_HEALTH_NAMES]
    return {
        "restricted_modes": restricted_modes_from_checks(checks),
        "critical_fail_checks": critical_fails,
        "non_critical_fail_checks": non_critical_fails,
        "reason": (
            "non-critical failures present"
            if non_critical_fails and not critical_fails
            else "critical execution data failure" if critical_fails else ""
        ),
    }


def _field_zero_or_missing(market: MarketIndicators, field: str) -> bool:
    val = getattr(market, field, None)
    if field == "foreign_flow_3d":
        return not str(val or "").strip()
    if field == "regime":
        return not str(val or "").strip()
    try:
        return float(val or 0) <= 0
    except (TypeError, ValueError):
        return True


def _check_input_files(data_dir: Path) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    for name in REQUIRED_INPUT_FILES:
        path = data_dir / name
        checks.append(HealthCheck(
            module="input",
            name=name,
            status="pass" if path.exists() else "fail",
            message="존재" if path.exists() else "필수 파일 없음",
        ))
    for name in ALPHA_INPUT_FILES:
        path = data_dir / name
        checks.append(HealthCheck(
            module="alpha_input",
            name=name,
            status="pass" if path.exists() else "warn",
            message="존재" if path.exists() else "Alpha 실행 불가",
        ))
    return checks


def _check_market_indicators(data_dir: Path) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    path = data_dir / "market_indicators.csv"
    if not path.exists():
        return checks
    try:
        market = load_market_indicators(path)
    except Exception as exc:
        checks.append(HealthCheck(
            module="compass_tier1",
            name="market_indicators_load",
            status="fail",
            message=str(exc),
        ))
        return checks

    missing_used: list[str] = []
    zero_used: list[str] = []
    for fld, desc in COMPASS_TIER1_USED.items():
        if fld in ("foreign_flow_3d", "regime"):
            if _field_zero_or_missing(market, fld):
                missing_used.append(f"{fld}({desc})")
        elif _field_zero_or_missing(market, fld):
            zero_used.append(f"{fld}({desc})")

    unused_zero: list[str] = []
    for fld, desc in COMPASS_TIER1_UNUSED.items():
        if _field_zero_or_missing(market, fld):
            unused_zero.append(f"{fld}({desc})")

    status: CheckStatus = "pass"
    if missing_used or zero_used:
        status = "warn" if not missing_used else "fail"
    checks.append(HealthCheck(
        module="compass_tier1",
        name="tier1_fields",
        status=status,
        message=f"date={market.date}, regime={market.regime}",
        detail={
            "used_fields_ok": len(zero_used) == 0 and len(missing_used) == 0,
            "zero_or_missing_used": zero_used + missing_used,
            "zero_unused_optional": unused_zero,
            "field_usage": COMPASS_TIER1_USED,
        },
    ))

    if market.regime:
        checks.append(HealthCheck(
            module="compass_tier1",
            name="manual_regime_input",
            status="pass",
            message=f"수동 regime={market.regime} (CSV 입력)",
            detail={"note": "산출 레짐과 다르면 override 적용 — outputs/compass_regime.json 참고"},
        ))
    return checks


def _check_tier2(data_dir: Path) -> list[HealthCheck]:
    path = data_dir / "macro_tier2.csv"
    if not path.exists():
        return [HealthCheck(
            module="compass_tier2",
            name="macro_tier2.csv",
            status="skip",
            message="Tier2 미사용 (Tier1만)",
        )]
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        return [HealthCheck(
            module="compass_tier2",
            name="macro_tier2.csv",
            status="warn",
            message="파일 비어 있음",
        )]
    row = df.iloc[-1].to_dict()
    missing = [f for f in TIER2_FIELDS if not str(row.get(f, "")).strip()]
    filled = len(TIER2_FIELDS) - len(missing)
    checks = [HealthCheck(
        module="compass_tier2",
        name="tier2_fields",
        status="pass" if filled >= 4 else "warn",
        message=f"{filled}/{len(TIER2_FIELDS)} 필드 입력",
        detail={"missing": missing, "as_of": row.get("date", "")},
    )]

    prov_path = data_dir / "tier2_provenance.json"
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            fields = prov.get("fields") or {}
            stale = [
                name for name, meta in fields.items()
                if isinstance(meta, dict) and (
                    str(meta.get("status") or "") == "stale"
                    or (
                        str(meta.get("status") or "") != "fresh"
                        and int(meta.get("stale_business_days", 0))
                        > int(meta.get("threshold_days", 45))
                    )
                )
            ]
            fallback = [
                name for name, meta in fields.items()
                if isinstance(meta, dict) and meta.get("fallback_used")
            ]
            status: CheckStatus = "pass"
            msg = f"API provenance {len(fields)}필드"
            if fallback and len(fallback) >= 3:
                status = "warn"
                msg += f" · fallback {len(fallback)}"
            if stale:
                status = "warn" if status == "pass" else status
                msg += f" · stale {len(stale)}"
            checks.append(HealthCheck(
                module="compass_tier2",
                name="tier2_provenance",
                status=status,
                message=msg,
                detail={"stale_fields": stale, "fallback_fields": fallback, "as_of": prov.get("as_of")},
            ))
        except (json.JSONDecodeError, OSError):
            checks.append(HealthCheck(
                module="compass_tier2",
                name="tier2_provenance",
                status="warn",
                message="tier2_provenance.json 파싱 실패",
            ))
    else:
        checks.append(HealthCheck(
            module="compass_tier2",
            name="tier2_provenance",
            status="warn",
            message="tier2_provenance 없음 — API 갱신 미실행",
        ))
    return checks


def _kr_alpha_tickers_from_sources(data_dir: Path) -> tuple[set[str], set[str]]:
    """(목표 kr_alpha, 보유 kr_alpha) ticker 집합."""
    target_tickers: set[str] = set()
    holding_tickers: set[str] = set()

    def _kr(rows, bucket: set[str]) -> None:
        for row in rows:
            if getattr(row, "asset_group", "") == "kr_alpha" and row.ticker.upper() != "CASH":
                bucket.add(row.ticker.strip())

    if (data_dir / "positions.csv").exists():
        _kr(load_positions(data_dir / "positions.csv"), holding_tickers)
    for path in (data_dir / "target_portfolio.csv", data_dir.parent / "outputs" / "generated_target_portfolio.csv"):
        if path.exists():
            _kr(load_target_portfolio(path), target_tickers)
    return target_tickers, holding_tickers


def _check_alpha_coverage(data_dir: Path) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    u_path = data_dir / "universe.csv"
    if not u_path.exists():
        return checks

    universe = pd.read_csv(u_path, dtype=str, keep_default_na=False)
    tickers = set(universe["ticker"].astype(str).str.strip())
    real_tickers = {t for t in tickers if t.isdigit() and not t.startswith("999")}

    fund_path = data_dir / "fundamentals.csv"
    price_path = data_dir / "prices.csv"
    fund_have: set[str] = set()
    price_have: set[str] = set()

    if fund_path.exists():
        fund = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
        fund_have = set(fund["ticker"].astype(str).str.strip())
    if price_path.exists():
        prices = pd.read_csv(price_path, dtype=str, keep_default_na=False)
        price_have = set(prices["ticker"].astype(str).str.strip())

    missing_fund = sorted(real_tickers - fund_have)
    fund_pct = (len(real_tickers - set(missing_fund)) / len(real_tickers) * 100) if real_tickers else 0

    target_kr, holding_kr = _kr_alpha_tickers_from_sources(data_dir)
    required = target_kr | holding_kr
    missing_target = sorted(target_kr - price_have)
    missing_holding = sorted(holding_kr - price_have)
    missing_required = sorted(required - price_have)
    target_pct = (
        (len(target_kr) - len(missing_target)) / len(target_kr) * 100 if target_kr else 100.0
    )
    req_pct = (
        (len(required) - len(missing_required)) / len(required) * 100 if required else 100.0
    )
    breadth_pct = (len(price_have) / len(real_tickers) * 100) if real_tickers else 0

    fv = validate_fundamentals(data_dir)
    checks.append(HealthCheck(
        module="alpha",
        name="fundamentals_coverage",
        status="pass" if fund_pct >= 80 and not fv.errors else "warn" if fund_pct >= 50 else "fail",
        message=f"재무 {fund_pct:.0f}% ({len(real_tickers) - len(missing_fund)}/{len(real_tickers)})",
        detail={"missing_tickers": missing_fund[:20], "validate_errors": fv.errors[:5]},
    ))
    if not target_kr:
        price_status: CheckStatus = "pass"
    elif target_pct >= 80:
        price_status = "pass" if not missing_holding else "warn"
    elif target_pct >= 50:
        price_status = "warn"
    else:
        price_status = "fail"
    checks.append(HealthCheck(
        module="alpha",
        name="prices_coverage",
        status=price_status,
        message=(
            f"kr_alpha 목표 시세 {target_pct:.0f}% ({len(target_kr) - len(missing_target)}/{len(target_kr)})"
            + (f" · 보유 미커버 {len(missing_holding)}종" if missing_holding else "")
        ),
        detail={
            "missing_target_tickers": missing_target[:20],
            "missing_holding_tickers": missing_holding[:20],
            "all_kr_alpha_coverage_pct": round(req_pct, 1),
        },
    ))
    checks.append(HealthCheck(
        module="alpha",
        name="universe_prices_breadth",
        status="pass" if breadth_pct >= 30 else "warn",
        message=f"유니버스 시세 확보 {breadth_pct:.0f}% ({len(price_have)}/{len(real_tickers)})",
        detail={"note": "liquid scope 수집 시 낮을 수 있음 — 운용필수 시세와 별도"},
    ))

    if fund_path.exists():
        df = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
        core = ["roe", "per", "pbr", "usable_from_date"]
        scope_tickers = required if required else set()
        scoped = (
            df[df["ticker"].astype(str).str.strip().isin(scope_tickers)]
            if scope_tickers
            else df.iloc[0:0]
        )
        stale = 0
        missing_ops: list[str] = []
        for _, row in scoped.iterrows():
            if not str(row.get("roe", "")).strip() or not str(row.get("usable_from_date", "")).strip():
                stale += 1
                missing_ops.append(str(row.get("ticker", "")).strip())
        universe_stale = 0
        if scope_tickers:
            for _, row in df.iterrows():
                t = str(row.get("ticker", "")).strip()
                if t in scope_tickers:
                    continue
                if not str(row.get("roe", "")).strip() or not str(row.get("usable_from_date", "")).strip():
                    universe_stale += 1
        msg = (
            f"운용 kr_alpha ROE/usable_from_date 결측 {stale}건"
            if scope_tickers
            else f"ROE/usable_from_date 결측 {stale}건"
        )
        if universe_stale:
            msg += f" (유니버스 전체 {universe_stale}건 — 운용 범위 외)"
        checks.append(HealthCheck(
            module="alpha",
            name="fundamentals_quality",
            status="pass" if stale == 0 else "warn",
            message=msg,
            detail={
                "required_columns": core,
                "operational_tickers": sorted(scope_tickers),
                "missing_operational": missing_ops[:20],
                "universe_stale_count": universe_stale,
            },
        ))
    return checks


def _check_price_coverage_gates(data_dir: Path, output_dir: Path | None, as_of: str) -> list[HealthCheck]:
    from src.validation.tier_a_price_coverage import (
        evaluate_tier_a_price_coverage,
        evaluate_tier_b_refresh_health,
        write_price_coverage_reports,
    )

    result = evaluate_tier_a_price_coverage(data_dir, output_dir, as_of)
    if output_dir is not None:
        write_price_coverage_reports(result, data_dir, output_dir)

    core = result.core
    alpha = result.alpha
    checks = [
        HealthCheck(
            module="alpha",
            name="core_price_gate",
            status=core.status,
            message=(
                f"held {core.held_coverage:.0%} · target {core.target_coverage:.0%} · "
                f"trade {core.trade_actions_coverage:.0%}"
                + (f" — {core.reasons[0]}" if core.reasons else "")
            ),
            detail=core.to_dict(),
        ),
        HealthCheck(
            module="alpha",
            name="alpha_price_gate",
            status=alpha.status,
            message=(
                f"top30 {alpha.alpha_top30_coverage:.0%} · top50 {alpha.alpha_top50_coverage:.0%} · "
                f"action={alpha.action}"
                + (f" — {alpha.reasons[0]}" if alpha.reasons else "")
            ),
            detail=alpha.to_dict(),
        ),
    ]

    tb_status, tb_msg, tb_detail = evaluate_tier_b_refresh_health(data_dir, as_of)
    checks.append(HealthCheck(
        module="alpha",
        name="tier_b_refresh",
        status=tb_status,
        message=tb_msg,
        detail=tb_detail,
    ))
    return checks


def _check_portfolio_inputs(data_dir: Path, output_dir: Path | None = None) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    try:
        positions = load_positions(data_dir / "positions.csv")
        targets = load_target_portfolio(data_dir / "target_portfolio.csv")
        pos_val = sum(p.current_value for p in positions)
        tgt_sum = sum(t.target_weight for t in targets)
        checks.append(HealthCheck(
            module="portfolio",
            name="positions",
            status="pass" if positions and pos_val > 0 else "fail",
            message=f"{len(positions)}종목, 평가합 {pos_val:,.0f}",
        ))
        checks.append(HealthCheck(
            module="portfolio",
            name="target_weights",
            status="pass" if abs(tgt_sum - 100) < 0.01 else "fail",
            message=f"target 합 {tgt_sum:.2f}%",
        ))
    except Exception as exc:
        checks.append(HealthCheck(
            module="portfolio",
            name="load",
            status="fail",
            message=str(exc),
        ))

    from src.alpha.target_portfolio_guard import check_unapproved_target_overwrite, evaluate_target_guard

    out_dir = output_dir if output_dir is not None else data_dir.parent / "outputs"
    guard_detail = evaluate_target_guard(data_dir, out_dir)
    guard_status = str(guard_detail.get("status", "pass"))
    guard_messages = check_unapproved_target_overwrite(data_dir, out_dir)
    message = guard_messages[0] if guard_messages else (
        f"target_portfolio_guard {guard_detail.get('severity', 'PASS')} — "
        f"changed_rows={guard_detail.get('changed_rows', 0)}"
    )
    checks.append(HealthCheck(
        module="portfolio",
        name="target_portfolio_guard",
        status=guard_status,  # type: ignore[arg-type]
        message=message,
        detail=guard_detail,
    ))
    return checks


def _check_outputs(data_dir: Path, output_dir: Path) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    for name in EXPECTED_OUTPUT_FILES:
        path = output_dir / name
        checks.append(HealthCheck(
            module="output",
            name=name,
            status="pass" if path.exists() else "warn",
            message="생성됨" if path.exists() else "미생성 — 전체 분석 실행 필요",
        ))

    regime_path = output_dir / "compass_regime.json"
    if regime_path.exists():
        from src.validation.regime_override_divergence import assess_regime_divergence_from_outputs

        data = json.loads(regime_path.read_text(encoding="utf-8"))
        override = data.get("override") or {}
        assessment = assess_regime_divergence_from_outputs(data_dir, output_dir)
        if assessment is None:
            status = "fail"
            message = f"산출={data.get('computed_regime')} 적용={data.get('applied_regime')}"
            divergence_detail: dict[str, Any] = {}
        elif not data.get("computed_regime"):
            status = "fail"
            message = f"산출={data.get('computed_regime')} 적용={data.get('applied_regime')}"
            divergence_detail = assessment.detail
        else:
            status = assessment.status
            message = assessment.message
            divergence_detail = assessment.detail
        checks.append(HealthCheck(
            module="compass_output",
            name="regime_computed",
            status=status,  # type: ignore[arg-type]
            message=message,
            detail={
                "override_active": override.get("active"),
                "tier2_used": data.get("tier2_used"),
                "execution_level": data.get("execution_level"),
                "divergence": divergence_detail,
            },
        ))

    gpt_path = output_dir / "gpt_context.json"
    if gpt_path.exists():
        gpt = json.loads(gpt_path.read_text(encoding="utf-8"))
        checks.append(HealthCheck(
            module="alpha_output",
            name="gpt_context",
            status="pass" if gpt.get("top_candidates") else "warn",
            message=f"후보 {len(gpt.get('top_candidates', []))} · data_gate={gpt.get('data_gate')}",
            detail={"excluded_summary": gpt.get("excluded_summary", {})},
        ))

    log_path = output_dir / "decision_log.jsonl"
    if log_path.exists():
        last = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        entry = json.loads(last)
        checks.append(HealthCheck(
            module="execution",
            name="decision_log",
            status="pass",
            message=f"data_gate={entry.get('data_gate')} exec_level={entry.get('execution_level')} actions={entry.get('action_count')}",
            detail=entry,
        ))
        pg = entry.get("portfolio_gate", entry.get("data_gate"))
        ag = entry.get("alpha_gate")
        hg = entry.get("health_gate", "GREEN")
        merged = entry.get("data_gate")
        if ag is not None and pg is not None:
            from src.operational_gate import resolve_operational_gate

            expected = resolve_operational_gate(str(pg), str(ag), str(hg))
            detail = {
                "expected": expected,
                "portfolio_gate": pg,
                "alpha_gate": ag,
                "health_gate": hg,
            }
            if entry.get("data_gate_detail"):
                detail["data_gate_detail"] = entry["data_gate_detail"]
            checks.append(HealthCheck(
                module="execution",
                name="data_gate_merged",
                status="pass" if merged == expected else "warn",
                message=f"통합={merged} (portfolio={pg}, alpha={ag}, health={hg})",
                detail=detail,
            ))
        elif gpt_path.exists():
            gpt = json.loads(gpt_path.read_text(encoding="utf-8"))
            ag = gpt.get("data_gate")
            if pg and ag and pg != ag:
                checks.append(HealthCheck(
                    module="execution",
                    name="data_gate_note",
                    status="warn",
                    message=f"portfolio={pg} alpha={ag} — merge_alpha_gate 설정 확인",
                    detail={"portfolio_gate": pg, "alpha_gate": ag},
                ))
    return checks


def run_input_health_checks(data_dir: Path, *, as_of: str | None = None, output_dir: Path | None = None) -> SystemHealthReport:
    """입력·커버리지만 검증 (파이프라인 중 게이트 산출용)."""
    out_dir = output_dir if output_dir is not None else data_dir.parent / "outputs"
    checks: list[HealthCheck] = []
    checks.extend(_check_input_files(data_dir))
    checks.extend(_check_market_indicators(data_dir))
    checks.extend(_check_tier2(data_dir))
    checks.extend(_check_alpha_coverage(data_dir))
    checks.extend(_check_portfolio_inputs(data_dir, out_dir))

    resolved_as_of = as_of
    if not resolved_as_of:
        mi = data_dir / "market_indicators.csv"
        if mi.exists():
            try:
                resolved_as_of = load_market_indicators(mi).date
            except ValueError:
                pass
    if not resolved_as_of:
        resolved_as_of = datetime.now().strftime("%Y-%m-%d")

    checks.extend(_check_price_coverage_gates(data_dir, out_dir, resolved_as_of))

    summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for c in checks:
        summary[c.status] = summary.get(c.status, 0) + 1

    return SystemHealthReport(
        as_of=resolved_as_of,
        overall=_overall_status(checks),
        checks=checks,
        summary=summary,
        meta=_health_report_meta(checks),
    )


def run_system_health(
    data_dir: Path,
    output_dir: Path | None = None,
    *,
    as_of: str | None = None,
) -> SystemHealthReport:
    """필수 입력·커버리지·출력 산출물을 모듈별로 검증."""
    output_dir = output_dir or data_dir.parent / "outputs"
    checks: list[HealthCheck] = []
    checks.extend(_check_input_files(data_dir))
    checks.extend(_check_market_indicators(data_dir))
    checks.extend(_check_tier2(data_dir))
    checks.extend(_check_alpha_coverage(data_dir))
    checks.extend(_check_portfolio_inputs(data_dir, output_dir))

    resolved_as_of = as_of
    if not resolved_as_of:
        mi = data_dir / "market_indicators.csv"
        if mi.exists():
            try:
                resolved_as_of = load_market_indicators(mi).date
            except ValueError:
                pass
    if not resolved_as_of:
        resolved_as_of = datetime.now().strftime("%Y-%m-%d")

    checks.extend(_check_price_coverage_gates(data_dir, output_dir, resolved_as_of))
    if output_dir.exists():
        checks.extend(_check_outputs(data_dir, output_dir))

    summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for c in checks:
        summary[c.status] = summary.get(c.status, 0) + 1

    return SystemHealthReport(
        as_of=resolved_as_of,
        overall=_overall_status(checks),
        checks=checks,
        summary=summary,
        meta=_health_report_meta(checks),
    )


def write_health_report(report: SystemHealthReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
