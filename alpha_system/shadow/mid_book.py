"""Pure mid-book shadow rebalance — QV proposal + ops ladder + add gates.

Review-only simulation. Does not touch target_portfolio or broker APIs.
Priority matches weight_action: exit > trim > hold; mom/now gate adds only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


def _norm_tk(ticker: object) -> str:
    return str(ticker or "").strip().zfill(6)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


@dataclass
class ShadowNameGate:
    """Per-name ops + timing gates for one day."""

    ops_signal: str = "hold"  # hold|trim|cash_half|exit_full|missing
    mom_weak: bool = False
    now_hard_block: bool = False  # 추매금지|추가금지 only
    in_buy_zone: bool = False  # ladder 매수1/2
    has_target: bool = True


@dataclass
class ShadowBookState:
    """Weights are fractions of book NAV (sum <= 1); residual = cash."""

    weights: dict[str, float] = field(default_factory=dict)
    nav: float = 1.0

    def normalized(self) -> "ShadowBookState":
        w = {_norm_tk(k): _clip01(v) for k, v in self.weights.items() if float(v) > 1e-12}
        s = sum(w.values())
        if s > 1.0 + 1e-9:
            w = {k: v / s for k, v in w.items()}
        return ShadowBookState(weights=w, nav=float(self.nav))


def apply_ops_to_weights(
    weights: Mapping[str, float],
    *,
    proposal: Mapping[str, float],
    gates: Mapping[str, ShadowNameGate],
    single_cap: float = 0.25,
    add_frac: float = 0.5,
) -> tuple[dict[str, float], list[dict]]:
    """Map current weights → next target weights using mid ops priority.

    Returns (new_weights, trade_events).
    """
    cur = {_norm_tk(k): _clip01(v) for k, v in weights.items() if float(v) > 1e-12}
    prop = {_norm_tk(k): _clip01(v) for k, v in proposal.items() if float(v) > 1e-12}
    # Normalize proposal to sum<=1
    ps = sum(prop.values())
    if ps > 1.0 + 1e-9:
        prop = {k: v / ps for k, v in prop.items()}

    out = dict(cur)
    events: list[dict] = []

    # 1) Exit / trim on held names (ops wins)
    for tk, w in list(out.items()):
        g = gates.get(tk) or ShadowNameGate()
        sig = (g.ops_signal or "hold").strip()
        if not g.has_target and sig in {"", "hold", "missing"}:
            events.append({"ticker": tk, "kind": "missing", "from": w, "to": w})
            continue
        if sig == "exit_full":
            events.append({"ticker": tk, "kind": "exit_full", "from": w, "to": 0.0})
            out[tk] = 0.0
        elif sig == "cash_half":
            nw = w * 0.5
            events.append({"ticker": tk, "kind": "cash_half", "from": w, "to": nw})
            out[tk] = nw
        elif sig == "trim":
            nw = w * 0.75
            events.append({"ticker": tk, "kind": "trim", "from": w, "to": nw})
            out[tk] = nw

    # Drop zeros
    out = {k: v for k, v in out.items() if v > 1e-12}

    # 2) Scale toward proposal for names not in reduce mode
    for tk, pw in prop.items():
        g = gates.get(tk) or ShadowNameGate()
        sig = (g.ops_signal or "hold").strip()
        if sig in {"exit_full", "cash_half", "trim"}:
            continue
        if not g.has_target:
            continue
        cur_w = out.get(tk, 0.0)
        if pw <= cur_w + 1e-12:
            # Already at/above proposal — hold (no chase)
            continue
        # Add only in buy zone and when mom/now allow
        if not g.in_buy_zone:
            events.append({"ticker": tk, "kind": "add_skip_zone", "from": cur_w, "to": cur_w})
            continue
        if g.mom_weak or g.now_hard_block:
            events.append(
                {
                    "ticker": tk,
                    "kind": "add_wait",
                    "from": cur_w,
                    "to": cur_w,
                    "mom_weak": g.mom_weak,
                    "now_hard_block": g.now_hard_block,
                }
            )
            continue
        gap = pw - cur_w
        nw = cur_w + gap * float(add_frac)
        nw = min(nw, float(single_cap), pw)
        events.append({"ticker": tk, "kind": "add_ready", "from": cur_w, "to": nw})
        out[tk] = nw

    # 3) Enforce single cap + renorm if sum>1
    out = {k: min(v, float(single_cap)) for k, v in out.items() if v > 1e-12}
    s = sum(out.values())
    if s > 1.0 + 1e-9:
        out = {k: v / s for k, v in out.items()}
    return out, events


def _portfolio_return(
    weights: Mapping[str, float],
    rets: Mapping[str, float],
) -> float:
    """Weight-weighted name return; missing ret → 0."""
    total = 0.0
    for tk, w in weights.items():
        r = rets.get(_norm_tk(tk))
        if r is None:
            continue
        total += float(w) * float(r)
    return total


def turnover_one_way(
    before: Mapping[str, float],
    after: Mapping[str, float],
) -> float:
    keys = set(before) | set(after)
    return 0.5 * sum(abs(float(after.get(k, 0.0)) - float(before.get(k, 0.0))) for k in keys)


def step_day(
    state: ShadowBookState,
    *,
    name_returns: Mapping[str, float],
    proposal: Mapping[str, float],
    gates: Mapping[str, ShadowNameGate],
    cost_bps_per_one_way: float,
    market_return: float = 0.0,
    ew_returns: Mapping[str, float] | None = None,
    single_cap: float = 0.25,
    add_frac: float = 0.5,
    as_of: str = "",
) -> tuple[ShadowBookState, dict]:
    """One shadow day: mark-to-market → rebalance → apply turnover cost.

    Cost: one-way turnover * cost_bps_per_one_way (commission+slippage);
    sell tax approximated inside assumptions when caller passes full one-way bps.
    """
    st = state.normalized()
    rets = {_norm_tk(k): float(v) for k, v in name_returns.items()}
    gross_ret = _portfolio_return(st.weights, rets)
    # After mark-to-market: w_i' = w_i * (1+r_i) / (1+gross)
    denom = 1.0 + gross_ret
    if abs(denom) < 1e-15:
        drifted = dict(st.weights)
    else:
        drifted = {
            k: (w * (1.0 + rets.get(k, 0.0))) / denom
            for k, w in st.weights.items()
            if (w * (1.0 + rets.get(k, 0.0))) / denom > 1e-12
        }

    before_w = dict(drifted)
    after_w, events = apply_ops_to_weights(
        before_w,
        proposal=proposal,
        gates=gates,
        single_cap=single_cap,
        add_frac=add_frac,
    )
    tov = turnover_one_way(before_w, after_w)
    cost_frac = tov * (float(cost_bps_per_one_way) / 10_000.0)
    net_ret = gross_ret - cost_frac
    nav_net = st.nav * (1.0 + net_ret)

    # EW bench over proposal universe (or provided map)
    ew_map = ew_returns if ew_returns is not None else rets
    ew_tickers = [t for t in proposal.keys() if _norm_tk(t) in ew_map]
    if not ew_tickers:
        ew_tickers = list(ew_map.keys())
    if ew_tickers:
        ew_ret = sum(float(ew_map[_norm_tk(t)]) for t in ew_tickers) / len(ew_tickers)
    else:
        ew_ret = 0.0

    # Attribution buckets by event kinds that day (weight * not used — event counts + signed delta)
    attr = {
        "exit_full": 0.0,
        "cash_half": 0.0,
        "trim": 0.0,
        "add_ready": 0.0,
        "add_wait": 0.0,
        "hold_drift": gross_ret,
    }
    for ev in events:
        kind = str(ev.get("kind") or "")
        if kind in attr:
            delta = float(ev.get("to", 0.0)) - float(ev.get("from", 0.0))
            attr[kind] += delta

    violations: list[str] = []
    for tk, g in gates.items():
        if not g.has_target and tk in (set(before_w) | set(after_w)):
            violations.append(f"missing_target:{tk}")
    for tk, w in after_w.items():
        if w > single_cap + 1e-9:
            violations.append(f"cap:{tk}")

    day = {
        "as_of": as_of,
        "nav_gross": round(st.nav * (1.0 + gross_ret), 8),
        "nav_net": round(nav_net, 8),
        "gross_ret": round(gross_ret, 10),
        "net_ret": round(net_ret, 10),
        "turnover": round(tov, 8),
        "cost_frac": round(cost_frac, 10),
        "market_ret": round(float(market_return), 10),
        "ew_ret": round(float(ew_ret), 10),
        "weights": {k: round(v, 8) for k, v in after_w.items()},
        "cash_weight": round(max(0.0, 1.0 - sum(after_w.values())), 8),
        "events": events,
        "attribution": {k: round(v, 8) for k, v in attr.items()},
        "violations": violations,
        "review_only": True,
        "writes_target": False,
    }
    new_state = ShadowBookState(weights=after_w, nav=nav_net)
    return new_state, day
