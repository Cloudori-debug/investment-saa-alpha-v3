from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.compass.models import GroupGapRow
from src.execution_permissions import infer_trim_reason
from src.models import TradeAction
from src.operating_state import OperatingStateBundle

GROUP_GAP_SOURCE_COMPASS = "compass_allocation"
GROUP_GAP_SOURCE_TICKER = "ticker_target_aggregate"


@dataclass
class FinalExecutionDecision:
    run_id: str | None
    as_of: str
    system_status: Literal["GREEN", "YELLOW", "RED"]
    data_gate: str
    execution_scope: str
    alpha_approval: str
    alpha_execution_status: str
    group_gap_source: str
    operational_verdict: str
    dry_run_days: int
    allowed_actions: list[dict[str, Any]] = field(default_factory=list)
    blocked_actions: list[dict[str, Any]] = field(default_factory=list)
    final_trade_list: list[dict[str, Any]] = field(default_factory=list)
    group_gaps: list[dict[str, Any]] = field(default_factory=list)
    data_gate_detail: dict[str, Any] | None = None
    market_data_audit: dict[str, Any] | None = None
    execution_permissions: dict[str, Any] | None = None
    policy_cap: dict[str, Any] | None = None
    technical_status: dict[str, Any] | None = None
    operating: OperatingStateBundle | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": "1.0",
            "authoritative": True,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "run_id": self.run_id,
            "as_of": self.as_of,
            "system_status": self.system_status,
            "data_gate": self.data_gate,
            "execution_scope": self.execution_scope,
            "alpha_approval": self.alpha_approval,
            "alpha_execution_status": self.alpha_execution_status,
            "group_gap_source": self.group_gap_source,
            "operational_verdict": self.operational_verdict,
            "dry_run_days": self.dry_run_days,
            "references_note": (
                "최종 권위 출력. trade_actions·portfolio_actions·holdings_review·"
                "alpha_candidates는 참고자료 — 충돌 시 본 파일 우선."
            ),
            "allowed_actions": self.allowed_actions,
            "blocked_actions": self.blocked_actions,
            "final_trade_list": self.final_trade_list,
            "group_gaps": self.group_gaps,
        }
        if self.data_gate_detail:
            out["data_gate_detail"] = self.data_gate_detail
        if self.market_data_audit:
            out["market_data_audit"] = self.market_data_audit
        if self.execution_permissions:
            out["execution_permissions"] = self.execution_permissions
        if self.policy_cap:
            out["policy_cap"] = self.policy_cap
        if self.technical_status:
            out["technical_status"] = self.technical_status
        if self.operating:
            out.update(self.operating.to_dict())
        return out


_EXECUTABLE_ACTIONS = frozenset({
    "Buy-allowed", "Add", "Hold", "Park", "Wait", "Trim",
})
_BLOCKED_ACTIONS = frozenset({
    "Review-only", "No trade", "Stop-buy", "Risk defense", "Replace",
})


def build_final_execution_decision(
    *,
    run_id: str | None,
    as_of: str,
    system_status: Literal["GREEN", "YELLOW", "RED"],
    data_gate: str,
    execution_scope: str,
    alpha_approval: str,
    alpha_execution_status: str,
    group_gap_source: str,
    operational_verdict: str,
    dry_run_days: int,
    executable_actions: list[TradeAction],
    review_actions: list[TradeAction],
    group_gaps: list[GroupGapRow] | None = None,
    data_gate_detail: dict[str, Any] | None = None,
    market_data_audit: dict[str, Any] | None = None,
    execution_permissions: dict[str, Any] | None = None,
    policy_cap: dict[str, Any] | None = None,
    technical_status: dict[str, Any] | None = None,
    operating: OperatingStateBundle | None = None,
) -> FinalExecutionDecision:
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    final_trades: list[dict[str, Any]] = []

    for act in executable_actions:
        if act.ticker == "PORTFOLIO":
            continue
        row = {
            "ticker": act.ticker,
            "name": act.name,
            "action": act.action,
            "allowed_size_pct": act.allowed_size_pct,
            "reason": act.reason,
            "priority": act.priority,
        }
        trim_reason = infer_trim_reason(act.action, act.reason)
        if trim_reason:
            row["trim_reason"] = trim_reason
        if act.action in _EXECUTABLE_ACTIONS and act.action not in {"Wait", "Hold", "Park"}:
            final_trades.append(row)
        if act.action in _EXECUTABLE_ACTIONS:
            allowed.append(row)
        elif act.action in _BLOCKED_ACTIONS or act.action == "Review-only":
            blocked.append({**row, "block_reason": act.reason})

    for act in review_actions:
        blocked.append({
            "ticker": act.ticker,
            "name": act.name,
            "action": act.action,
            "theoretical": True,
            "block_reason": act.reason,
            "priority": act.priority,
        })

    gap_rows = [
        {
            "asset_group": g.asset_group,
            "current": g.current,
            "target": g.target,
            "gap": g.gap,
            "action": g.action,
            "reason": g.reason,
        }
        for g in (group_gaps or [])
    ]

    return FinalExecutionDecision(
        run_id=run_id,
        as_of=as_of,
        system_status=system_status,
        data_gate=data_gate,
        execution_scope=execution_scope,
        alpha_approval=alpha_approval,
        alpha_execution_status=alpha_execution_status,
        group_gap_source=group_gap_source,
        operational_verdict=operational_verdict,
        dry_run_days=dry_run_days,
        allowed_actions=allowed,
        blocked_actions=blocked,
        final_trade_list=final_trades,
        group_gaps=gap_rows,
        data_gate_detail=data_gate_detail,
        market_data_audit=market_data_audit,
        execution_permissions=execution_permissions,
        policy_cap=policy_cap,
        technical_status=technical_status,
        operating=operating,
    )


def write_final_execution_decision(decision: FinalExecutionDecision, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
