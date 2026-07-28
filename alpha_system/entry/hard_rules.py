"""Hard-rule enforcement for tranche entry (sunset / reverse / thesis damage)."""



from __future__ import annotations



from datetime import date

from typing import Any



from alpha_system.entry.models import (

    EntryAction,

    EntryActionType,

    TrancheState,

)

from alpha_system.schema import AlphaSystemConfig, TrancheId





TERMINAL_STATES = frozenset(

    {TrancheState.EXECUTED, TrancheState.EXPIRED, TrancheState.FROZEN}

)





def is_past_window(cfg: AlphaSystemConfig, as_of: date) -> bool:

    return as_of > cfg.thesis_window.window_end





def apply_sunset(

    *,

    cfg: AlphaSystemConfig,

    tranche_id: TrancheId,

    state: TrancheState,

    weight: float,

    as_of: date,

    meta: dict[str, Any] | None = None,

) -> tuple[TrancheState, list[EntryAction]]:

    """Hard rule 1: unexecuted / remainder expires after window_end → SAA reflux."""

    if not cfg.hard_rules.sunset_enabled:

        return state, []

    if state in TERMINAL_STATES:

        return state, []

    if not is_past_window(cfg, as_of):

        return state, []



    meta = dict(meta or {})

    remaining_frac = float(meta.get("remaining_fraction", 0.0))

    if state == TrancheState.PARTIAL_EXECUTED and remaining_frac > 0:

        reflux_weight = weight * remaining_frac

        detail = (

            f"sunset: T4 remainder {remaining_frac:.0%} expires at window_end"

        )

    else:

        reflux_weight = weight

        detail = (

            f"sunset: window_end={cfg.thesis_window.window_end.isoformat()} "

            f"passed (as_of={as_of.isoformat()}); unexecuted tranche expires"

        )



    action = EntryAction(

        action_type=EntryActionType.REFLUX_TO_SAA,

        tranche_id=tranche_id,

        reason=detail,

        weight=reflux_weight,

        as_of=as_of,

    )

    return TrancheState.EXPIRED, [action]





def apply_thesis_damage_freeze(

    *,

    cfg: AlphaSystemConfig,

    tranche_id: TrancheId,

    state: TrancheState,

    weight: float,

    as_of: date,

    thesis_damage_active: bool,

    matched_events: list[str],

) -> tuple[TrancheState, list[EntryAction]]:

    """Hard rule 3: thesis-damage flag freezes all unexecuted tranches."""

    if not cfg.hard_rules.thesis_damage_freeze_enabled:

        return state, []

    if not thesis_damage_active:

        return state, []

    if state in TERMINAL_STATES:

        return state, []

    events = ", ".join(matched_events) if matched_events else "(flag)"

    freeze = EntryAction(

        action_type=EntryActionType.FREEZE,

        tranche_id=tranche_id,

        reason=f"thesis_damage: freeze unexecuted tranche; events={events}",

        weight=weight,

        as_of=as_of,

    )

    reflux = EntryAction(

        action_type=EntryActionType.REFLUX_TO_SAA,

        tranche_id=tranche_id,

        reason="thesis_damage: unexecuted capital → SAA reflux action",

        weight=weight,

        as_of=as_of,

    )

    return TrancheState.FROZEN, [freeze, reflux]





def block_reverse_execution(

    *,

    cfg: AlphaSystemConfig,

    tranche_id: TrancheId,

    state: TrancheState,

    trigger_met: bool,

    weight: float,

    as_of: date,

) -> EntryAction | None:

    """Hard rule 2: block execute when trigger is not met."""

    if not cfg.hard_rules.reverse_execution_blocked:

        return None

    if state in TERMINAL_STATES:

        return EntryAction(

            action_type=EntryActionType.WARN_BLOCKED,

            tranche_id=tranche_id,

            reason=f"reverse_blocked: tranche already terminal ({state.value})",

            weight=weight,

            as_of=as_of,

            blocked=True,

        )

    if trigger_met and state == TrancheState.READY:

        return None

    return EntryAction(

        action_type=EntryActionType.WARN_BLOCKED,

        tranche_id=tranche_id,

        reason=(

            "reverse_blocked: trigger not met — execution input rejected "

            f"(state={state.value}, trigger_met={trigger_met})"

        ),

        weight=weight,

        as_of=as_of,

        blocked=True,

    )


