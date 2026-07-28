from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.schemas import UniverseRecord
from src.alpha.universe_filter import filter_universe
from src.value_list.ticker_registry import hakedaka_meta_by_ticker, load_integration_config


@dataclass
class OverlapDiagnosticRow:
    ticker: str
    name: str
    hakedaka_grade: str
    priority_bucket: str
    dart_verified: bool
    dart_signal: str
    qvm_score: float | None
    qvm_rank: int | None
    qvm_grade: str
    fail_reason: str
    liquidity_pass: bool
    financial_pass: bool
    momentum_pass: bool | None
    in_scored_pool: bool
    in_shortlist: bool
    in_proposal: bool
    sector_cap_blocked: bool
    eligible_for_watch: bool
    eligible_for_portfolio: bool
    hakedaka_priority: bool
    shadow_slot_candidate: bool


def _pillar_pass(row: dict[str, Any], scoring_cfg: dict[str, Any]) -> bool:
    sel = scoring_cfg.get("selection", {})
    thresholds = sel.get(
        "min_pillar_score",
        {"quality": 60, "valuation": 55, "momentum": 55, "shareholder_return": 55},
    )
    floor = float(sel.get("min_all_pillar_floor", 45))
    min_pillars = int(sel.get("min_pillars_pass", 3))
    mapping = (
        ("quality_score", "quality"),
        ("valuation_score", "valuation"),
        ("momentum_score", "momentum"),
        ("shareholder_return_score", "shareholder_return"),
    )
    scores = [float(row.get(f, 0)) for f, _ in mapping]
    if min(scores) < floor:
        return False
    passed = sum(
        1 for f, key in mapping if float(row.get(f, 0)) >= float(thresholds.get(key, 55))
    )
    return passed >= min_pillars


def write_hakedaka_overlap_diagnostics(
    data_dir: Path,
    output_dir: Path,
    *,
    universe: list[UniverseRecord],
    excluded: list,
    graded: list[dict[str, Any]],
    shortlist_tickers: set[str],
    proposal_tickers: set[str],
    prices_by_ticker: dict[str, Any],
    filter_cfg: dict[str, Any],
    as_of: str,
    usable_fund_tickers: set[str],
    scoring_cfg: dict[str, Any],
) -> Path:
    cfg = load_integration_config(data_dir)
    meta = hakedaka_meta_by_ticker(data_dir)
    ex_by_ticker = {e.ticker: e for e in excluded}
    graded_by = {r["ticker"]: r for r in graded}
    sorted_graded = sorted(graded, key=lambda r: float(r.get("total_score", 0)), reverse=True)
    rank_map = {r["ticker"]: i + 1 for i, r in enumerate(sorted_graded)}

    import json

    ver_idx: dict[str, dict] = {}
    vpath = data_dir / "cache" / "hakedaka_dart_verification.json"
    if vpath.exists():
        ver_idx = {
            str(r["ticker"]).zfill(6): r
            for r in json.loads(vpath.read_text(encoding="utf-8")).get("rows", [])
        }

    _, fresh_excluded = filter_universe(universe, prices_by_ticker, filter_cfg, as_of)
    liq_rules = {"min_market_cap", "min_20d_trading_value", "min_60d_trading_value", "missing_price"}
    liq_fail = {e.ticker for e in fresh_excluded if e.failed_rule in liq_rules}

    port_cfg = cfg.get("portfolio_inclusion") or {}
    hard_slot = bool(port_cfg.get("hard_slot_enabled", False))

    rows: list[OverlapDiagnosticRow] = []
    for ticker, stock in sorted(meta.items(), key=lambda x: int(x[1].get("no", 0))):
        ex = ex_by_ticker.get(ticker)
        g = graded_by.get(ticker)
        ver = ver_idx.get(ticker, {})
        dart_verified = ver.get("verification_status") == "verified"
        liquidity_pass = ticker not in liq_fail and (ex is None or ex.failed_rule not in liq_rules)
        financial_pass = ticker in usable_fund_tickers
        in_scored = g is not None
        fail_parts: list[str] = []
        if ex:
            fail_parts.append(f"{ex.failed_rule}:{ex.exclude_reason}")
        if not financial_pass:
            fail_parts.append("missing_fundamentals")
        if not liquidity_pass:
            fail_parts.append("liquidity_fail")
        if g and not _pillar_pass(g, scoring_cfg):
            fail_parts.append("pillar_threshold")
        if g and str(g.get("grade", "")) == "Reject":
            fail_parts.append("qvm_reject")

        momentum_pass: bool | None = None
        if g:
            mom_thr = float(
                (scoring_cfg.get("selection", {}).get("min_pillar_score") or {}).get("momentum", 55)
            )
            momentum_pass = float(g.get("momentum_score", 0)) >= mom_thr

        in_sl = ticker in shortlist_tickers
        in_prop = ticker in proposal_tickers
        sector_blocked = False

        h_priority = bool(g and g.get("hakedaka_priority"))
        eligible_watch = bool(
            dart_verified or str(stock.get("grade", "")) in {"A", "B"}
        )
        eligible_portfolio = bool(
            in_sl
            and liquidity_pass
            and financial_pass
            and not hard_slot
            and (g and str(g.get("grade", "Reject")) != "Reject")
        )
        shadow = bool(
            cfg.get("shadow_slot_candidate_enabled", True)
            and h_priority
            and eligible_portfolio
            and not in_prop
            and port_cfg.get("max_hakedaka_soft_slots", 1) > 0
            and not hard_slot
        )

        rows.append(
            OverlapDiagnosticRow(
                ticker=ticker,
                name=str(stock.get("name", "")),
                hakedaka_grade=str(stock.get("grade", "")),
                priority_bucket=str(stock.get("priority_bucket", "")),
                dart_verified=dart_verified,
                dart_signal=str(ver.get("dart_signal", "")),
                qvm_score=round(float(g.get("qvm_pure_score", g["total_score"])), 2) if g else None,
                qvm_rank=rank_map.get(ticker),
                qvm_grade=str(g.get("grade", "")) if g else "",
                fail_reason=";".join(fail_parts) if fail_parts else ("ok" if in_sl else "not_in_shortlist"),
                liquidity_pass=liquidity_pass,
                financial_pass=financial_pass,
                momentum_pass=momentum_pass,
                in_scored_pool=in_scored,
                in_shortlist=in_sl,
                in_proposal=in_prop,
                sector_cap_blocked=sector_blocked,
                eligible_for_watch=eligible_watch,
                eligible_for_portfolio=eligible_portfolio,
                hakedaka_priority=h_priority,
                shadow_slot_candidate=shadow,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(r) for r in rows])
    path = output_dir / "hakedaka_overlap_diagnostics.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")

    if cfg.get("hakedaka_priority_display", True):
        elig = cfg.get("eligibility_for_priority") or {}
        min_grade = str((elig.get("required") or {}).get("qvm_grade_min", "B"))
        grade_order = {"A": 0, "B": 1, "C": 2, "W": 3, "Reject": 9}
        min_ord = grade_order.get(min_grade, 1)

        def _grade_ok(g: str) -> bool:
            return grade_order.get(str(g), 9) <= min_ord

        priority = df[
            (df["hakedaka_priority"].astype(str).str.lower() == "true")
            & (df["liquidity_pass"].astype(str).str.lower() == "true")
            & (df["dart_verified"].astype(str).str.lower() == "true")
            & df["qvm_grade"].map(_grade_ok)
        ]
        if not priority.empty:
            priority.to_csv(
                output_dir / "hakedaka_priority_review.csv",
                index=False,
                encoding="utf-8-sig",
            )
    return path
