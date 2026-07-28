"""Evaluate exit conditions; discretionary exits are warned but never blocked."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from alpha_system.exit.models import ExitAction, ExitActionType, ExitReason
from alpha_system.journal.recorder import record_action
from alpha_system.schema import AlphaSystemConfig, ConfigTodoError


@dataclass
class PositionView:
    ticker: str
    name: str = ""
    weight: float = 0.0
    thesis_damage_name: Optional[bool] = None
    total_score: Optional[float] = None
    target_valuation_reached: Optional[bool] = None


@dataclass
class ExitSnapshot:
    as_of: date
    positions: list[PositionView] = field(default_factory=list)
    thesis_damage_flag: bool = False
    thesis_damage_events: tuple[str, ...] = ()


@dataclass
class ExitEvaluation:
    as_of: date
    actions: list[ExitAction]
    warnings: list[str]
    todo_fields: list[str]
    window_end_report: Optional[str] = None


def _todo_exit_fields(cfg: AlphaSystemConfig) -> list[str]:
    pending: list[str] = []
    if cfg.exit.thesis_damage_exit is None:
        pending.append("exit.thesis_damage_exit")
    if cfg.exit.score_below_cutoff_action is None:
        pending.append("exit.score_below_cutoff_action")
    if cfg.exit.target_valuation_exit is None:
        pending.append("exit.target_valuation_exit")
    if cfg.exit.window_end_portfolio_action is None:
        pending.append("exit.window_end_portfolio_action")
    if cfg.scoring.score_cutoff is None:
        pending.append("scoring.score_cutoff")
    return pending


def evaluate_exits(
    cfg: AlphaSystemConfig,
    snapshot: ExitSnapshot,
    *,
    journal: bool = True,
) -> ExitEvaluation:
    """
    Judge four exit conditions.

    Entry FROZEN = unexecuted tranche freeze.
    Exit THESIS_DAMAGE = held-position liquidation judgment.
    """
    actions: list[ExitAction] = []
    warnings: list[str] = []
    todos = _todo_exit_fields(cfg)
    window_report: Optional[str] = None

    past_or_on_end = snapshot.as_of >= cfg.thesis_window.window_end
    if past_or_on_end:
        window_report = (
            f"window_end={cfg.thesis_window.window_end.isoformat()} "
            f"as_of={snapshot.as_of.isoformat()}: "
            f"held_names={len(snapshot.positions)}"
        )
        if cfg.exit.window_end_portfolio_action is None:
            warnings.append(
                "window_end reached but exit.window_end_portfolio_action [TODO] "
                "— judgment report only"
            )
            act = ExitAction(
                action_type=ExitActionType.PORTFOLIO_WIND_DOWN_REPORT,
                reason=ExitReason.WINDOW_END,
                ticker="*",
                as_of=snapshot.as_of,
                detail=window_report + " — decide full wind-down vs hold (config TODO)",
                fraction=1.0,
                rule_met=True,
                meta={"positions": [p.ticker for p in snapshot.positions]},
            )
            actions.append(_maybe_journal(act, journal))
        else:
            mode = str(cfg.exit.window_end_portfolio_action.get("mode", "report"))
            for pos in snapshot.positions:
                act = ExitAction(
                    action_type=(
                        ExitActionType.LIQUIDATE
                        if mode == "liquidate"
                        else ExitActionType.PORTFOLIO_WIND_DOWN_REPORT
                    ),
                    reason=ExitReason.WINDOW_END,
                    ticker=pos.ticker,
                    as_of=snapshot.as_of,
                    detail=f"window_end action mode={mode}",
                    fraction=1.0,
                    rule_met=True,
                )
                actions.append(_maybe_journal(act, journal))

    for pos in snapshot.positions:
        # market_value_cap — exit-only (sizing never trims runners)
        mv_cap = float(cfg.sizing.market_value_cap)
        if pos.weight > mv_cap + 1e-12:
            over = pos.weight - mv_cap
            frac = over / pos.weight if pos.weight > 0 else 0.0
            act = ExitAction(
                action_type=ExitActionType.REDUCE,
                reason=ExitReason.MARKET_VALUE_CAP,
                ticker=pos.ticker,
                as_of=snapshot.as_of,
                detail=(
                    f"market_value_cap breached: weight={pos.weight:.4f} > "
                    f"cap={mv_cap:.2f}; reduce toward cap "
                    f"(sizing does not handle mark-to-market)"
                ),
                fraction=min(1.0, max(0.0, frac)),
                rule_met=True,
                meta={
                    "market_value_cap": mv_cap,
                    "current_weight": pos.weight,
                    "owned_by": "exit",
                },
            )
            actions.append(_maybe_journal(act, journal))

        name_damage = bool(pos.thesis_damage_name) or snapshot.thesis_damage_flag
        if name_damage:
            if cfg.exit.thesis_damage_exit is None:
                warnings.append(
                    f"{pos.ticker}: thesis damage signaled; "
                    "exit.thesis_damage_exit [TODO] — LIQUIDATE judgment"
                )
                frac = 1.0
            else:
                frac = float(cfg.exit.thesis_damage_exit.get("fraction", 1.0))
            act = ExitAction(
                action_type=(
                    ExitActionType.LIQUIDATE if frac >= 1.0 else ExitActionType.REDUCE
                ),
                reason=ExitReason.THESIS_DAMAGE,
                ticker=pos.ticker,
                as_of=snapshot.as_of,
                detail=(
                    "held-position thesis damage "
                    f"(events={list(snapshot.thesis_damage_events)}); "
                    "distinct from entry FROZEN on unexecuted tranches"
                ),
                fraction=frac,
                rule_met=True,
            )
            actions.append(_maybe_journal(act, journal))

        if pos.total_score is not None:
            cutoff = cfg.scoring.score_cutoff
            if cutoff is None:
                warnings.append(
                    f"{pos.ticker}: total_score present but score_cutoff [TODO] "
                    "— score-exit not fired"
                )
            elif pos.total_score < float(cutoff):
                mode = cfg.exit.score_below_cutoff_action
                if mode is None:
                    warnings.append(
                        f"{pos.ticker}: below cutoff; "
                        "exit.score_below_cutoff_action [TODO] — REDUCE placeholder"
                    )
                    act = ExitAction(
                        action_type=ExitActionType.REDUCE,
                        reason=ExitReason.SCORE_BELOW_CUTOFF,
                        ticker=pos.ticker,
                        as_of=snapshot.as_of,
                        detail=(
                            f"total_score={pos.total_score} < cutoff={cutoff}; "
                            "action mode TODO"
                        ),
                        fraction=0.5,
                        rule_met=True,
                        meta={"todo_action_mode": True},
                    )
                else:
                    act = ExitAction(
                        action_type=(
                            ExitActionType.LIQUIDATE
                            if mode == "liquidate"
                            else ExitActionType.REDUCE
                        ),
                        reason=ExitReason.SCORE_BELOW_CUTOFF,
                        ticker=pos.ticker,
                        as_of=snapshot.as_of,
                        detail=f"total_score={pos.total_score} < cutoff={cutoff}",
                        fraction=1.0 if mode == "liquidate" else 0.5,
                        rule_met=True,
                    )
                actions.append(_maybe_journal(act, journal))

        if pos.target_valuation_reached is True:
            if cfg.exit.target_valuation_exit is None:
                warnings.append(
                    f"{pos.ticker}: target valuation reached; "
                    "exit.target_valuation_exit [TODO] — LIQUIDATE judgment"
                )
                frac = 1.0
            else:
                frac = float(cfg.exit.target_valuation_exit.get("fraction", 1.0))
            act = ExitAction(
                action_type=(
                    ExitActionType.LIQUIDATE if frac >= 1.0 else ExitActionType.REDUCE
                ),
                reason=ExitReason.TARGET_VALUATION,
                ticker=pos.ticker,
                as_of=snapshot.as_of,
                detail="target valuation reached",
                fraction=frac,
                rule_met=True,
            )
            actions.append(_maybe_journal(act, journal))

    return ExitEvaluation(
        as_of=snapshot.as_of,
        actions=actions,
        warnings=warnings,
        todo_fields=todos,
        window_end_report=window_report,
    )


def attempt_exit(
    cfg: AlphaSystemConfig,
    *,
    ticker: str,
    as_of: date,
    rule_met: bool,
    fraction: float = 1.0,
    detail: str = "",
    rationale: str = "",
    discretionary_reason: str | None = None,
    trigger_snapshot: dict | None = None,
    score_snapshot: dict | None = None,
    journal: bool = True,
) -> ExitAction:
    """
    Acknowledge an exit intent.

    Asymmetry vs entry hard rule 2:
      - Entry with unmet trigger → BLOCK
      - Exit with unmet rule → WARN only, still allowed (discretionary escape)
    WARN_DISCRETIONARY requires discretionary_reason (journal-enforced).
    """
    _ = cfg
    exec_type = (
        ExitActionType.LIQUIDATE if fraction >= 1.0 else ExitActionType.REDUCE
    )
    snap_t = dict(trigger_snapshot or {})
    snap_s = dict(score_snapshot or {})
    rationale_text = rationale or detail

    if rule_met:
        action = ExitAction(
            action_type=exec_type,
            reason=ExitReason.DISCRETIONARY,
            ticker=ticker,
            as_of=as_of,
            detail=detail or "exit acknowledged (rule_met)",
            fraction=fraction,
            rule_met=True,
            blocked=False,
        )
        return _maybe_journal(
            action,
            journal,
            rationale=rationale_text,
            discretionary_reason=None,
            trigger_snapshot=snap_t,
            score_snapshot=snap_s,
        )

    warn = ExitAction(
        action_type=ExitActionType.WARN_DISCRETIONARY,
        reason=ExitReason.DISCRETIONARY,
        ticker=ticker,
        as_of=as_of,
        detail=(
            detail
            or "discretionary exit: no exit rule met — WARNING only, not blocked"
        ),
        fraction=fraction,
        rule_met=False,
        blocked=False,
        meta={"allowed": True, "asymmetric_to_entry": True},
    )
    warn = _maybe_journal(
        warn,
        journal,
        rationale=rationale_text,
        discretionary_reason=discretionary_reason,
        trigger_snapshot=snap_t,
        score_snapshot=snap_s,
    )
    follow = ExitAction(
        action_type=exec_type,
        reason=ExitReason.DISCRETIONARY,
        ticker=ticker,
        as_of=as_of,
        detail="discretionary exit allowed after warning",
        fraction=fraction,
        rule_met=False,
        blocked=False,
        meta={"after_warning": warn.journal_id},
    )
    follow = _maybe_journal(
        follow,
        journal,
        rationale=rationale_text or "follow-through after discretionary warning",
        discretionary_reason=None,
        trigger_snapshot=snap_t,
        score_snapshot=snap_s,
    )
    return ExitAction(
        action_type=warn.action_type,
        reason=warn.reason,
        ticker=warn.ticker,
        as_of=warn.as_of,
        detail=warn.detail,
        fraction=warn.fraction,
        rule_met=False,
        blocked=False,
        meta={**warn.meta, "follow_through_journal_id": follow.journal_id},
        journal_id=warn.journal_id,
    )


def _maybe_journal(
    action: ExitAction,
    journal: bool,
    *,
    rationale: str = "",
    discretionary_reason: str | None = None,
    trigger_snapshot: dict | None = None,
    score_snapshot: dict | None = None,
) -> ExitAction:
    if not journal:
        return action
    entry = record_action(
        kind="exit",
        payload={
            "action_type": action.action_type.value,
            "reason": action.reason.value,
            "ticker": action.ticker,
            "as_of": action.as_of.isoformat(),
            "detail": action.detail,
            "rationale": rationale or action.detail,
            "discretionary_reason": discretionary_reason,
            "trigger_snapshot": dict(trigger_snapshot or {}),
            "score_snapshot": dict(score_snapshot or {}),
            "fraction": action.fraction,
            "rule_met": action.rule_met,
            "blocked": action.blocked,
            "meta": action.meta,
        },
    )
    return ExitAction(
        action_type=action.action_type,
        reason=action.reason,
        ticker=action.ticker,
        as_of=action.as_of,
        detail=action.detail,
        fraction=action.fraction,
        rule_met=action.rule_met,
        blocked=action.blocked,
        meta=action.meta,
        journal_id=entry.entry_id,
    )


def require_exit_threshold(cfg: AlphaSystemConfig, field_path: str) -> dict[str, Any]:
    mapping = {
        "exit.thesis_damage_exit": cfg.exit.thesis_damage_exit,
        "exit.target_valuation_exit": cfg.exit.target_valuation_exit,
        "exit.window_end_portfolio_action": cfg.exit.window_end_portfolio_action,
    }
    value = mapping.get(field_path)
    if value is None:
        raise ConfigTodoError(f"[TODO] {field_path} unset")
    return dict(value)
