"""Tranche trigger evaluation and state transitions."""



from __future__ import annotations



from dataclasses import dataclass, field

from datetime import date

from typing import Mapping, Optional, Sequence



from alpha_system.entry.entry_gates import missing_entry_target_tickers

from alpha_system.entry.hard_rules import (

    TERMINAL_STATES,

    apply_sunset,

    apply_thesis_damage_freeze,

    block_reverse_execution,

)

from alpha_system.entry.models import (

    EntryAction,

    EntryActionType,

    TrancheState,

    TrancheStatus,

)

from alpha_system.journal import append_record

from alpha_system.schema import (

    AlphaSystemConfig,

    ConfigTodoError,

    TRANCHE_ORDER,

    TrancheId,

    TriggerType,

)





@dataclass

class TriggerSnapshot:

    """Market / ops inputs for one evaluation pass (no live trading)."""



    as_of: date

    system_started: bool = True

    go_live_date: Optional[date] = None

    events_fired: frozenset[str] = field(default_factory=frozenset)

    thesis_damage_flag: bool = False

    # T3 primary: monthly feed — KOSPI market PBR in 10y bottom-20% band

    kospi_pbr_in_bottom_band: Optional[bool] = None

    # Legacy alias

    valuation_band_touched: Optional[bool] = None

    prior_states: Mapping[TrancheId, TrancheState] = field(default_factory=dict)

    prior_meta: Mapping[TrancheId, dict] = field(default_factory=dict)





@dataclass

class EntryEvaluation:

    as_of: date

    statuses: list[TrancheStatus]

    actions: list[EntryAction]

    warnings: list[str]

    todo_fields: list[str]





def _prior(snapshot: TriggerSnapshot, tranche_id: TrancheId) -> TrancheState:

    return snapshot.prior_states.get(tranche_id, TrancheState.PENDING)





def _prior_meta(snapshot: TriggerSnapshot, tranche_id: TrancheId) -> dict:

    return dict(snapshot.prior_meta.get(tranche_id, {}))





def _thesis_damage_active(

    cfg: AlphaSystemConfig, snapshot: TriggerSnapshot

) -> tuple[bool, list[str]]:

    matched = sorted(

        set(cfg.thesis_damage_event_ids) & set(snapshot.events_fired)

    )

    active = bool(snapshot.thesis_damage_flag or matched)

    return active, matched





def _months_since_go_live(cfg: AlphaSystemConfig, snapshot: TriggerSnapshot) -> int:

    start = snapshot.go_live_date or cfg.go_live_date

    if start is None:

        return 0

    return (snapshot.as_of.year - start.year) * 12 + (

        snapshot.as_of.month - start.month

    )





def _t3_band_touched(cfg: AlphaSystemConfig, snapshot: TriggerSnapshot) -> tuple[bool, str]:

    tcfg = cfg.tranches["T3"]

    band = tcfg.valuation_band

    if band is None:

        return False, "price: valuation_band unset"

    touched = snapshot.kospi_pbr_in_bottom_band

    if touched is None:

        touched = snapshot.valuation_band_touched

    if touched is None:

        return False, "price: kospi_pbr_in_bottom_band unknown in snapshot"

    if touched:

        pct = band.get("bottom_percentile", 20)

        yrs = band.get("lookback_years", 10)

        return True, f"price: KOSPI PBR in {yrs}y bottom {pct}% band"

    or_hook = dict(band.get("or_eligible_avg_value_score") or {})

    if or_hook.get("enabled"):

        return False, "price: primary band not touched; OR hook enabled but not implemented"

    return False, "price: market PBR band not touched"





def _t4_evaluate(

    cfg: AlphaSystemConfig,

    snapshot: TriggerSnapshot,

    *,

    statuses_so_far: Mapping[TrancheId, TrancheStatus],

    prior_state: TrancheState,

    prior_meta: dict,

) -> tuple[bool, str, dict]:

    rules = cfg.tranches["T4"].hybrid_rules

    if rules is None:

        return False, "hybrid: hybrid_rules unset", {}



    mode = str(rules.get("mode", "split_follow_expire"))

    months_req = int(rules.get("months_after_go_live", 12))

    init_frac = float(rules.get("initial_execution_fraction", 0.5))

    follow_frac = float(rules.get("follow_on_execution_fraction", 0.5))



    t2 = statuses_so_far.get(TrancheId.T2)

    t3 = statuses_so_far.get(TrancheId.T3)

    t2_met = t2 is not None and t2.trigger_met

    t3_met = t3 is not None and t3.trigger_met

    months = _months_since_go_live(cfg, snapshot)



    if prior_state == TrancheState.PARTIAL_EXECUTED:

        if t2_met or t3_met:

            return (

                True,

                f"hybrid: T2/T3 follow-on for remaining {follow_frac:.0%} "

                f"(t2={t2_met}, t3={t3_met})",

                {

                    "executable_fraction": follow_frac,

                    "phase": "follow_on",

                    "remaining_fraction": 0.0,

                },

            )

        return False, "hybrid: partial executed — awaiting T2/T3 for remainder", {}



    if prior_state in (TrancheState.EXECUTED, TrancheState.EXPIRED, TrancheState.FROZEN):

        return False, f"hybrid: terminal prior state {prior_state.value}", {}



    if months >= months_req and not t2_met and not t3_met:

        return (

            True,

            f"hybrid: {months}m >= {months_req}m and T2/T3 unmet — "

            f"initial {init_frac:.0%} ({mode})",

            {

                "executable_fraction": init_frac,

                "phase": "initial",

                "remaining_fraction": follow_frac,

            },

        )

    if months < months_req:

        return (

            False,

            f"hybrid: {months}m < {months_req}m since go-live",

            {},

        )

    return False, "hybrid: T2 or T3 already met — initial T4 slice does not fire", {}





def evaluate_trigger_met(

    cfg: AlphaSystemConfig,

    tranche_id: TrancheId,

    snapshot: TriggerSnapshot,

    *,

    statuses_so_far: Mapping[TrancheId, TrancheStatus] | None = None,

    prior_state: TrancheState | None = None,

    prior_meta: dict | None = None,

) -> tuple[bool, str, dict]:

    """Return (met, detail, meta). Does not invent TODO values."""

    tcfg = cfg.tranches[tranche_id.value]

    prior_state = prior_state or _prior(snapshot, tranche_id)

    prior_meta = prior_meta or _prior_meta(snapshot, tranche_id)



    if tcfg.trigger_type == TriggerType.TIME:

        if snapshot.system_started:

            return True, "time: system_started", {}

        return False, "time: system not started", {}



    if tcfg.trigger_type == TriggerType.EVENT:

        if not tcfg.event_ids:

            return False, "event: event_ids empty", {}

        hit = [e for e in tcfg.event_ids if e in snapshot.events_fired]

        if hit:

            return True, f"event: fired={hit}", {}

        return False, "event: none of configured event_ids fired", {}



    if tcfg.trigger_type == TriggerType.PRICE:

        met, detail = _t3_band_touched(cfg, snapshot)

        return met, detail, {}



    if tcfg.trigger_type == TriggerType.HYBRID:

        return _t4_evaluate(

            cfg,

            snapshot,

            statuses_so_far=statuses_so_far or {},

            prior_state=prior_state,

            prior_meta=prior_meta,

        )



    return False, f"unknown trigger_type={tcfg.trigger_type}", {}





def evaluate_entry(

    cfg: AlphaSystemConfig,

    snapshot: TriggerSnapshot,

    *,

    journal: bool = True,

) -> EntryEvaluation:

    actions: list[EntryAction] = []

    warnings: list[str] = []

    statuses: list[TrancheStatus] = []

    by_id: dict[TrancheId, TrancheStatus] = {}



    # App run != system live: no go_live_date => PRE_LAUNCH lock (skip all triggers)

    effective_go_live = (

        snapshot.go_live_date

        if snapshot.go_live_date is not None

        else cfg.go_live_date

    )

    if effective_go_live is None:

        for tranche_id in TRANCHE_ORDER:

            tcfg = cfg.tranches[tranche_id.value]

            status = TrancheStatus(

                tranche_id=tranche_id,

                state=TrancheState.PENDING,

                weight=tcfg.weight,

                trigger_type=tcfg.trigger_type,

                trigger_met=False,

                detail="pre_launch: locked (go_live_date unset)",

                meta={"pre_launch": True, "locked": True},

            )

            statuses.append(status)

            by_id[tranche_id] = status

        return EntryEvaluation(

            as_of=snapshot.as_of,

            statuses=statuses,

            actions=actions,

            warnings=["PRE_LAUNCH: all tranches locked until go_live_date"],

            todo_fields=cfg.todo_fields(),

        )



    damage_active, matched = _thesis_damage_active(cfg, snapshot)



    for tranche_id in TRANCHE_ORDER:

        tcfg = cfg.tranches[tranche_id.value]

        state = _prior(snapshot, tranche_id)

        meta = _prior_meta(snapshot, tranche_id)

        detail = ""

        trigger_met = False

        trigger_meta: dict = {}

        last: EntryAction | None = None



        if state == TrancheState.EXECUTED:

            status = TrancheStatus(

                tranche_id=tranche_id,

                state=state,

                weight=tcfg.weight,

                trigger_type=tcfg.trigger_type,

                trigger_met=True,

                detail="already executed",

                meta=meta,

            )

            statuses.append(status)

            by_id[tranche_id] = status

            continue



        state, freeze_actions = apply_thesis_damage_freeze(

            cfg=cfg,

            tranche_id=tranche_id,

            state=state,

            weight=tcfg.weight,

            as_of=snapshot.as_of,

            thesis_damage_active=damage_active,

            matched_events=matched,

        )

        if freeze_actions:

            actions.extend(freeze_actions)

            last = freeze_actions[-1]

            status = TrancheStatus(

                tranche_id=tranche_id,

                state=state,

                weight=tcfg.weight,

                trigger_type=tcfg.trigger_type,

                trigger_met=False,

                detail=freeze_actions[0].reason,

                last_action=last,

                meta=meta,

            )

            statuses.append(status)

            by_id[tranche_id] = status

            continue



        state, sunset_actions = apply_sunset(

            cfg=cfg,

            tranche_id=tranche_id,

            state=state,

            weight=tcfg.weight,

            as_of=snapshot.as_of,

            meta=meta,

        )

        if sunset_actions:

            actions.extend(sunset_actions)

            last = sunset_actions[-1]

            status = TrancheStatus(

                tranche_id=tranche_id,

                state=state,

                weight=tcfg.weight,

                trigger_type=tcfg.trigger_type,

                trigger_met=False,

                detail=last.reason,

                last_action=last,

                meta=meta,

            )

            statuses.append(status)

            by_id[tranche_id] = status

            continue



        if state in TERMINAL_STATES:

            status = TrancheStatus(

                tranche_id=tranche_id,

                state=state,

                weight=tcfg.weight,

                trigger_type=tcfg.trigger_type,

                trigger_met=False,

                detail=f"terminal {state.value}",

                meta=meta,

            )

            statuses.append(status)

            by_id[tranche_id] = status

            continue



        trigger_met, detail, trigger_meta = evaluate_trigger_met(

            cfg,

            tranche_id,

            snapshot,

            statuses_so_far=by_id,

            prior_state=state,

            prior_meta=meta,

        )

        merged_meta = {**meta, **trigger_meta}



        if trigger_met and state in (TrancheState.PENDING, TrancheState.PARTIAL_EXECUTED):

            state = TrancheState.READY

            mark = EntryAction(

                action_type=EntryActionType.MARK_READY,

                tranche_id=tranche_id,

                reason=detail,

                weight=tcfg.weight * float(merged_meta.get("executable_fraction", 1.0)),

                as_of=snapshot.as_of,

            )

            actions.append(mark)

            last = mark

        elif trigger_met and state == TrancheState.READY:

            detail = f"already ready ({detail})"

        elif "[TODO]" in detail or "unset" in detail:

            warnings.append(f"{tranche_id.value}: {detail}")



        status = TrancheStatus(

            tranche_id=tranche_id,

            state=state,

            weight=tcfg.weight,

            trigger_type=tcfg.trigger_type,

            trigger_met=trigger_met,

            detail=detail,

            last_action=last,

            meta=merged_meta,

        )

        statuses.append(status)

        by_id[tranche_id] = status



    if journal:

        for act in actions:

            _journal_entry_action(act, snapshot=snapshot)



    return EntryEvaluation(

        as_of=snapshot.as_of,

        statuses=statuses,

        actions=actions,

        warnings=warnings,

        todo_fields=cfg.todo_fields(),

    )





def _journal_entry_action(

    action: EntryAction,

    *,

    snapshot: TriggerSnapshot,

    rationale: str = "",

) -> EntryAction:

    append_record(

        action_kind=action.action_type.value,

        as_of=action.as_of,

        subject=action.tranche_id.value,

        rationale=rationale or action.reason,

        trigger_snapshot={

            "as_of": snapshot.as_of.isoformat(),

            "system_started": snapshot.system_started,

            "go_live_date": (

                snapshot.go_live_date.isoformat()

                if snapshot.go_live_date

                else None

            ),

            "events_fired": sorted(snapshot.events_fired),

            "thesis_damage_flag": snapshot.thesis_damage_flag,

            "kospi_pbr_in_bottom_band": snapshot.kospi_pbr_in_bottom_band,

            "valuation_band_touched": snapshot.valuation_band_touched,

            "prior_states": {

                k.value: v.value for k, v in snapshot.prior_states.items()

            },

        },

        score_snapshot={},

        payload={

            "weight": action.weight,

            "blocked": action.blocked,

            "reason": action.reason,

        },

    )

    return action





def attempt_execute(
    cfg: AlphaSystemConfig,
    *,
    tranche_id: TrancheId,
    status: TrancheStatus,
    as_of: date,
    rationale: str = "",
    score_snapshot: dict | None = None,
    journal: bool = True,
    execution_fraction: float | None = None,
    entry_tickers: Sequence[str] | None = None,
    has_target_by_ticker: Mapping[str, bool] | None = None,
) -> tuple[TrancheStatus, EntryAction]:
    frac = execution_fraction
    if frac is None:
        frac = float(status.meta.get("executable_fraction", 1.0))
    effective_weight = status.weight * frac

    blocked = block_reverse_execution(
        cfg=cfg,
        tranche_id=tranche_id,
        state=status.state,
        trigger_met=status.trigger_met,
        weight=effective_weight,
        as_of=as_of,
    )
    if blocked is None and cfg.exit.entry_require_target_valuation:
        missing = missing_entry_target_tickers(
            cfg,
            entry_tickers=entry_tickers,
            has_target_by_ticker=has_target_by_ticker,
        )
        if missing:
            if missing == ["*"]:
                reason = (
                    "entry blocked: entry_tickers omitted while "
                    "entry_require_target_valuation=true — pass tickers (or [] if none)"
                )
            else:
                reason = (
                    "entry blocked: waiting candidates lack target valuation — "
                    + "; ".join(missing)
                )
            blocked = EntryAction(
                action_type=EntryActionType.WARN_BLOCKED,
                tranche_id=tranche_id,
                reason=reason,
                weight=effective_weight,
                as_of=as_of,
                blocked=True,
            )

    if blocked is not None:

        if journal:

            append_record(

                action_kind=blocked.action_type.value,

                as_of=as_of,

                subject=tranche_id.value,

                rationale=rationale or blocked.reason,

                trigger_snapshot={

                    "state": status.state.value,

                    "trigger_met": status.trigger_met,

                },

                score_snapshot=dict(score_snapshot or {}),

                payload={"blocked": True, "weight": effective_weight},

            )

        return status, blocked



    action = EntryAction(

        action_type=EntryActionType.EXECUTE,

        tranche_id=tranche_id,

        reason="execute acknowledged (manual / ops) — report only, no auto-trade",

        weight=effective_weight,

        as_of=as_of,

    )

    if journal:

        append_record(

            action_kind=action.action_type.value,

            as_of=as_of,

            subject=tranche_id.value,

            rationale=rationale or action.reason,

            trigger_snapshot={

                "state": status.state.value,

                "trigger_met": status.trigger_met,

                "execution_fraction": frac,

            },

            score_snapshot=dict(score_snapshot or {}),

            payload={"blocked": False, "weight": effective_weight},

        )



    remaining = float(status.meta.get("remaining_fraction", 0.0))

    if frac < 1.0 - 1e-9 and remaining > 1e-9:

        new_state = TrancheState.PARTIAL_EXECUTED

        new_meta = {

            **status.meta,

            "executed_fraction": frac,

            "remaining_fraction": remaining,

        }

    else:

        new_state = TrancheState.EXECUTED

        new_meta = {**status.meta, "executed_fraction": 1.0, "remaining_fraction": 0.0}



    updated = TrancheStatus(

        tranche_id=status.tranche_id,

        state=new_state,

        weight=status.weight,

        trigger_type=status.trigger_type,

        trigger_met=True,

        detail=action.reason,

        last_action=action,

        meta=new_meta,

    )

    return updated, action





def require_score_cutoff(cfg: AlphaSystemConfig) -> float:

    if cfg.scoring.score_cutoff is None:

        raise ConfigTodoError(

            "[TODO] scoring.score_cutoff unset — absolute cutoff required"

        )

    return float(cfg.scoring.score_cutoff)


