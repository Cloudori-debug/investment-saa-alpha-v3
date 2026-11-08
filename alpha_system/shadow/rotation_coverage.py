"""순환매 가용(P1)·우위(P2) 집계 — Review-only.

docs/ROTATION_FIND_PROBABILITY_LIT.md
Never writes target_portfolio.csv or places orders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.screen_book import operational_data_dir

SELL_KINDS = frozenset({"exit_full", "cash_half", "trim"})


@dataclass(frozen=True)
class RotationNameInput:
    ticker: str
    total_score: float
    is_held: bool
    has_target: bool = True
    price_below_target: bool = True
    eligible_gate: bool = True


@dataclass
class RotationSnapshot:
    as_of: str
    sell_tickers: list[str] = field(default_factory=list)
    sell_kinds: list[str] = field(default_factory=list)
    n_eligible: int = 0
    p1: bool = False
    p2: bool = False
    top: list[dict[str, Any]] = field(default_factory=list)
    gap_req_pct: float = 20.0
    hits_req: int = 2
    hit_state: dict[str, int] = field(default_factory=dict)
    review_only: bool = True
    writes_target: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "rotation_coverage",
            "as_of": self.as_of,
            "sell_tickers": list(self.sell_tickers),
            "sell_kinds": list(self.sell_kinds),
            "n_eligible": int(self.n_eligible),
            "p1": bool(self.p1),
            "p2": bool(self.p2),
            "top": list(self.top),
            "gap_req_pct": float(self.gap_req_pct),
            "hits_req": int(self.hits_req),
            "hit_state": dict(self.hit_state),
            "review_only": True,
            "writes_target": False,
        }


def rotation_log_path(root: Path, market: object | None = None) -> Path:
    data = operational_data_dir(Path(root), market, "mid")
    return data / "shadow_rotation_coverage.jsonl"


def rotation_hit_state_path(root: Path, market: object | None = None) -> Path:
    data = operational_data_dir(Path(root), market, "mid")
    return data / "shadow_rotation_hit_state.json"


def load_hit_state_file(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in obj.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def save_hit_state_file(path: Path, hit_state: Mapping[str, int]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {str(k): int(v) for k, v in hit_state.items() if int(v) > 0}
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def gap_pct(candidate_score: float, held_score: float) -> float:
    if held_score <= 0:
        return 0.0
    return 100.0 * (float(candidate_score) - float(held_score)) / float(held_score)


def _hit_key(held: str, cand: str) -> str:
    return f"{held}|{cand}"


def eligible_pool(names: Sequence[RotationNameInput]) -> list[RotationNameInput]:
    out: list[RotationNameInput] = []
    for n in names:
        if n.is_held:
            continue
        if not n.eligible_gate or not n.has_target or not n.price_below_target:
            continue
        tk = norm_ticker(n.ticker)
        if not tk or tk == "000000":
            continue
        out.append(n)
    return out


def snapshot_coverage(
    names: Sequence[RotationNameInput],
    *,
    as_of: str,
    sell_events: Sequence[Mapping[str, Any]] | None = None,
    gap_req_pct: float = 20.0,
    hits_req: int = 2,
    prior_hits: Mapping[str, int] | None = None,
) -> RotationSnapshot:
    """One sell-day (or observe-day) snapshot.

    P1: |eligible| >= 1
    P2: some eligible beats a sell (or weakest held) by gap_req for hits_req streaks
    """
    sells = [e for e in (sell_events or []) if str(e.get("kind") or "") in SELL_KINDS]
    sell_tickers = sorted(
        {norm_ticker(e.get("ticker")) for e in sells if norm_ticker(e.get("ticker"))}
    )
    sell_kinds = sorted({str(e.get("kind")) for e in sells})

    pool = eligible_pool(names)
    by_tk = {norm_ticker(n.ticker): n for n in names if norm_ticker(n.ticker)}

    # Reference held scores: sell names first; else lowest held
    ref_held: list[RotationNameInput] = []
    for tk in sell_tickers:
        n = by_tk.get(tk)
        if n is not None:
            ref_held.append(n)
    if not ref_held:
        held = [n for n in names if n.is_held]
        if held:
            ref_held = [min(held, key=lambda x: float(x.total_score))]

    prior = dict(prior_hits or {})
    hit_state: dict[str, int] = dict(prior)
    p2 = False
    top: list[dict[str, Any]] = []

    if pool and ref_held:
        # Rank pool by score desc for top display
        ranked = sorted(pool, key=lambda x: float(x.total_score), reverse=True)
        weakest = min(ref_held, key=lambda x: float(x.total_score))
        for cand in ranked[:5]:
            g = gap_pct(cand.total_score, weakest.total_score)
            top.append(
                {
                    "ticker": norm_ticker(cand.ticker),
                    "score": round(float(cand.total_score), 4),
                    "gap_vs_ref_pct": round(g, 2),
                    "ref_ticker": norm_ticker(weakest.ticker),
                }
            )

        # Update consecutive hits per (ref, cand); P2 if any pair meets hits_req
        active_keys: set[str] = set()
        for ref in ref_held:
            for cand in pool:
                key = _hit_key(norm_ticker(ref.ticker), norm_ticker(cand.ticker))
                active_keys.add(key)
                g = gap_pct(cand.total_score, ref.total_score)
                if g >= float(gap_req_pct):
                    hit_state[key] = int(hit_state.get(key, 0)) + 1
                else:
                    hit_state[key] = 0
                if hit_state[key] >= int(hits_req):
                    p2 = True
        # Decay pairs not seen this day
        for key in list(hit_state.keys()):
            if key not in active_keys:
                hit_state[key] = 0

    p1 = len(pool) >= 1
    # Without sell events, still allow coverage observe (P1 only meaningful for pool size)
    return RotationSnapshot(
        as_of=str(as_of),
        sell_tickers=sell_tickers,
        sell_kinds=sell_kinds,
        n_eligible=len(pool),
        p1=p1,
        p2=bool(p2 and sell_tickers),  # P2 only counts on sell days
        top=top,
        gap_req_pct=float(gap_req_pct),
        hits_req=int(hits_req),
        hit_state={k: v for k, v in hit_state.items() if v > 0},
    )


def names_from_rows(rows: Sequence[Any]) -> list[RotationNameInput]:
    """Build inputs from proposal/ops portfolio rows (duck-typed)."""
    out: list[RotationNameInput] = []
    seen: set[str] = set()
    for r in rows:
        if isinstance(r, dict):
            tk = norm_ticker(r.get("ticker"))
            score = r.get("total_score")
            is_held = bool(r.get("is_held") or r.get("held"))
            has_target = bool(r.get("has_target", True))
            px = r.get("current_price")
            tp = r.get("target_price")
            eligible = bool(r.get("eligible", r.get("eligible_gate", True)))
            extra = r.get("extra") or {}
        else:
            tk = norm_ticker(getattr(r, "ticker", None))
            score = getattr(r, "total_score", None)
            is_held = bool(getattr(r, "is_held", False))
            has_target = bool(getattr(r, "has_target", True))
            px = getattr(r, "current_price", None)
            tp = getattr(r, "target_price", None)
            extra = getattr(r, "extra", None) or {}
            eligible = True
            if extra.get("eligible_gate") is False or extra.get("gate_fail"):
                eligible = False
        if not tk or tk == "000000" or tk in seen:
            continue
        try:
            sf = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            sf = 0.0
        below = True
        try:
            if px is not None and tp is not None and float(tp) > 0:
                below = float(px) < float(tp)
        except (TypeError, ValueError):
            below = True
        if not has_target:
            below = False
        seen.add(tk)
        out.append(
            RotationNameInput(
                ticker=tk,
                total_score=sf,
                is_held=is_held,
                has_target=has_target,
                price_below_target=below,
                eligible_gate=eligible,
            )
        )
    return out


def load_rotation_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("kind") == "rotation_coverage":
            rows.append(obj)
    return rows


def append_rotation_event(path: Path, snap: RotationSnapshot | Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = snap.as_dict() if isinstance(snap, RotationSnapshot) else dict(snap)
    payload.setdefault("kind", "rotation_coverage")
    payload.setdefault("review_only", True)
    payload.setdefault("writes_target", False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def last_hit_state(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    for ev in reversed(events):
        hs = ev.get("hit_state")
        if isinstance(hs, dict):
            out: dict[str, int] = {}
            for k, v in hs.items():
                try:
                    out[str(k)] = int(v)
                except (TypeError, ValueError):
                    continue
            return out
    return {}


def summarize_rotation(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate P1/P2 over sell-day events only."""
    sell_days = [e for e in events if e.get("sell_tickers")]
    if not sell_days:
        return {
            "n_sell_days": 0,
            "p1_hat": None,
            "p2_hat": None,
            "p2_given_p1": None,
            "median_n_eligible": None,
            "review_only": True,
        }
    p1s = [1.0 if e.get("p1") else 0.0 for e in sell_days]
    p2s = [1.0 if e.get("p2") else 0.0 for e in sell_days]
    p1_hat = sum(p1s) / len(p1s)
    p2_hat = sum(p2s) / len(p2s)
    p1_pos = [e for e in sell_days if e.get("p1")]
    p2_g = (
        sum(1.0 if e.get("p2") else 0.0 for e in p1_pos) / len(p1_pos) if p1_pos else None
    )
    ns = sorted(int(e.get("n_eligible") or 0) for e in sell_days)
    mid = ns[len(ns) // 2]
    return {
        "n_sell_days": len(sell_days),
        "p1_hat": round(p1_hat, 4),
        "p2_hat": round(p2_hat, 4),
        "p2_given_p1": None if p2_g is None else round(p2_g, 4),
        "median_n_eligible": mid,
        "as_of_first": str(sell_days[0].get("as_of") or ""),
        "as_of_last": str(sell_days[-1].get("as_of") or ""),
        "review_only": True,
        "writes_target": False,
    }


def _apply_held_mask(
    names: Sequence[RotationNameInput],
    *,
    weights: Mapping[str, Any] | None,
    sell_tickers: Sequence[str],
) -> list[RotationNameInput]:
    held_set = {norm_ticker(t) for t in sell_tickers if norm_ticker(t)}
    if weights:
        held_set |= {
            norm_ticker(k) for k, v in weights.items() if float(v or 0) > 1e-12
        }
    if not held_set:
        return list(names)
    return [
        RotationNameInput(
            ticker=n.ticker,
            total_score=n.total_score,
            is_held=n.is_held or n.ticker in held_set,
            has_target=n.has_target,
            price_below_target=n.price_below_target,
            eligible_gate=n.eligible_gate,
        )
        for n in names
    ]


def maybe_record_from_shadow_day(
    root: Path,
    *,
    market: object | None,
    as_of: str,
    day: Mapping[str, Any],
    rows: Sequence[Any],
    gap_req_pct: float = 20.0,
    hits_req: int = 2,
    persist: bool = True,
) -> RotationSnapshot | None:
    """Update consecutive gap hits every day; append P1/P2 jsonl on sell days only."""
    events = day.get("events") or []
    sells = [e for e in events if isinstance(e, dict) and str(e.get("kind")) in SELL_KINDS]
    sell_tickers = [norm_ticker(e.get("ticker")) for e in sells if norm_ticker(e.get("ticker"))]

    hit_path = rotation_hit_state_path(root, market)
    prior = load_hit_state_file(hit_path)
    names = _apply_held_mask(
        names_from_rows(rows),
        weights=day.get("weights") if isinstance(day.get("weights"), dict) else None,
        sell_tickers=sell_tickers,
    )
    snap = snapshot_coverage(
        names,
        as_of=as_of,
        sell_events=sells,
        gap_req_pct=gap_req_pct,
        hits_req=hits_req,
        prior_hits=prior,
    )
    if persist:
        save_hit_state_file(hit_path, snap.hit_state)
        if sells:
            append_rotation_event(rotation_log_path(root, market), snap)
            return snap
        return None
    return snap if sells else None
