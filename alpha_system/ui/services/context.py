"""Dashboard data context — alpha_system direct import, no API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd
import yaml

from alpha_system.entry.evaluate import TriggerSnapshot, evaluate_entry
from alpha_system.entry.models import TrancheState
from alpha_system.exit.evaluate import ExitSnapshot, PositionView, evaluate_exits
from alpha_system.journal import ensure_journal_hydrated, list_discretionary_warnings, list_entries
from alpha_system.loader import load_config
from alpha_system.schema import AlphaSystemConfig, TrancheId
from alpha_system.scoring.engine import NameScore, score_name
from alpha_system.sizing.allocate import allocate_tranche
from alpha_system.sizing.sector_map import load_sector_groups
from alpha_system.swap.observe import SwapObserveInput, evaluate_swap_observe
from alpha_system.ui.services.action_queue import ActionItem, build_action_queue
from alpha_system.ui.services.data_freshness import SourceStatus, inspect_sources
from alpha_system.ui.services.runtime_state import RuntimeState, sync_runtime_from_journal
from alpha_system.ui.services.t3_pbr import T3PbrStatus, load_t3_pbr_status
from alpha_system.ui.services.ui_copy import copy_get


@dataclass
class PortfolioRow:
    ticker: str
    name: str
    weight_pct: float
    initial_weight_pct: Optional[float]
    avg_price: Optional[float]
    current_price: Optional[float]
    target_price: Optional[float]
    target_progress: Optional[float]
    """0~100+: 집행단가→목표가 사이 현재가 위치(%)."""
    remaining_upside_pct: Optional[float]
    """목표가까지 남은 상승률(%). None = 목표가 없음."""
    has_target: bool
    target_detail: str
    cap_pct: float
    cap_headroom_pct: Optional[float]
    cap_near: bool
    """market_value_cap 대비 여유 5%p 미만(≥30% when cap=35)."""
    cap_over: bool = False
    """weight >= market_value_cap → 감축 신호."""
    target_gap_kind: str = "none"
    """none | legacy_pending | rule_violation — 목표가 부재 시 구분 (P4)."""
    price_progress_pct: Optional[float] = None
    """바 채움용 (음수 가능 — 손실 구간)."""
    tranche_source: str = "T1"
    total_score: Optional[float] = None
    sector: str = ""
    current_pbr: Optional[float] = None
    pbr_max: Optional[float] = None
    ops_signal: str = ""
    """hold | trim | review | missing — ops-book operator cue (Review-only)."""
    ops_signal_label: str = ""
    """유지 | 줄이기 | 검토 | 목표없음"""
    ops_signal_detail: str = ""
    ops_trim_pct: Optional[int] = None
    """Suggested partial trim percent when ops_signal=trim."""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreboardRow:
    ticker: str
    name: str
    total_score: Optional[float]
    score_q: Optional[float]
    score_v: Optional[float]
    score_sr: Optional[float]
    score_r: Optional[float]
    cecs: Optional[float]
    eligibility: Optional[bool]
    sector_peer_fallback: bool
    is_held: bool
    status: str
    # Normalized concentration key (= sector_group from KRX mapping).
    sector: str = ""


@dataclass
class DashboardContext:
    root: Path
    data_dir: Path
    cfg: AlphaSystemConfig
    as_of: date
    runtime: RuntimeState
    entry_eval: Any
    exit_eval: Any
    swap_eval: Any
    action_queue: list[ActionItem]
    source_status: list[SourceStatus]
    t3_pbr: T3PbrStatus
    portfolio_rows: list[PortfolioRow]  # proposal_book (screen / Review-only)
    ops_portfolio_rows: list[PortfolioRow]  # ops_book (positions.csv holdings)
    scoreboard_rows: list[ScoreboardRow]
    cecs_final_count: int
    cecs_total: int
    sector_peer_fallback_count: int
    gate_pass_count: int
    discretionary_count: int
    execution_rate_pct: Optional[float]
    held_kr_alpha: int  # ops_book holding count
    proposal_count: int  # proposal_book name count
    target_kr_alpha: int
    window_end: date
    t4_days_remaining: int
    event_labels: dict[str, str]
    pre_launch: bool = True
    effective_go_live: Optional[date] = None
    checklist: Any = None


EVENT_LABELS = {
    "commercial_code_enforcement_decrees": "상법 시행령·시행규칙 확정",
    "msci_dm_index_inclusion_confirmed": "MSCI DM 지수 편입 확정",
    "ifrs18_domestic_adoption_schedule_confirmed": "IFRS18 국내 도입 일정 확정",
}


def _paths(root: Path) -> dict[str, Path]:
    return {
        "journal": root / "data" / "alpha_system_journal.jsonl",
        "runtime": root / "data" / "alpha_dashboard_runtime.json",
        "dashboard_cfg": root / "alpha_system" / "config" / "dashboard.yaml",
        "system_cfg": root / "alpha_system" / "config" / "alpha_system.yaml",
        "positions": root / "data" / "positions.csv",
        "targets": root / "data" / "target_portfolio.csv",
        "prices": root / "data" / "prices.csv",
        "fundamentals": root / "data" / "fundamentals.csv",
        "cecs": root / "data" / "cecs_manual_scoring_template.csv",
        "alpha_scores": root / "alpha_portfolio" / "data" / "output" / "alpha_scores.csv",
        "sector_gate": root / "data" / "sector_coverage_gate_pass.json",
        "exit_targets": root / "data" / "kr_alpha_exit_targets.yaml",
        "quant_provenance": root / "data" / "alpha_quant_snapshot_provenance.json",
    }


def load_context(root: Path | None = None, *, as_of: date | None = None) -> DashboardContext:
    root = root or Path(__file__).resolve().parents[3]
    paths = _paths(root)
    as_of = as_of or date.today()
    ensure_journal_hydrated(paths["journal"])
    runtime = RuntimeState.load(paths["runtime"])
    runtime = sync_runtime_from_journal(runtime, paths["journal"])
    cfg = load_config(paths["system_cfg"])

    effective_go_live = cfg.go_live_date or runtime.effective_go_live()
    pre_launch = effective_go_live is None
    from alpha_system.ui.services.go_live_gate import assess_checklist

    checklist = assess_checklist(
        cfg, root=root, go_live_date=effective_go_live, cecs_path=paths["cecs"]
    )

    t3_band = cfg.tranches["T3"].valuation_band or {}
    t3_pbr = load_t3_pbr_status(
        root,
        bottom_percentile=float(t3_band.get("bottom_percentile", 20)),
        lookback_years=int(t3_band.get("lookback_years", 10)),
        today=as_of,
    )

    snap = TriggerSnapshot(
        as_of=as_of,
        system_started=not pre_launch,
        go_live_date=effective_go_live,
        events_fired=runtime.effective_events(),
        thesis_damage_flag=runtime.effective_thesis_damage(),
        kospi_pbr_in_bottom_band=t3_pbr.in_bottom_band,
        prior_states=runtime.prior_tranche_states(),
        prior_meta=runtime.prior_tranche_meta(),
    )
    entry_eval = evaluate_entry(cfg, snap, journal=False)

    # persist derived tranche states back
    for st in entry_eval.statuses:
        runtime.tranche_states[st.tranche_id] = st.state.value
        if st.meta:
            runtime.tranche_meta[st.tranche_id] = dict(st.meta)
    runtime.save_best_effort(paths["runtime"])

    positions_df = _read_csv(paths["positions"])
    targets_df = _read_csv(paths["targets"])
    prices_df = _read_csv(paths["prices"])
    fundamentals_df = _read_csv(paths["fundamentals"])
    cecs_df = _read_csv(paths["cecs"])
    scores_df = _read_csv(paths["alpha_scores"])

    kr_positions = positions_df[positions_df["asset_group"] == "kr_alpha"] if not positions_df.empty else positions_df
    kr_targets = targets_df[targets_df["asset_group"] == "kr_alpha"] if not targets_df.empty else targets_df

    # positions are read as dtype=str — never use Series.sum() (string concat).
    total_value = _sum_numeric(
        positions_df["current_value"] if "current_value" in positions_df.columns else None
    )

    scoreboard_rows, fallback_count = _build_scoreboard(
        cfg, cecs_df, scores_df, fundamentals_df, kr_positions, data_dir=root / "data"
    )

    pos_views: list[PositionView] = []
    for _, row in kr_positions.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6) if str(row.get("ticker", "")).isdigit() else str(row.get("ticker", ""))
        cur_val = _f(row.get("current_value")) or 0.0
        w = cur_val / total_value * 100 if total_value else 0.0
        sc = next((s for s in scoreboard_rows if s.ticker == ticker), None)
        pos_views.append(
            PositionView(
                ticker=ticker,
                name=str(row.get("name", "")),
                weight=w,
                total_score=sc.total_score if sc else None,
            )
        )

    exit_snap = ExitSnapshot(
        as_of=as_of,
        positions=pos_views,
        thesis_damage_flag=runtime.effective_thesis_damage(),
    )
    exit_eval = evaluate_exits(cfg, exit_snap, journal=False)

    swap_inputs = [
        SwapObserveInput(
            ticker=r.ticker,
            total_score=float(r.total_score or 0),
            is_held=r.is_held,
            eligible=r.eligibility is not False,
        )
        for r in scoreboard_rows
        if r.total_score is not None
    ]
    prior_hits = {tuple(k.split("|")): v for k, v in runtime.swap_hits.items() if "|" in k}
    swap_eval = evaluate_swap_observe(cfg, swap_inputs, as_of=as_of, prior_hits=prior_hits, journal=False)

    source_status = inspect_sources(root, dashboard_cfg_path=paths["dashboard_cfg"], today=as_of)
    stale = [s for s in source_status if s.stale]

    proposal_rows = _build_screen_portfolio(
        cfg,
        scoreboard_rows,
        prices_df,
        fundamentals_df,
        paths["exit_targets"],
    )
    from alpha_system.ui.services.proposal_freeze import load_freeze, pin_proposal_rows

    proposal_rows = pin_proposal_rows(proposal_rows, load_freeze(root))
    ops_rows = _build_ops_portfolio(
        cfg,
        kr_positions,
        total_value,
        scoreboard_rows,
        prices_df,
        fundamentals_df,
        paths["exit_targets"],
    )
    _enrich_ops_exit_signals(
        proposal_rows,
        proposal_tickers={r.ticker for r in proposal_rows},
        fundamentals_df=fundamentals_df,
        exit_targets_path=paths["exit_targets"],
        check_proposal_membership=False,
        as_of=as_of,
    )
    _enrich_ops_exit_signals(
        ops_rows,
        proposal_tickers={r.ticker for r in proposal_rows},
        fundamentals_df=fundamentals_df,
        exit_targets_path=paths["exit_targets"],
        check_proposal_membership=True,
        as_of=as_of,
    )
    proposal_n = len(proposal_rows)
    ops_n = len(ops_rows)
    target_n = (
        len(kr_targets)
        if not kr_targets.empty
        else int(cfg.sizing.target_names)
    )

    action_queue = build_action_queue(
        entry_eval=entry_eval,
        exit_eval=exit_eval,
        swap_eval=swap_eval,
        stale_sources=stale,
        cap_over_holdings=[
            (r.ticker, r.name, r.weight_pct, r.cap_pct)
            for r in ops_rows
            if r.cap_over
        ],
        pre_launch=pre_launch,
        checklist_blocking=checklist.blocking if pre_launch else [],
        window_end=cfg.thesis_window.window_end,
        pending_rescores=_load_pending_rescores(root),
    )
    # Basel thematic timeline — Review-only auto cues (no Core/target writes)
    if not pre_launch:
        try:
            from alpha_system.ui.services.action_queue import ActionSeverity
            from alpha_system.ui.services.basel_theme_board import build_basel_auto_cues

            _, basel_cues = build_basel_auto_cues(root, as_of=as_of, persist_log=True)
            for cue in basel_cues:
                sev = (
                    ActionSeverity.WARN
                    if cue.severity == "warn"
                    else ActionSeverity.INFO
                )
                action_queue.append(
                    ActionItem(
                        key=cue.key,
                        title=cue.title,
                        detail=cue.detail,
                        severity=sev,
                        source="basel_theme",
                        panel_kind="generic",
                        payload={"phase_ids": list(cue.phase_ids)},
                    )
                )
        except Exception:
            pass

    from alpha_system.ui.services.auto_journal import sync_system_journal

    sync_system_journal(
        as_of=as_of,
        runtime=runtime,
        entry_eval=entry_eval,
        portfolio_rows=ops_rows,
        pre_launch=pre_launch,
    )
    runtime.save_best_effort(paths["runtime"])

    cecs_final = 0
    cecs_total = 0
    if not cecs_df.empty and "status" in cecs_df.columns:
        cecs_total = len(cecs_df)
        cecs_final = int((cecs_df["status"] == "final").sum())

    gate_pass = 0
    if paths["sector_gate"].exists():
        import json

        gate_pass = int(json.loads(paths["sector_gate"].read_text(encoding="utf-8")).get("gate_pass", 0))

    executed_weight = sum(
        float(st.weight)
        for st in entry_eval.statuses
        if st.state in (TrancheState.EXECUTED, TrancheState.PARTIAL_EXECUTED)
    )
    execution_rate = round(executed_weight * 100, 1) if entry_eval.statuses else None

    go_live = effective_go_live
    t4_rules = cfg.tranches["T4"].hybrid_rules or {}
    t4_months = int(t4_rules.get("months_after_go_live", 12))
    if go_live is None:
        t4_days = 0
    else:
        t4_anchor = go_live + timedelta(days=int(t4_months * 30.44))
        t4_days = max(0, (t4_anchor - as_of).days)

    return DashboardContext(
        root=root,
        data_dir=paths["journal"].parent,
        cfg=cfg,
        as_of=as_of,
        runtime=runtime,
        entry_eval=entry_eval,
        exit_eval=exit_eval,
        swap_eval=swap_eval,
        action_queue=action_queue,
        source_status=source_status,
        t3_pbr=t3_pbr,
        portfolio_rows=proposal_rows,
        ops_portfolio_rows=ops_rows,
        scoreboard_rows=scoreboard_rows,
        cecs_final_count=cecs_final,
        cecs_total=cecs_total,
        sector_peer_fallback_count=fallback_count,
        gate_pass_count=gate_pass,
        discretionary_count=len(list_discretionary_warnings()),
        execution_rate_pct=execution_rate,
        held_kr_alpha=ops_n,
        proposal_count=proposal_n,
        target_kr_alpha=target_n,
        window_end=cfg.thesis_window.window_end,
        t4_days_remaining=t4_days,
        event_labels=EVENT_LABELS,
        pre_launch=pre_launch,
        effective_go_live=effective_go_live,
        checklist=checklist,
    )


def try_reverse_execution(ctx: DashboardContext, tranche_id: str) -> str:
    """Hard rule: show block reason on attempt (never hide button)."""
    from alpha_system.entry.hard_rules import block_reverse_execution
    from alpha_system.ui.services.ui_copy import copy_get

    st_status = next((s for s in ctx.entry_eval.statuses if s.tranche_id == tranche_id), None)
    if st_status is None:
        return copy_get("judgment", "fallback", default="판정 사유 확인 필요")
    act = block_reverse_execution(
        cfg=ctx.cfg,
        tranche_id=tranche_id,  # type: ignore[arg-type]
        state=st_status.state,
        trigger_met=False,
        weight=st_status.weight,
        as_of=ctx.as_of,
    )
    if act is None:
        return copy_get("hard_rule", "reverse_blocked", why="차단 규칙 비활성")
    return copy_get("hard_rule", "reverse_blocked", why=act.reason)


def _load_pending_rescores(root: Path) -> list[dict[str, Any]]:
    from alpha_system.scoring.pending_rescore import load_pending, pending_path

    return load_pending(pending_path(root))


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str)


def _build_scoreboard(
    cfg: AlphaSystemConfig,
    cecs_df: pd.DataFrame,
    scores_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    kr_positions: pd.DataFrame,
    *,
    data_dir: Path | None = None,
) -> tuple[list[ScoreboardRow], int]:
    """Build scoreboard from alpha_scores.csv factors + CECS finals (same as dry CLI)."""
    if cecs_df.empty:
        return [], 0
    held_set = (
        set(kr_positions["ticker"].astype(str).str.zfill(6))
        if not kr_positions.empty and "ticker" in kr_positions.columns
        else set()
    )
    rows: list[ScoreboardRow] = []
    fallback_count = 0
    scores_idx = _index_alpha_scores(scores_df)
    del fundamentals_df  # factors come only from alpha_scores (dry parity)
    sector_map = load_sector_groups(str((data_dir or Path("data")).resolve())) if data_dir else {}

    for _, r in cecs_df.iterrows():
        ticker = str(r.get("ticker", "")).zfill(6)
        name = str(r.get("name", "") or "")
        status = str(r.get("status", "draft") or "draft").strip().lower()
        if status != "final" and cfg.scoring.score_cutoff is not None:
            continue

        factor = scores_idx.get(ticker)
        q = v = sr = rr = None
        gate_ok = False
        if factor is not None:
            q = _f(factor.get("score_q"))
            v = _f(factor.get("score_v"))
            sr = _f(factor.get("score_sr"))
            rr = _f(factor.get("score_r"))
            gate_ok = _as_bool(factor.get("gate_pass"), default=True)
            if not name:
                name = str(factor.get("name") or "")

        cecs_val = _f(r.get("cecs_computed"))
        cecs_inputs = None
        if cecs_val is None:
            cecs_inputs = _cecs_inputs_from_row(r, ticker=ticker, name=name)

        total: Optional[float] = None
        elig: Optional[bool] = None
        # Match dry CLI: missing alpha_scores row or gate fail → not scored eligible.
        if factor is None:
            elig = False
        elif not gate_ok:
            elig = False
        elif cecs_val is None and cecs_inputs is None:
            elig = False
        else:
            try:
                ns = score_name(
                    ticker=ticker,
                    name=name,
                    score_q=q,
                    score_v=v,
                    score_sr=sr,
                    score_r=rr,
                    cecs=cecs_val,
                    cecs_inputs=cecs_inputs,
                    system_cfg=cfg,
                )
                total = ns.total_score
                elig = ns.eligibility
                cecs_val = _f((ns.factors or {}).get("cecs")) or cecs_val
            except Exception:
                total = None
                elig = False

        fb = False
        if factor is not None and "sector_peer_fallback" in factor.index:
            raw_fb = factor.get("sector_peer_fallback")
            fb = bool(raw_fb) if pd.notna(raw_fb) else False
        elif "sector_peer_fallback" in r.index:
            raw_fb = r.get("sector_peer_fallback")
            fb = bool(raw_fb) if pd.notna(raw_fb) else False
        if fb:
            fallback_count += 1
        sector = str(sector_map.get(ticker, "") or "")
        rows.append(
            ScoreboardRow(
                ticker=ticker,
                name=name,
                total_score=total,
                score_q=q,
                score_v=v,
                score_sr=sr,
                score_r=rr,
                cecs=cecs_val,
                eligibility=elig,
                sector_peer_fallback=fb,
                is_held=ticker in held_set,
                status=status,
                sector=sector,
            )
        )
    rows.sort(key=lambda x: (x.total_score is None, -(x.total_score or 0)))
    return rows, fallback_count


def _index_alpha_scores(scores_df: pd.DataFrame) -> dict[str, pd.Series]:
    if scores_df.empty or "ticker" not in scores_df.columns:
        return {}
    out: dict[str, pd.Series] = {}
    for _, row in scores_df.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        if ticker and ticker not in out:
            out[ticker] = row
    return out


def _cecs_inputs_from_row(
    row: pd.Series, *, ticker: str, name: str
) -> Optional[Any]:
    from alpha_system.scoring.cecs import CatalystInputs

    keys = (
        "execution_continuity",
        "pension_flow_score",
        "investment_purpose_flag",
    )
    values = {key: _f(row.get(key)) for key in keys}
    if any(value is None for value in values.values()):
        return None
    return CatalystInputs(
        ticker=ticker,
        name=name,
        execution_continuity=float(values["execution_continuity"]),
        pension_flow_score=float(values["pension_flow_score"]),
        investment_purpose_flag=float(values["investment_purpose_flag"]),
        policy_dependency_flag=float(_f(row.get("policy_dependency_flag")) or 0.0),
    )


def _as_bool(val: Any, *, default: bool = False) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    if isinstance(val, bool):
        return val
    text = str(val).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n"}:
        return False
    return default


def _fund_val(fund_idx: pd.DataFrame, ticker: str) -> Optional[float]:
    if fund_idx.empty or ticker not in fund_idx.index:
        return None
    row = fund_idx.loc[ticker]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    pbr = _f(row.get("pbr"))
    if pbr is None or pbr <= 0:
        return None
    return max(0.0, min(100.0, 100.0 - pbr * 10))


def _fund(fund_idx: pd.DataFrame, ticker: str, col: str) -> Optional[float]:
    if fund_idx.empty or ticker not in fund_idx.index:
        return None
    row = fund_idx.loc[ticker]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return _f(row.get(col))


def _f(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _sum_numeric(series) -> float:
    """Sum a CSV column read as dtype=str without string-concatenation."""
    if series is None:
        return 0.0
    try:
        if getattr(series, "empty", False):
            return 0.0
    except Exception:
        return 0.0
    return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())


def _build_ops_portfolio(
    cfg: AlphaSystemConfig,
    kr_positions: pd.DataFrame,
    total_value: float,
    scores: list[ScoreboardRow],
    prices_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    exit_targets_path: Path,
) -> list[PortfolioRow]:
    """Build ops_book from actual kr_alpha holdings (purchase weights)."""
    del total_value  # weights are sleeve-relative inside _build_portfolio
    rows = _build_portfolio(
        cfg,
        kr_positions,
        pd.DataFrame(),
        prices_df,
        fundamentals_df,
        scores,
        exit_targets_path,
    )
    for row in rows:
        row.extra = {**(row.extra or {}), "book": "ops"}
    return rows


def _enrich_ops_exit_signals(
    rows: list[PortfolioRow],
    *,
    proposal_tickers: set[str],
    fundamentals_df: pd.DataFrame,
    exit_targets_path: Path,
    check_proposal_membership: bool = True,
    as_of: date | None = None,
) -> None:
    """Attach 유지/줄이기/환금/전량 cues (display only)."""
    if not rows:
        return
    from alpha_system.ui.services.ops_exit_signal import apply_ops_exit_signals
    from src.alpha.take_profit_thesis import load_exit_targets

    bundle = load_exit_targets(exit_targets_path)
    fund_by: dict[str, dict[str, Any]] = {}
    if not fundamentals_df.empty and "ticker" in fundamentals_df.columns:
        for _, fr in fundamentals_df.iterrows():
            t = str(fr.get("ticker", "")).zfill(6)
            fund_by[t] = fr.to_dict()
    apply_ops_exit_signals(
        rows,
        proposal_tickers=proposal_tickers,
        fundamentals_by_ticker=fund_by,
        exit_tickers=bundle.get("tickers") or {},
        defaults=bundle.get("defaults") or {},
        check_proposal_membership=check_proposal_membership,
        as_of=as_of,
    )


def _build_screen_portfolio(
    cfg: AlphaSystemConfig,
    scores: list[ScoreboardRow],
    prices_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    exit_targets_path: Path,
) -> list[PortfolioRow]:
    """Build proposal_book from screened eligible names only (Policy B).

    Purchase weights from positions.csv are intentionally excluded.
    Proposed weights come from allocate_tranche; target_portfolio.csv is not written.
    """
    name_scores = _name_scores_from_board(scores)
    if not name_scores:
        return []

    from alpha_system.ui.services.alpha_book_ops import (
        equal_equity_weights,
        load_alpha_book_ops,
    )

    # root is not on cfg — use exit path parent.parent or default
    root_guess = exit_targets_path.parent.parent if exit_targets_path else Path(".")
    policy = load_alpha_book_ops(root_guess)
    # Candidate count = sizing.target_names (portfolio UI / yaml). Do not
    # override with alpha_book_ops default (that file is 9:1 weight policy).
    allocation = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T1,
        scores=name_scores,
        existing_weights={},
        tranche_budget=float(policy.equity_share),
    )
    selected = [
        item for item in allocation.allocated if item.incremental_weight > 0
    ]
    if not selected:
        return []

    # Literature ops: rank by score, weight equal within equity sleeve
    if policy.equity_weight_mode == "equal":
        each = equal_equity_weights(len(selected), equity_share=policy.equity_share)
        from alpha_system.sizing.allocate import NameAllocation

        selected = [
            NameAllocation(
                ticker=a.ticker,
                weight_input=a.weight_input,
                incremental_weight=each,
                total_weight_after=each,
                capped=False,
            )
            for a in selected
        ]
    score_map = {str(s.ticker).zfill(6): s for s in scores}
    exit_yaml: dict[str, Any] = {}
    if exit_targets_path.exists():
        with exit_targets_path.open(encoding="utf-8") as handle:
            exit_yaml = yaml.safe_load(handle) or {}

    price_idx = pd.DataFrame()
    if not prices_df.empty and "ticker" in prices_df.columns:
        work = prices_df.copy()
        work["ticker"] = work["ticker"].astype(str).str.zfill(6)
        # Keep latest row per ticker if duplicates exist
        if "date" in work.columns:
            work = work.sort_values("date")
        price_idx = work.drop_duplicates("ticker", keep="last").set_index("ticker")

    fund_by_ticker: dict[str, dict[str, Any]] = {}
    if not fundamentals_df.empty and "ticker" in fundamentals_df.columns:
        for _, fr in fundamentals_df.iterrows():
            t = str(fr.get("ticker", "")).zfill(6)
            fund_by_ticker[t] = fr.to_dict()

    rows: list[PortfolioRow] = []
    cap = float(cfg.sizing.market_value_cap) * 100.0
    from alpha_system.ui.services.portfolio_metrics import classify_cap_tone

    for item in selected:
        ticker = str(item.ticker).zfill(6)
        sc = score_map.get(ticker) or score_map.get(item.ticker)
        name = sc.name if sc else item.ticker
        weight = round(item.incremental_weight * 100.0, 2)
        cur_p = None
        if not price_idx.empty and ticker in price_idx.index:
            cur_p = _f(
                price_idx.loc[ticker].get("close")
                or price_idx.loc[ticker].get("price")
            )
        fund_row = fund_by_ticker.get(ticker, {})
        current_pbr = _f(fund_row.get("pbr"))
        ticker_targets = (exit_yaml.get("tickers") or {}).get(ticker) or {}
        if not ticker_targets:
            # YAML keys may be unpadded
            ticker_targets = (exit_yaml.get("tickers") or {}).get(item.ticker) or {}
        has_target = bool(ticker_targets)
        pbr_max = None
        yaml_target_px = None
        approved_as_of = ""
        revalidate_required = False
        revalidate_reason = ""
        if isinstance(ticker_targets, dict):
            pbr_max = _f((ticker_targets.get("valuation") or {}).get("pbr_max"))
            yaml_target_px = _f(ticker_targets.get("target_price"))
            approved_as_of = str(ticker_targets.get("approved_as_of") or "").strip()
            revalidate_required = bool(ticker_targets.get("revalidate_required"))
            revalidate_reason = str(ticker_targets.get("revalidate_reason") or "").strip()

        target_price: Optional[float] = None
        remaining_upside: Optional[float] = None
        price_progress: Optional[float] = None
        target_gap_kind = "none"
        target_detail = ""
        progress_legacy: Optional[float] = None

        if not has_target:
            target_gap_kind = "screen_pending"
            target_detail = copy_get(
                "portfolio",
                "target_missing_screen",
                default="목표가 없음 — 다음 주 통합 보고서(E)까지 대기 · 편입 차단",
            )
        elif has_target and cur_p and current_pbr and current_pbr > 0 and pbr_max and pbr_max > 0:
            target_price = round(cur_p * (pbr_max / current_pbr), 0)
            remaining_upside = round((target_price / cur_p - 1.0) * 100.0, 1)
            price_progress = min(100.0, max(0.0, (current_pbr / pbr_max) * 100.0))
            target_detail = f"PBR 목표 {pbr_max:.2f} (현재 {current_pbr:.2f})"
            progress_legacy = price_progress
        elif has_target and cur_p and yaml_target_px and yaml_target_px > 0:
            target_price = yaml_target_px
            remaining_upside = round((target_price / cur_p - 1.0) * 100.0, 1)
            price_progress = round(min(100.0, max(0.0, (cur_p / target_price) * 100.0)), 1)
            target_detail = f"목표가 {target_price:,.0f}"
            progress_legacy = price_progress
        elif has_target and not cur_p:
            target_price = yaml_target_px
            target_gap_kind = "price_missing"
            target_detail = copy_get(
                "portfolio",
                "price_missing_signal_invalid",
                default="데이터 없음 — 신호 무효 (가격 확인)",
            )
        elif has_target and cur_p:
            target_price = yaml_target_px
            target_detail = "목표 평가 대기"

        if approved_as_of:
            target_detail = (
                f"{target_detail} · 승인 {approved_as_of}".strip(" ·")
                if target_detail
                else f"승인 {approved_as_of}"
            )
        if revalidate_required:
            note = revalidate_reason or copy_get(
                "portfolio",
                "target_revalidate_required",
                default="목표가 재검증 필요",
            )
            target_detail = f"{target_detail} · ⚠ {note}".strip(" ·")

        headroom = round(cap - weight, 2) if cap else None
        tone = classify_cap_tone(weight, cap)
        rows.append(
            PortfolioRow(
                ticker=ticker,
                name=name,
                weight_pct=weight,
                initial_weight_pct=weight,
                avg_price=None,
                current_price=cur_p,
                target_price=target_price,
                target_progress=progress_legacy,
                remaining_upside_pct=remaining_upside,
                has_target=has_target,
                target_detail=target_detail,
                target_gap_kind=target_gap_kind,
                cap_pct=cap,
                cap_headroom_pct=headroom,
                cap_near=tone == "warn",
                cap_over=tone == "danger",
                price_progress_pct=price_progress,
                tranche_source="SCREEN",
                total_score=sc.total_score if sc else item.weight_input,
                sector=(sc.sector if sc and sc.sector else str(fund_row.get("sector", "") or "")),
                current_pbr=current_pbr,
                pbr_max=pbr_max,
                extra={
                    "book": "proposal",
                    "selection_policy": "B",
                    "approved_as_of": approved_as_of,
                    "revalidate_required": revalidate_required,
                    "revalidate_reason": revalidate_reason,
                },
            )
        )
    rows.sort(key=lambda r: (-(r.total_score or 0), -r.weight_pct, r.ticker))
    return rows


def _name_scores_from_board(scores: Sequence[ScoreboardRow]) -> list[NameScore]:
    out: list[NameScore] = []
    for row in scores:
        if row.eligibility is not True or row.total_score is None:
            continue
        total = float(row.total_score)
        out.append(
            NameScore(
                ticker=row.ticker,
                name=row.name,
                factors={
                    "score_q": float(row.score_q) if row.score_q is not None else float("nan"),
                    "score_v": float(row.score_v) if row.score_v is not None else float("nan"),
                    "score_sr": float(row.score_sr) if row.score_sr is not None else float("nan"),
                    "score_r": float(row.score_r) if row.score_r is not None else float("nan"),
                    "cecs": float(row.cecs) if row.cecs is not None else float("nan"),
                },
                total_score=total,
                eligibility=True,
                weight_input=total,
                eligibility_reason="scoreboard eligible",
                sector=str(getattr(row, "sector", "") or ""),
            )
        )
    return out


def _build_portfolio(
    cfg: AlphaSystemConfig,
    kr_positions: pd.DataFrame,
    kr_targets: pd.DataFrame,
    prices_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    scores: list[ScoreboardRow],
    exit_targets_path: Path,
) -> list[PortfolioRow]:
    """Legacy positions-based book (kept for tests; UI uses _build_screen_portfolio)."""
    if kr_positions.empty:
        return []
    total = _sum_numeric(kr_positions["current_value"]) if "current_value" in kr_positions.columns else 0.0
    price_idx = (
        prices_df.set_index("ticker")
        if not prices_df.empty and "ticker" in prices_df.columns
        else pd.DataFrame()
    )
    target_idx = kr_targets.set_index("ticker") if not kr_targets.empty else pd.DataFrame()
    score_map = {s.ticker: s for s in scores}
    exit_yaml: dict[str, Any] = {}
    if exit_targets_path.exists():
        with exit_targets_path.open(encoding="utf-8") as handle:
            exit_yaml = yaml.safe_load(handle) or {}

    formal_entry = _tickers_with_formal_entry()

    fund_by_ticker: dict[str, dict[str, Any]] = {}
    if not fundamentals_df.empty and "ticker" in fundamentals_df.columns:
        for _, fr in fundamentals_df.iterrows():
            t = str(fr.get("ticker", "")).zfill(6)
            fund_by_ticker[t] = fr.to_dict()

    rows: list[PortfolioRow] = []
    cap = float(cfg.sizing.market_value_cap) * 100.0

    for _, pos in kr_positions.iterrows():
        ticker = str(pos.get("ticker", "")).zfill(6)
        name = str(pos.get("name", ""))
        cur_val = _f(pos.get("current_value")) or 0.0
        weight = cur_val / total * 100 if total else 0.0
        init_w = None
        if ticker in target_idx.index:
            init_w = _f(target_idx.loc[ticker].get("target_weight"))
        avg_p = _f(pos.get("avg_price"))
        cur_p = _f(pos.get("current_price"))
        if cur_p is None and not price_idx.empty and ticker in price_idx.index:
            cur_p = _f(price_idx.loc[ticker].get("close") or price_idx.loc[ticker].get("price"))

        fund_row = fund_by_ticker.get(ticker, {})
        current_pbr = _f(fund_row.get("pbr"))
        ticker_targets = (exit_yaml.get("tickers") or {}).get(ticker) or {}
        has_target = bool(ticker_targets)
        pbr_max = None
        if isinstance(ticker_targets, dict):
            pbr_max = _f((ticker_targets.get("valuation") or {}).get("pbr_max"))

        target_price: Optional[float] = None
        remaining_upside: Optional[float] = None
        price_progress: Optional[float] = None
        target_gap_kind = "none"
        target_detail = ""
        progress_legacy: Optional[float] = None

        if not has_target:
            if ticker in formal_entry:
                target_gap_kind = "rule_violation"
                target_detail = copy_get(
                    "portfolio",
                    "target_missing_violation",
                    default="목표가 없음 — 편입 규칙 위반",
                )
            else:
                target_gap_kind = "legacy_pending"
                target_detail = copy_get(
                    "portfolio",
                    "target_missing_legacy",
                    default="목표가 없음 — 레거시 보유, 이행 심사 대기",
                )
        elif has_target and cur_p and current_pbr and current_pbr > 0 and pbr_max and pbr_max > 0:
            target_price = round(cur_p * (pbr_max / current_pbr), 0)
            remaining_upside = round((target_price / cur_p - 1.0) * 100.0, 1)
            entry = avg_p if avg_p and avg_p > 0 else None
            if entry and target_price != entry:
                price_progress = (cur_p - entry) / (target_price - entry) * 100.0
            else:
                price_progress = min(100.0, max(0.0, (current_pbr / pbr_max) * 100.0))
            target_detail = f"PBR 목표 {pbr_max:.2f} (현재 {current_pbr:.2f})"
            progress_legacy = price_progress
        elif has_target and cur_p:
            try:
                from src.alpha.take_profit_thesis import assess_take_profit

                per_targets = ticker_targets if isinstance(ticker_targets, dict) else {}
                verdict = assess_take_profit(
                    ticker,
                    fundamentals=fund_row,
                    prices={"current_price": cur_p},
                    targets=per_targets,
                )
                target_detail = verdict.rationale or verdict.suggested_action
                progress_legacy = verdict.val_proximity_pct or verdict.fund_proximity_pct
                price_progress = progress_legacy
                remaining_upside = (
                    round(100.0 - float(progress_legacy), 1)
                    if progress_legacy is not None
                    else None
                )
            except Exception:
                target_detail = "목표 평가 불가"

        headroom = round(cap - weight, 2) if cap else None
        from alpha_system.ui.services.portfolio_metrics import classify_cap_tone

        tone = classify_cap_tone(weight, cap)
        sc = score_map.get(ticker)
        rows.append(
            PortfolioRow(
                ticker=ticker,
                name=name,
                weight_pct=round(weight, 2),
                initial_weight_pct=init_w,
                avg_price=avg_p,
                current_price=cur_p,
                target_price=target_price,
                target_progress=progress_legacy,
                remaining_upside_pct=remaining_upside,
                has_target=has_target,
                target_detail=target_detail,
                target_gap_kind=target_gap_kind,
                cap_pct=cap,
                cap_headroom_pct=headroom,
                cap_near=tone == "warn",
                cap_over=tone == "danger",
                price_progress_pct=price_progress,
                tranche_source="T1",
                total_score=sc.total_score if sc else None,
                sector=str(pos.get("sector", "")),
                current_pbr=current_pbr,
                pbr_max=pbr_max,
            )
        )
    rows.sort(key=lambda r: -r.weight_pct)
    return rows


_FORMAL_ENTRY_KINDS = frozenset(
    {
        "ENTRY_JOURNAL",
        "TRANCHE_EXEC_FILL",
        "EXECUTE",
    }
)


def _tickers_with_formal_entry() -> set[str]:
    """Tickers that went through the new-system entry path (journal evidence)."""
    out: set[str] = set()
    for e in list_entries():
        if e.action_kind not in _FORMAL_ENTRY_KINDS:
            continue
        sub = str(e.subject or "").strip()
        if sub.isdigit():
            out.add(sub.zfill(6))
        elif sub:
            out.add(sub)
    return out
