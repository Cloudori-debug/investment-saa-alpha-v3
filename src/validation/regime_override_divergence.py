"""레짐 오버라이드 격차(divergence) — 표시/경고만. 오버라이드 자동 해제 없음."""


from __future__ import annotations


import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


from src.compass.models import RiskRegime
from src.config import load_yaml


# RISK_ON(0) < YELLOW_STABLE(1) < CAUTION(2) < RISK_OFF(3) < CRISIS(4)
REGIME_SEVERITY: dict[str, int] = {
    RiskRegime.RISK_ON.value: 0,
    RiskRegime.YELLOW_STABLE.value: 1,
    RiskRegime.CAUTION.value: 2,
    RiskRegime.RISK_OFF.value: 3,
    RiskRegime.CRISIS.value: 4,
}


DEFAULT_WARN_GAP = 2
DEFAULT_ESCALATION_DAYS = 3
DEFAULT_REVIEW_BUFFER_DAYS = 2
REGIME_DIVERGENCE_LOG = "regime_divergence_log.jsonl"




def regime_severity(regime: str | RiskRegime | None) -> int | None:
    if regime is None:
        return None
    key = regime.value if isinstance(regime, RiskRegime) else str(regime).strip().upper()
    if key not in REGIME_SEVERITY:
        return None
    return REGIME_SEVERITY[key]




def regime_override_gap(
    computed_regime: str | RiskRegime | None,
    applied_regime: str | RiskRegime | None,
) -> int | None:
    """severity(computed) - severity(applied). 양수 = 오버라이드가 리스크를 완화한 방향."""
    c = regime_severity(computed_regime)
    a = regime_severity(applied_regime)
    if c is None or a is None:
        return None
    return c - a




def _compass_rules_path(rules_path: Path | None) -> Path:
    return rules_path or (Path(__file__).resolve().parents[2] / "data" / "compass_rules.yaml")




def _load_regime_rules(rules_path: Path | None = None) -> dict[str, Any]:
    path = _compass_rules_path(rules_path)
    if not path.exists():
        return {}
    rules = load_yaml(path)
    return rules.get("regime_rules") or {}




def load_override_divergence_warn_gap(rules_path: Path | None = None) -> int:
    return int(_load_regime_rules(rules_path).get("override_divergence_warn_gap", DEFAULT_WARN_GAP))




def load_override_divergence_escalation_days(rules_path: Path | None = None) -> int:
    return int(
        _load_regime_rules(rules_path).get(
            "override_divergence_escalation_days",
            DEFAULT_ESCALATION_DAYS,
        )
    )




def load_override_divergence_review_buffer_days(rules_path: Path | None = None) -> int:
    return int(
        _load_regime_rules(rules_path).get(
            "override_divergence_review_buffer_days",
            DEFAULT_REVIEW_BUFFER_DAYS,
        )
    )




def regime_divergence_log_path(output_dir: Path) -> Path:
    return output_dir / REGIME_DIVERGENCE_LOG




def _parse_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip()[:10]




def _log_dates(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    dates: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = _parse_iso_date(row.get("date"))
        if d:
            dates.add(d)
    return dates




def append_regime_divergence_log(
    output_dir: Path,
    *,
    date: str,
    computed_regime: str | None,
    applied_regime: str | None,
    gap: int | None,
    override_active: bool,
) -> Path | None:
    """일별 격차 스냅샷 append.

    동일 date:
    - 내용이 완전히 같으면 스킵 (중복 방지).
    - 사람 재분류 등으로 값이 바뀌면 당일 행만 upsert (과거 소급 아님).
    """
    as_of = _parse_iso_date(date)
    if not as_of:
        return None
    path = regime_divergence_log_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "schema_version": "1.0",
        "date": as_of,
        "computed_regime": computed_regime,
        "applied_regime": applied_regime,
        "gap": gap,
        "override_active": bool(override_active),
    }

    if not path.exists():
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path

    lines = path.read_text(encoding="utf-8").splitlines()
    rewritten: list[str] = []
    found = False
    unchanged = False
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            rewritten.append(line)
            continue
        if _parse_iso_date(row.get("date")) != as_of:
            rewritten.append(line)
            continue
        found = True
        same = (
            row.get("computed_regime") == entry["computed_regime"]
            and row.get("applied_regime") == entry["applied_regime"]
            and row.get("gap") == entry["gap"]
            and bool(row.get("override_active")) == entry["override_active"]
        )
        if same:
            unchanged = True
            rewritten.append(line)
        else:
            rewritten.append(json.dumps(entry, ensure_ascii=False))
    if not found:
        rewritten.append(json.dumps(entry, ensure_ascii=False))
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return None if (found and unchanged) else path


def _load_log_entries(log_path: Path, *, as_of: str | None = None) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    cutoff = _parse_iso_date(as_of)
    entries: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = _parse_iso_date(row.get("date"))
        if not d:
            continue
        if cutoff and d > cutoff:
            continue
        entries.append({**row, "date": d})
    by_date: dict[str, dict[str, Any]] = {}
    for row in entries:
        by_date[str(row["date"])] = row
    return sorted(by_date.values(), key=lambda r: str(r["date"]), reverse=True)


def count_consecutive_divergence_days(
    log_path: Path,
    *,
    warn_gap: int,
    as_of: str,
) -> int:
    """최신 날짜부터 역순 — override_active and gap>=warn_gap 연속 일수.

    applied_regime이 바뀌면 에피소드를 끊는다(사람 재분류 시 카운트 리셋).
    """
    entries = _load_log_entries(log_path, as_of=as_of)
    count = 0
    prev_applied: str | None = None
    for row in entries:
        try:
            gap = row.get("gap")
            gap_val = int(gap) if gap is not None else None
        except (TypeError, ValueError):
            gap_val = None
        active = bool(row.get("override_active"))
        applied = str(row.get("applied_regime") or "")
        if not (active and gap_val is not None and gap_val >= int(warn_gap)):
            break
        if prev_applied is not None and applied != prev_applied:
            break
        prev_applied = applied
        count += 1
    return count


@dataclass(frozen=True)
class RegimeDivergenceAssessment:
    gap: int | None
    computed_regime: str | None
    applied_regime: str | None
    override_active: bool
    warn: bool
    status: str  # pass | warn
    message: str
    detail: dict[str, Any]
    consecutive_days: int = 0
    escalated: bool = False
    recommended_review_by: str | None = None




def assess_regime_override_divergence(
    *,
    computed_regime: str | None,
    applied_regime: str | None,
    override_active: bool = False,
    override_reason: str | None = None,
    regime_set_date: str | None = None,
    warn_gap: int | None = None,
) -> RegimeDivergenceAssessment:
    """격차 평가. warn_gap 이상은 warn — 오버라이드를 바꾸지 않음."""
    threshold = DEFAULT_WARN_GAP if warn_gap is None else int(warn_gap)
    gap = regime_override_gap(computed_regime, applied_regime)
    detail: dict[str, Any] = {
        "computed_regime": computed_regime,
        "applied_regime": applied_regime,
        "gap": gap,
        "warn_gap_threshold": threshold,
        "override_active": override_active,
        "regime_override_reason": override_reason,
        "regime_set_date": regime_set_date,
        "note": (
            "산출값과 적용값의 격차가 크면 재확인이 필요하다는 보조 경고이며, "
            "오버라이드가 틀렸다는 뜻이 아니며 자동 해제하지 않는다."
        ),
    }


    if not computed_regime or not applied_regime:
        return RegimeDivergenceAssessment(
            gap=gap,
            computed_regime=computed_regime,
            applied_regime=applied_regime,
            override_active=override_active,
            warn=False,
            status="pass",
            message=f"산출={computed_regime} 적용={applied_regime}",
            detail=detail,
        )


    if gap is None:
        return RegimeDivergenceAssessment(
            gap=None,
            computed_regime=computed_regime,
            applied_regime=applied_regime,
            override_active=override_active,
            warn=False,
            status="pass",
            message=f"산출={computed_regime} 적용={applied_regime} (서수 미매핑)",
            detail=detail,
        )


    # 양수 gap(완화 방향) + 임계 이상만 warn. 동일·1단계·강화 방향은 정보성.
    if override_active and gap >= threshold:
        msg = (
            f"레짐 오버라이드 격차 gap={gap} "
            f"(산출={computed_regime} → 적용={applied_regime})"
        )
        if override_reason:
            msg += f" · 근거={override_reason}"
        if regime_set_date:
            msg += f" · 설정일={regime_set_date}"
        msg += " — 재확인 권고(자동 해제 없음)"
        return RegimeDivergenceAssessment(
            gap=gap,
            computed_regime=computed_regime,
            applied_regime=applied_regime,
            override_active=override_active,
            warn=True,
            status="warn",
            message=msg,
            detail=detail,
        )


    base = f"산출={computed_regime} 적용={applied_regime}"
    if gap == 0:
        message = base
    elif gap > 0:
        message = f"{base} (완화 gap={gap}, 정보)"
    else:
        message = f"{base} (강화 gap={gap}, 정보)"


    return RegimeDivergenceAssessment(
        gap=gap,
        computed_regime=computed_regime,
        applied_regime=applied_regime,
        override_active=override_active,
        warn=False,
        status="pass",
        message=message,
        detail=detail,
    )




def _recommended_review_by(as_of: str, buffer_days: int) -> str:
    base = datetime.strptime(_parse_iso_date(as_of) or as_of, "%Y-%m-%d")
    return (base + timedelta(days=int(buffer_days))).strftime("%Y-%m-%d")




def assess_regime_divergence_with_persistence(
    output_dir: Path,
    *,
    computed_regime: str | None,
    applied_regime: str | None,
    override_active: bool = False,
    override_reason: str | None = None,
    regime_set_date: str | None = None,
    as_of: str,
    warn_gap: int | None = None,
) -> RegimeDivergenceAssessment:
    """AC-05b + 지속일 에스컬레이션. 로그는 오늘부터 정직하게 쌓음(소급 채우기 없음)."""
    threshold = load_override_divergence_warn_gap() if warn_gap is None else int(warn_gap)
    base = assess_regime_override_divergence(
        computed_regime=computed_regime,
        applied_regime=applied_regime,
        override_active=override_active,
        override_reason=override_reason,
        regime_set_date=regime_set_date,
        warn_gap=threshold,
    )
    as_of_date = _parse_iso_date(as_of)
    if not as_of_date:
        return base


    append_regime_divergence_log(
        output_dir,
        date=as_of_date,
        computed_regime=base.computed_regime,
        applied_regime=base.applied_regime,
        gap=base.gap,
        override_active=override_active,
    )


    log_path = regime_divergence_log_path(output_dir)
    consecutive = count_consecutive_divergence_days(
        log_path,
        warn_gap=threshold,
        as_of=as_of_date,
    )
    escalation_days = load_override_divergence_escalation_days()
    buffer_days = load_override_divergence_review_buffer_days()


    detail = {
        **base.detail,
        "consecutive_divergence_days": consecutive,
        "escalation_threshold_days": escalation_days,
        "review_buffer_days": buffer_days,
        "divergence_log": str(log_path.name),
    }


    if not base.warn:
        return replace(base, consecutive_days=consecutive, detail=detail)


    if consecutive < escalation_days:
        return replace(
            base,
            consecutive_days=consecutive,
            detail=detail,
        )


    review_by = _recommended_review_by(as_of_date, buffer_days)
    msg = (
        f"{base.message} · {consecutive}일째 지속 — "
        f"{review_by} 전 재확인 권고(만료일과 별도, 자동 해제 없음)"
    )
    detail.update(
        {
            "escalated": True,
            "recommended_review_by": review_by,
        }
    )
    return replace(
        base,
        message=msg,
        detail=detail,
        consecutive_days=consecutive,
        escalated=True,
        recommended_review_by=review_by,
    )




def assess_regime_divergence_from_outputs(
    data_dir: Path,
    output_dir: Path,
) -> RegimeDivergenceAssessment | None:
    """compass_regime.json + market_indicators 기반 통합 평가."""
    regime_path = output_dir / "compass_regime.json"
    if not regime_path.exists():
        return None


    reg = json.loads(regime_path.read_text(encoding="utf-8"))
    override = reg.get("override") or {}
    override_active = bool(override.get("active"))
    computed = reg.get("computed_regime")
    applied = reg.get("applied_regime")


    reason = override.get("reason")
    set_date = None
    as_of = ""
    mi_path = data_dir / "market_indicators.csv"
    if mi_path.exists():
        from src.data_loader import load_market_indicators


        market = load_market_indicators(mi_path)
        reason = (market.regime_override_reason or "").strip() or reason
        set_date = getattr(market, "regime_set_date", None)
        as_of = str(market.date or "")[:10]


    if not as_of:
        as_of = str(reg.get("as_of") or "")[:10]
    if not as_of:
        return assess_regime_override_divergence(
            computed_regime=str(computed) if computed else None,
            applied_regime=str(applied) if applied else None,
            override_active=override_active,
            override_reason=str(reason) if reason else None,
            regime_set_date=str(set_date) if set_date else None,
            warn_gap=load_override_divergence_warn_gap(),
        )


    return assess_regime_divergence_with_persistence(
        output_dir,
        computed_regime=str(computed) if computed else None,
        applied_regime=str(applied) if applied else None,
        override_active=override_active,
        override_reason=str(reason) if reason else None,
        regime_set_date=str(set_date) if set_date else None,
        as_of=as_of,
        warn_gap=load_override_divergence_warn_gap(),
    )


# --- 조건부 조기 재검토 (설정일 대비 낙폭 악화/회복) — 경고만 ---

DEFAULT_WORSENING_DD_DELTA = -5.0
DEFAULT_RECOVERY_DD_THRESHOLD = -15.0
DEFAULT_AGE_WARN_DAYS = 5
DEFAULT_AGE_ESCALATION_DAYS = 15


def load_override_age_warn_days(rules_path: Path | None = None) -> int:
    return int(_load_regime_rules(rules_path).get("override_age_warn_days", DEFAULT_AGE_WARN_DAYS))


def load_override_age_escalation_days(rules_path: Path | None = None) -> int:
    return int(
        _load_regime_rules(rules_path).get(
            "override_age_escalation_days",
            DEFAULT_AGE_ESCALATION_DAYS,
        )
    )


def load_early_review_worsening_dd_delta(rules_path: Path | None = None) -> float:
    return float(
        _load_regime_rules(rules_path).get(
            "early_review_worsening_dd_delta_pct",
            DEFAULT_WORSENING_DD_DELTA,
        )
    )


def load_early_review_recovery_dd_threshold(rules_path: Path | None = None) -> float:
    rules = _load_regime_rules(rules_path)
    if "early_review_recovery_dd_threshold" in rules:
        return float(rules["early_review_recovery_dd_threshold"])
    return float(rules.get("crisis_kospi_drawdown", DEFAULT_RECOVERY_DD_THRESHOLD))


def kospi_drawdown_pct(kospi: float | None, kospi_recent_high: float | None) -> float | None:
    try:
        k = float(kospi) if kospi is not None else 0.0
        h = float(kospi_recent_high) if kospi_recent_high is not None else 0.0
    except (TypeError, ValueError):
        return None
    if k <= 0 or h <= 0:
        return None
    return round((k / h - 1.0) * 100.0, 4)


def drawdown_on_or_before(data_dir: Path, as_of: str) -> float | None:
    """market_indicators_history / market_indicators에서 as_of 이하 최근 낙폭."""
    cutoff = str(as_of)[:10]
    for name in ("market_indicators_history.csv", "market_indicators.csv"):
        path = data_dir / name
        if not path.exists():
            continue
        import pandas as pd

        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        if df.empty or "date" not in df.columns:
            continue
        rows = [r for r in df.to_dict(orient="records") if str(r.get("date", ""))[:10] <= cutoff]
        if not rows:
            continue
        rows.sort(key=lambda r: str(r.get("date", ""))[:10])
        last = rows[-1]
        dd = kospi_drawdown_pct(last.get("kospi"), last.get("kospi_recent_high"))
        if dd is not None:
            return dd
    return None


@dataclass(frozen=True)
class EarlyRegimeReviewAssessment:
    status: str  # pass | warn | info
    message: str
    detail: dict[str, Any]
    trigger: str | None = None  # worsening | recovery | None


def assess_early_regime_review(
    *,
    override_active: bool,
    regime_set_date: str | None,
    current_drawdown_pct: float | None,
    set_date_drawdown_pct: float | None = None,
    worsening_delta_pct: float | None = None,
    recovery_threshold_pct: float | None = None,
) -> EarlyRegimeReviewAssessment:
    """설정일 대비 낙폭 악화/회복 — 알림만. override/cap 변경 없음."""
    worsen = (
        DEFAULT_WORSENING_DD_DELTA if worsening_delta_pct is None else float(worsening_delta_pct)
    )
    recover = (
        DEFAULT_RECOVERY_DD_THRESHOLD
        if recovery_threshold_pct is None
        else float(recovery_threshold_pct)
    )
    detail: dict[str, Any] = {
        "override_active": override_active,
        "regime_set_date": regime_set_date,
        "current_drawdown_pct": current_drawdown_pct,
        "set_date_drawdown_pct": set_date_drawdown_pct,
        "worsening_delta_threshold": worsen,
        "recovery_threshold": recover,
        "note": "조건부 재검토 알림만 — override/policy_cap 자동 변경 없음",
    }
    if not override_active or not regime_set_date:
        return EarlyRegimeReviewAssessment(
            status="pass",
            message="조기 재검토 트리거 해당 없음",
            detail=detail,
        )
    if current_drawdown_pct is None:
        return EarlyRegimeReviewAssessment(
            status="pass",
            message="조기 재검토 — 현재 낙폭 불가",
            detail=detail,
        )

    if set_date_drawdown_pct is not None:
        delta = float(current_drawdown_pct) - float(set_date_drawdown_pct)
        detail["drawdown_delta_pct"] = round(delta, 4)
        if delta <= worsen:
            msg = (
                f"오버라이드 설정 이후 KOSPI 낙폭 추가 악화 "
                f"(설정일 {set_date_drawdown_pct:.1f}% → 현재 {current_drawdown_pct:.1f}%, "
                f"Δ{delta:.1f}%p) — 즉시 재검토 권고(자동 변경 없음)"
            )
            return EarlyRegimeReviewAssessment(
                status="warn",
                message=msg,
                detail=detail,
                trigger="worsening",
            )

    if float(current_drawdown_pct) > recover:
        msg = (
            f"KOSPI 낙폭 {current_drawdown_pct:.1f}% — crisis 임계({recover:.1f}%) 상회(개선). "
            f"완화 검토 후보(자동 완화 아님 · 사람 갱신 필요)"
        )
        return EarlyRegimeReviewAssessment(
            status="info",
            message=msg,
            detail=detail,
            trigger="recovery",
        )

    return EarlyRegimeReviewAssessment(
        status="pass",
        message=f"조기 재검토 트리거 미충족 (현재 낙폭 {current_drawdown_pct:.1f}%)",
        detail=detail,
    )


def assess_early_regime_review_from_data(
    data_dir: Path,
    *,
    override_active: bool,
    regime_set_date: str | None,
    kospi: float | None,
    kospi_recent_high: float | None,
) -> EarlyRegimeReviewAssessment:
    current = kospi_drawdown_pct(kospi, kospi_recent_high)
    set_dd = drawdown_on_or_before(data_dir, regime_set_date) if regime_set_date else None
    return assess_early_regime_review(
        override_active=override_active,
        regime_set_date=regime_set_date,
        current_drawdown_pct=current,
        set_date_drawdown_pct=set_dd,
        worsening_delta_pct=load_early_review_worsening_dd_delta(),
        recovery_threshold_pct=load_early_review_recovery_dd_threshold(),
    )

