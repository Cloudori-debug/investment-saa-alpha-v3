from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from src.execution_scope import ExecutionScope
from src.models import MarketIndicators

OperationalApproval = Literal["GREEN", "YELLOW", "RED"]
ExpiryStatus = Literal["NONE", "ACTIVE", "EXPIRED_REVIEW_REQUIRED"]

_POLICY_MAX_SCOPE: dict[str, ExecutionScope] = {
    "YELLOW_STABLE": "ETF_ONLY",
    "CAUTION": "ETF_ONLY",
    "RISK_OFF": "NO_TRADE",
    "CRISIS": "NO_TRADE",
    "RED": "NO_TRADE",
}

_SCOPE_RANK: dict[str, int] = {
    "NO_TRADE": 0,
    "ETF_ONLY": 1,
    "ETF_ONLY_ALPHA_REVIEW": 2,
    "ETF_AND_BETA": 3,
    "FULL_WITH_ALPHA": 4,
}

EXPIRY_ACTION = "REQUIRE_MANUAL_REVIEW"


def _scope_min(a: str, b: str) -> str:
    ra = _SCOPE_RANK.get(a, 0)
    rb = _SCOPE_RANK.get(b, 0)
    return a if ra <= rb else b


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _manual_regime_state(market: MarketIndicators) -> tuple[str | None, bool, str | None]:
    """(regime_raw, is_expired, expires_date) — 만료여도 regime은 유지."""
    raw = (market.regime or "").strip()
    if not raw or raw.upper() in {"NEUTRAL", "AUTO", ""}:
        return None, False, None
    expires = getattr(market, "regime_expires_date", None)
    as_dt = _parse_date(market.date)
    exp_dt = _parse_date(expires)
    expired = bool(exp_dt and as_dt and as_dt > exp_dt)
    return raw, expired, expires


def _normalize_regime_key(regime: str) -> str:
    upper = regime.upper()
    for key in _POLICY_MAX_SCOPE:
        if key in upper:
            return key
    return upper


def _days_to_expiry(market: MarketIndicators, expires: str | None) -> int | None:
    as_dt = _parse_date(market.date)
    exp_dt = _parse_date(expires)
    if not as_dt or not exp_dt:
        return None
    return (exp_dt - as_dt).days


def derive_technical_system_status(
    *,
    data_gate: str,
    health_gate: str,
    portfolio_gate: str,
    technical_scope: str,
) -> OperationalApproval:
    if data_gate == "RED" or health_gate == "RED" or portfolio_gate == "RED":
        return "RED"
    if (
        data_gate == "GREEN"
        and health_gate == "GREEN"
        and portfolio_gate == "GREEN"
        and technical_scope in {"FULL_WITH_ALPHA", "ETF_AND_BETA"}
    ):
        return "GREEN"
    return "YELLOW"


@dataclass
class PolicyCapResult:
    active: bool
    cap_regime: str | None
    cap_source: str
    cap_reason: str | None
    regime_expires_date: str | None
    fsr_reference: str | None
    max_execution_scope: str | None
    max_operational_approval: OperationalApproval
    technical_execution_scope: str
    capped_execution_scope: str
    technical_data_gate: str
    technical_health_gate: str
    expiry_action: str
    expiry_status: ExpiryStatus
    days_to_expiry: int | None
    is_expired: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "cap_regime": self.cap_regime,
            "cap_source": self.cap_source,
            "cap_reason": self.cap_reason,
            "regime_expires_date": self.regime_expires_date,
            "fsr_reference": self.fsr_reference,
            "max_execution_scope": self.max_execution_scope,
            "max_operational_approval": self.max_operational_approval,
            "technical_execution_scope": self.technical_execution_scope,
            "capped_execution_scope": self.capped_execution_scope,
            "expiry_action": self.expiry_action,
            "expiry_status": self.expiry_status,
            "days_to_expiry": self.days_to_expiry,
            "is_expired": self.is_expired,
            "technical_status": {
                "data_gate": self.technical_data_gate,
                "health_gate": self.technical_health_gate,
                "execution_scope": self.technical_execution_scope,
                "note": "게이트만 반영 — policy cap 적용 전",
            },
        }


def resolve_policy_cap(
    market: MarketIndicators,
    *,
    technical_scope: str,
    data_gate: str,
    health_gate: str,
    computed_regime: str | None = None,
) -> PolicyCapResult:
    """수동 레짐 기반 캡.

    만료 시(`is_expired`)에는 regime_engine과 같이 **컴퓨티드 레짐**으로
    cap_regime / max_execution_scope를 재계산한다. override 자동 해제 아님 —
    캡 전제만 만료 폴백과 일치시킴.
    """
    manual, is_expired, expires = _manual_regime_state(market)
    reason = getattr(market, "regime_override_reason", None) or ""
    days_left = _days_to_expiry(market, expires)

    fsr_ref = None
    if "FSR" in reason.upper() or "금융안정" in reason or "BOK FSR" in reason:
        fsr_ref = reason.strip()[:240] if reason else None

    inactive = PolicyCapResult(
        active=False,
        cap_regime=None,
        cap_source="none",
        cap_reason=None,
        regime_expires_date=expires,
        fsr_reference=fsr_ref,
        max_execution_scope=None,
        max_operational_approval="GREEN",
        technical_execution_scope=technical_scope,
        capped_execution_scope=technical_scope,
        technical_data_gate=data_gate,
        technical_health_gate=health_gate,
        expiry_action=EXPIRY_ACTION,
        expiry_status="NONE",
        days_to_expiry=days_left,
        is_expired=False,
    )

    if not manual:
        return inactive

    # 만료 시: 수동값 대신 컴퓨티드 레짐으로 캡 계산 (regime_engine 폴백과 정합)
    if is_expired and computed_regime and str(computed_regime).strip():
        regime_for_cap = str(computed_regime).strip()
        cap_source = "computed_after_manual_expiry"
        cap_reason = (
            f"manual_expired({manual}) → computed({regime_for_cap}); "
            f"{(reason or 'manual expired').strip()}"
        )[:240]
    else:
        regime_for_cap = manual
        cap_source = "manual_regime"
        cap_reason = reason or None

    regime_key = _normalize_regime_key(regime_for_cap)
    max_scope = _POLICY_MAX_SCOPE.get(regime_key)
    if max_scope is None:
        return PolicyCapResult(
            active=False,
            cap_regime=regime_for_cap,
            cap_source=cap_source,
            cap_reason=cap_reason,
            regime_expires_date=expires,
            fsr_reference=fsr_ref,
            max_execution_scope=None,
            max_operational_approval="GREEN",
            technical_execution_scope=technical_scope,
            capped_execution_scope=technical_scope,
            technical_data_gate=data_gate,
            technical_health_gate=health_gate,
            expiry_action=EXPIRY_ACTION,
            expiry_status="ACTIVE" if not is_expired else "EXPIRED_REVIEW_REQUIRED",
            days_to_expiry=days_left,
            is_expired=is_expired,
        )

    capped = _scope_min(technical_scope, max_scope)
    max_approval: OperationalApproval = "YELLOW"
    if regime_key in {"CRISIS", "RED", "RISK_OFF"}:
        max_approval = "RED"

    expiry_status: ExpiryStatus = "EXPIRED_REVIEW_REQUIRED" if is_expired else "ACTIVE"

    return PolicyCapResult(
        active=True,
        cap_regime=regime_for_cap if is_expired and computed_regime else manual,
        cap_source=cap_source,
        cap_reason=cap_reason,
        regime_expires_date=expires,
        fsr_reference=fsr_ref,
        max_execution_scope=max_scope,
        max_operational_approval=max_approval,
        technical_execution_scope=technical_scope,
        capped_execution_scope=capped,
        technical_data_gate=data_gate,
        technical_health_gate=health_gate,
        expiry_action=EXPIRY_ACTION,
        expiry_status=expiry_status,
        days_to_expiry=days_left,
        is_expired=is_expired,
    )


def apply_policy_cap_to_approval(
    overall: OperationalApproval,
    policy_cap: PolicyCapResult,
) -> OperationalApproval:
    if not policy_cap.active:
        return overall
    rank = {"RED": 0, "YELLOW": 1, "GREEN": 2}
    cap = policy_cap.max_operational_approval
    capped = overall if rank[overall] <= rank[cap] else cap
    if policy_cap.is_expired and capped == "GREEN":
        return "YELLOW"
    return capped


def build_technical_status_block(
    *,
    data_gate: str,
    health_gate: str,
    portfolio_gate: str,
    alpha_gate: str | None,
    execution_scope: str,
) -> dict[str, Any]:
    tech_status = derive_technical_system_status(
        data_gate=data_gate,
        health_gate=health_gate,
        portfolio_gate=portfolio_gate,
        technical_scope=execution_scope,
    )
    return {
        "system_status": tech_status,
        "data_gate": data_gate,
        "health_gate": health_gate,
        "portfolio_gate": portfolio_gate,
        "alpha_gate": alpha_gate or "GREEN",
        "execution_scope": execution_scope,
        "note": "게이트·dry-run 기준 — policy cap 적용 전 기술 상태",
    }


def fsr_policy_permissions(cap_regime: str | None) -> dict[str, str]:
    """YELLOW_STABLE / CAUTION 캡 시 세분화 권한 (_POLICY_MAX_SCOPE ETF_ONLY 축과 정합)."""
    if not cap_regime:
        return {}
    key = _normalize_regime_key(str(cap_regime))
    if key in {"YELLOW_STABLE", "CAUTION"}:
        return {
            "etf_new_buy": "REVIEW_ONLY",
            "etf_chase_buy": "BLOCKED",
            "etf_rebalance": "REVIEW_ONLY",
            "etf_risk_reduce": "ALLOWED",
            "kr_alpha_new_buy": "BLOCKED",
            "kr_alpha_replace": "BLOCKED",
            "kr_alpha_trim": "ALLOWED",
        }
    return {}
