"""Dashboard data context — alpha_system direct import, no API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import pandas as pd
import yaml

from alpha_system.entry.evaluate import TriggerSnapshot, evaluate_entry
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
from alpha_system.ui.services.t3_pbr import T3PbrStatus
from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.screen_book import (
    DEFAULT_MARKET,
    apply_book_config,
    ensure_book_dirs,
    operational_data_dir,
    alpha_data_dir,
    provenance_rel,
    normalize_market,
    resolve_quality_fundamentals_csv,
)


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
    eligibility_reason: str = ""


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
    screen_market: str = "KOSPI"
    proposal_blocked_rows: list[PortfolioRow] = field(default_factory=list)


EVENT_LABELS = {
    "commercial_code_enforcement_decrees": "상법 시행령·시행규칙 확정",
    "msci_dm_index_inclusion_confirmed": "MSCI DM 지수 편입 확정",
    "ifrs18_domestic_adoption_schedule_confirmed": "IFRS18 국내 도입 일정 확정",
}


def _paths(root: Path, market: str = "KOSPI") -> dict[str, Path]:
    data = operational_data_dir(root, market)
    alpha = alpha_data_dir(root, market)
    return {
        "journal": root / "data" / "alpha_system_journal.jsonl",
        "runtime": root / "data" / "alpha_dashboard_runtime.json",
        "dashboard_cfg": root / "alpha_system" / "config" / "dashboard.yaml",
        "system_cfg": root / "alpha_system" / "config" / "alpha_system.yaml",
        "positions": data / "positions.csv",
        "targets": data / "target_portfolio.csv",
        "prices": data / "prices.csv",
        "fundamentals": data / "fundamentals.csv",
        "cecs": root / "data" / "cecs_manual_scoring_template.csv",
        "alpha_scores": alpha / "output" / "alpha_scores.csv",
        "sector_gate": data / "sector_coverage_gate_pass.json",
        "exit_targets": data / "kr_alpha_exit_targets.yaml",
        "quant_provenance": root / provenance_rel(market),
        "overlay": data / "qual_rank_overlay.json",
    }


def load_context(
    root: Path | None = None,
    *,
    as_of: date | None = None,
    market: str | None = None,
) -> DashboardContext:
    root = root or Path(__file__).resolve().parents[3]
    screen_market = normalize_market(market or DEFAULT_MARKET)
    ensure_book_dirs(root, screen_market)
    paths = _paths(root, screen_market)
    as_of = as_of or date.today()
    ensure_journal_hydrated(paths["journal"])
    runtime = RuntimeState.load(paths["runtime"])
    runtime = sync_runtime_from_journal(runtime, paths["journal"])
    cfg = apply_book_config(load_config(paths["system_cfg"]), screen_market, root=root)

    effective_go_live = cfg.go_live_date or runtime.effective_go_live()
    pre_launch = effective_go_live is None
    from alpha_system.ui.services.go_live_gate import assess_checklist

    checklist = assess_checklist(
        cfg, root=root, go_live_date=effective_go_live, cecs_path=paths["cecs"]
    )

    t3_pbr = T3PbrStatus(
        available=False,
        current_pbr=None,
        percentile_10y=None,
        in_bottom_band=None,
        bottom_pct=20.0,
        as_of=None,
        source_note="capital T3 retired",
    )

    snap = TriggerSnapshot(
        as_of=as_of,
        system_started=not pre_launch,
        go_live_date=effective_go_live,
        events_fired=runtime.effective_events(),
        thesis_damage_flag=runtime.effective_thesis_damage(),
        kospi_pbr_in_bottom_band=None,
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
        cfg, cecs_df, scores_df, fundamentals_df, kr_positions, data_dir=paths["positions"].parent
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

    from src.alpha.price_ladder import load_lookback_lows
    from alpha_system.sizing.target_gate import (
        collect_above_justified_target_tickers_from_root,
        ops_proposal_membership,
    )

    lookback_lows = load_lookback_lows(root, prices_df)

    exit_yaml: dict[str, Any] = {}
    if paths["exit_targets"].exists():
        loaded = yaml.safe_load(paths["exit_targets"].read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            exit_yaml = loaded
    above_target = collect_above_justified_target_tickers_from_root(
        [str(s.ticker) for s in scoreboard_rows],
        root,
        prices_df=prices_df,
        fundamentals_df=fundamentals_df,
        exit_yaml=exit_yaml,
    )
    skip_reasons: dict[str, str] = {}
    proposal_rows = _build_screen_portfolio(
        cfg,
        scoreboard_rows,
        prices_df,
        fundamentals_df,
        paths["exit_targets"],
        lookback_lows=lookback_lows,
        overlay_path=paths["overlay"],
        exclude_tickers=above_target,
        root=root,
        data_dir=paths["positions"].parent,
        skip_reasons=skip_reasons,
    )
    from alpha_system.ui.services.proposal_freeze import load_freeze, pin_proposal_rows

    proposal_rows = pin_proposal_rows(proposal_rows, load_freeze(root))
    band_n = int(cfg.sizing.target_names)
    band_scores = proposal_band_scores(scoreboard_rows, target_n=band_n)
    already = {str(r.ticker).zfill(6) for r in proposal_rows}
    blocked_scores = [
        s for s in band_scores if str(s.ticker).zfill(6) not in already
    ]
    blocked_rows = _blocked_proposal_rows(
        blocked_scores,
        cfg=cfg,
        prices_df=prices_df,
        fundamentals_df=fundamentals_df,
        lookback_lows=lookback_lows,
        root=root,
        above_target=above_target,
        skip_reasons=skip_reasons,
        data_dir=paths["positions"].parent,
    )
    ops_rows = _build_ops_portfolio(
        cfg,
        kr_positions,
        total_value,
        scoreboard_rows,
        prices_df,
        fundamentals_df,
        paths["exit_targets"],
        lookback_lows=lookback_lows,
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
        proposal_tickers=ops_proposal_membership(
            [r.ticker for r in proposal_rows],
            held_tickers=[r.ticker for r in ops_rows],
            above_target=above_target,
        ),
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

    execution_rate = None
    t4_days = 0

    return DashboardContext(
        root=root,
        data_dir=paths["positions"].parent,
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
        screen_market=screen_market,
        proposal_blocked_rows=blocked_rows,
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
    """Build scoreboard from alpha_scores.csv. CECS overlay is optional (Ops A weight 0)."""
    if scores_df.empty or "ticker" not in scores_df.columns:
        return [], 0
    held_set = (
        set(kr_positions["ticker"].astype(str).str.zfill(6))
        if not kr_positions.empty and "ticker" in kr_positions.columns
        else set()
    )
    rows: list[ScoreboardRow] = []
    fallback_count = 0
    sector_map = load_sector_groups(str((data_dir or Path("data")).resolve())) if data_dir else {}
    fund_ok = _fund_quality_index(
        _quality_fund_for_gate(fundamentals_df, data_dir)
    )
    cecs_idx: dict[str, pd.Series] = {}
    if not cecs_df.empty and "ticker" in cecs_df.columns:
        for _, r in cecs_df.iterrows():
            tk = str(r.get("ticker", "")).zfill(6)
            if tk:
                cecs_idx[tk] = r

    for _, factor in scores_df.iterrows():
        ticker = str(factor.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        name = str(factor.get("name") or "")
        q = _f(factor.get("score_q"))
        v = _f(factor.get("score_v"))
        sr = _f(factor.get("score_sr"))
        rr = _f(factor.get("score_r"))
        gate_ok = _as_bool(factor.get("gate_pass"), default=True)
        quality_ok = _quality_inputs_ok(factor, fund_ok)
        cecs_row = cecs_idx.get(ticker)
        status = "final"
        cecs_val = None
        cecs_inputs = None
        if cecs_row is not None:
            status = str(cecs_row.get("status", "draft") or "draft").strip().lower()
            if not name:
                name = str(cecs_row.get("name") or "")
            cecs_val = _f(cecs_row.get("cecs_computed"))
            if cecs_val is None:
                cecs_inputs = _cecs_inputs_from_row(
                    cecs_row, ticker=ticker, name=name
                )

        total: Optional[float] = None
        elig: Optional[bool] = None
        elig_reason = ""
        if not gate_ok:
            elig = False
            elig_reason = "유동성 게이트 미통과"
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
                    quality_inputs_ok=quality_ok,
                    system_cfg=cfg,
                )
                total = ns.total_score
                elig = ns.eligibility
                elig_reason = str(ns.eligibility_reason or "")
                cecs_val = _f((ns.factors or {}).get("cecs")) or cecs_val
            except Exception:
                total = None
                elig = False
                elig_reason = "채점 실패"

        fb = False
        if "sector_peer_fallback" in factor.index:
            raw_fb = factor.get("sector_peer_fallback")
            fb = bool(raw_fb) if pd.notna(raw_fb) else False
        if fb:
            fallback_count += 1
        sector = str(sector_map.get(ticker, "") or factor.get("sector") or "")
        rows.append(
            ScoreboardRow(
                ticker=ticker,
                name=name or ticker,
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
                eligibility_reason=elig_reason,
            )
        )
    rows.sort(key=lambda x: (x.total_score is None, -(x.total_score or 0)))
    return rows, fallback_count


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


def _quality_fund_for_gate(
    ops_fund: pd.DataFrame, data_dir: Path | None
) -> pd.DataFrame:
    """Prefer collect-time ROE over the ops ledger (ops often has empty ROE)."""
    path = resolve_quality_fundamentals_csv(data_dir)
    if path is not None and path.exists():
        try:
            alpha = pd.read_csv(path, dtype=str)
        except (OSError, ValueError):
            alpha = pd.DataFrame()
        if not alpha.empty and "ticker" in alpha.columns:
            return alpha
    return ops_fund


def _fund_quality_index(fundamentals_df: pd.DataFrame) -> dict[str, bool] | None:
    """ticker → ROE present. None = no fundamentals file (do not assume missing)."""
    if fundamentals_df is None or fundamentals_df.empty or "ticker" not in fundamentals_df.columns:
        return None
    out: dict[str, bool] = {}
    for _, row in fundamentals_df.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        out[ticker] = _f(row.get("roe_3y_avg")) is not None or _f(row.get("roe")) is not None
    return out


def _blank_optional(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    return str(val).strip().lower() in {"", "nan", "none", "<na>"}


def _quality_inputs_ok(
    factor: pd.Series, fund_ok: dict[str, bool] | None
) -> bool | None:
    raw = factor.get("quality_inputs_ok") if "quality_inputs_ok" in factor.index else None
    if not _blank_optional(raw):
        return _as_bool(raw, default=False)
    if fund_ok is None:
        return None
    ticker = str(factor.get("ticker", "")).zfill(6)
    if ticker in fund_ok:
        return fund_ok[ticker]
    return None


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
    lookback_lows: dict | None = None,
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
        lookback_lows=lookback_lows,
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
    lookback_lows: dict | None = None,
    overlay_path: Path | None = None,
    exclude_tickers: set[str] | None = None,
    root: Path | None = None,
    data_dir: Path | None = None,
    skip_reasons: dict[str, str] | None = None,
) -> list[PortfolioRow]:
    """Build proposal_book from screened eligible names only (Policy B).

    Purchase weights from positions.csv are intentionally excluded.
    Proposed weights come from allocate_tranche; target_portfolio.csv is not written.
    Names already at/above justified take-profit are dropped (next eligible fills).
    """
    name_scores = _name_scores_from_board(scores)
    if not name_scores:
        return []

    from alpha_system.sizing.cyclical_theme import is_cyclical_heavy
    from alpha_system.sizing.hakedaka_screen import (
        evaluate_hakedaka,
        hakedaka_fail_tickers,
        hits_label,
        load_hakedaka_inputs,
    )
    from alpha_system.sizing.qual_overlay import load_qual_overlay
    from alpha_system.sizing.target_gate import collect_above_justified_target_tickers
    from alpha_system.ui.services.alpha_book_ops import (
        equal_equity_weights,
        load_alpha_book_ops,
    )
    from src.alpha.price_ladder import attach_ladder_extra, load_lookback_lows
    from src.alpha.quant_target_estimate import (
        load_alpha_template_fundamentals,
        quant_portfolio_extra,
    )

    root_guess = Path(root) if root is not None else (
        exit_targets_path.parent.parent if exit_targets_path else Path(".")
    )
    book_dir = Path(data_dir) if data_dir is not None else (
        exit_targets_path.parent if exit_targets_path else root_guess / "data"
    )
    alpha_fund_by = load_alpha_template_fundamentals(root_guess)
    if lookback_lows is None:
        lookback_lows = load_lookback_lows(root_guess, prices_df)
    policy = load_alpha_book_ops(root_guess)
    overlay = load_qual_overlay(
        overlay_path
        if overlay_path is not None
        else (root_guess / "data" / "qual_rank_overlay.json")
    )
    exit_yaml: dict[str, Any] = {}
    if exit_targets_path.exists():
        with exit_targets_path.open(encoding="utf-8") as handle:
            exit_yaml = yaml.safe_load(handle) or {}
    gated = exclude_tickers
    if gated is None:
        gated = collect_above_justified_target_tickers(
            [s.ticker for s in name_scores],
            prices_df=prices_df,
            fundamentals_df=fundamentals_df,
            template_fund_by=alpha_fund_by,
            exit_yaml=exit_yaml,
        )
    hk_inputs = load_hakedaka_inputs(root_guess, data_dir=book_dir)
    hk_min = int(getattr(cfg.sizing, "hakedaka_min_hits", 2) or 2)
    hk_on = bool(getattr(cfg.sizing, "hakedaka_gate_enabled", True))
    hk_fail = hakedaka_fail_tickers(
        [s.ticker for s in name_scores],
        hk_inputs,
        min_hits=hk_min,
        enabled=hk_on,
    )
    # Candidate count = sizing.target_names (portfolio UI / yaml). Do not
    # override with alpha_book_ops default (that file is 9:1 weight policy).
    allocation = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T1,
        scores=name_scores,
        existing_weights={},
        tranche_budget=float(policy.equity_share),
        overlay=overlay,
        exclude_tickers=gated,
        hakedaka_skip=hk_fail,
    )
    if skip_reasons is not None:
        skip_reasons.update(allocation.skip_reasons)
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

    price_idx = pd.DataFrame()
    if not prices_df.empty and "ticker" in prices_df.columns:
        work = prices_df.copy()
        work["ticker"] = work["ticker"].astype(str).str.zfill(6)
        # Keep latest row per ticker if duplicates exist
        if "date" in work.columns:
            work = work.sort_values("date")
        price_idx = work.drop_duplicates("ticker", keep="last").set_index("ticker")

    fund_by_ticker: dict[str, dict[str, Any]] = {}
    fund_for_peers = fundamentals_df
    if not fundamentals_df.empty and "ticker" in fundamentals_df.columns:
        for _, fr in fundamentals_df.iterrows():
            t = str(fr.get("ticker", "")).zfill(6)
            fund_by_ticker[t] = fr.to_dict()
        if "sector" not in fundamentals_df.columns:
            smap = {
                str(s.ticker).zfill(6): s.sector
                for s in scores
                if getattr(s, "sector", "")
            }
            if smap:
                fund_for_peers = fundamentals_df.copy()
                fund_for_peers["ticker"] = fund_for_peers["ticker"].astype(str).str.zfill(6)
                fund_for_peers["sector"] = fund_for_peers["ticker"].map(
                    lambda t: smap.get(str(t).zfill(6), "")
                )

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
        approved_by = ""
        revalidate_required = False
        revalidate_reason = ""
        if isinstance(ticker_targets, dict):
            pbr_max = _f((ticker_targets.get("valuation") or {}).get("pbr_max"))
            yaml_target_px = _f(ticker_targets.get("target_price"))
            approved_as_of = str(ticker_targets.get("approved_as_of") or "").strip()
            approved_by = str(ticker_targets.get("approved_by") or "").strip()
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
                default="목표가 없음 — 제안 종목에서 정량초안 승인 · 편입 차단",
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
        sector = (
            sc.sector if sc and sc.sector else str(fund_row.get("sector", "") or "")
        )
        qextra = quant_portfolio_extra(
            ticker,
            fund_row=fund_row,
            price=cur_p,
            sector=sector,
            fundamentals_df=fund_for_peers,
            alpha_row=alpha_fund_by.get(ticker),
        )
        extra = {
            "book": "proposal",
            "selection_policy": "B",
            "proposal_eligible": True,
            "approved_as_of": approved_as_of,
            "approved_by": approved_by,
            "revalidate_required": revalidate_required,
            "revalidate_reason": revalidate_reason,
            **qextra,
        }
        hk = evaluate_hakedaka(ticker, hk_inputs, min_hits=hk_min)
        extra["hakedaka_detail"] = hits_label(hk)
        extra["hakedaka_hits"] = hk.hits
        extra["hakedaka_known"] = hk.known
        extra["cyclical_theme"] = is_cyclical_heavy(
            sector=sector, name=str(name or "")
        )
        mix_px = qextra.get("quant_price_mid")
        if yaml_target_px and mix_px not in (None, ""):
            try:
                mix_f = float(mix_px)
                saved = float(yaml_target_px)
                if mix_f > 0 and saved > 0 and abs(mix_f - saved) / max(mix_f, saved) > 0.15:
                    target_detail = (
                        f"{target_detail} · 지금 혼합 {mix_f:,.0f}원 (저장과 다름)"
                    ).strip(" ·")
            except (TypeError, ValueError):
                pass
        extra = attach_ladder_extra(
            extra,
            ticker=ticker,
            current=cur_p,
            target_price=target_price,
            lookback_lows=lookback_lows,
        )
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
                sector=sector,
                current_pbr=current_pbr,
                pbr_max=pbr_max,
                extra=extra,
            )
        )
    rows.sort(key=lambda r: (-(r.total_score or 0), -r.weight_pct, r.ticker))
    return rows


def proposal_band_scores(
    scores: Sequence[ScoreboardRow],
    *,
    target_n: int,
) -> list[ScoreboardRow]:
    """Top N by total_score for the proposal list. Eligibility does not drop names."""
    n = max(0, int(target_n))
    scored: list[ScoreboardRow] = []
    for row in scores:
        if row.total_score is None:
            continue
        try:
            float(row.total_score)
        except (TypeError, ValueError):
            continue
        scored.append(row)
    scored.sort(key=lambda r: (-float(r.total_score or 0), str(r.ticker).zfill(6)))
    return scored[:n]


def cutoff_passed_ineligible(
    scores: Sequence[ScoreboardRow],
    *,
    cutoff: float | None,
    target_n: int | None = None,
) -> list[ScoreboardRow]:
    """High total_score names blocked by quality/gates, not by the score cutoff."""
    if cutoff is None:
        return []
    bar = float(cutoff)
    out: list[ScoreboardRow] = []
    for row in scores:
        if row.eligibility is True:
            continue
        if row.total_score is None:
            continue
        try:
            score = float(row.total_score)
        except (TypeError, ValueError):
            continue
        if score >= bar:
            out.append(row)
    out.sort(key=lambda r: (-float(r.total_score or 0), str(r.ticker)))
    if target_n is not None:
        return out[: max(0, int(target_n))]
    return out


def _blocked_proposal_reason(
    sc: ScoreboardRow,
    *,
    min_q: float | None,
    above_target: set[str],
    skip_reasons: Mapping[str, str] | None = None,
) -> str:
    from alpha_system.ui.services.ko_display import format_ineligibility_reason

    ticker = str(sc.ticker).zfill(6)
    if sc.eligibility is not True:
        return format_ineligibility_reason(
            sc.eligibility_reason,
            score_q=sc.score_q,
            min_q=min_q,
        )
    if ticker in above_target:
        return "현재가 ≥ 혼합 목표가"
    mapped = (skip_reasons or {}).get(ticker) or (skip_reasons or {}).get(str(sc.ticker))
    if mapped:
        return str(mapped)
    return "편입 슬롯·업종 한도·게이트로 제외"


def _blocked_proposal_rows(
    blocked: Sequence[ScoreboardRow],
    *,
    cfg: AlphaSystemConfig,
    prices_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    lookback_lows: dict | None = None,
    root: Path | None = None,
    above_target: set[str] | None = None,
    skip_reasons: Mapping[str, str] | None = None,
    data_dir: Path | None = None,
) -> list[PortfolioRow]:
    """Same proposal card shape, weight 0, with the ineligibility reason."""
    from alpha_system.sizing.cyclical_theme import is_cyclical_heavy
    from alpha_system.sizing.hakedaka_screen import (
        evaluate_hakedaka,
        hits_label,
        load_hakedaka_inputs,
    )
    from src.alpha.price_ladder import attach_ladder_extra
    from src.alpha.quant_target_estimate import (
        load_alpha_template_fundamentals,
        quant_portfolio_extra,
    )

    if not blocked:
        return []
    gated = {str(t).zfill(6) for t in (above_target or set()) if str(t).strip()}
    cap = float(cfg.sizing.market_value_cap) * 100.0
    min_q = getattr(cfg.scoring, "quality_min_score", None)
    root_guess = Path(root) if root is not None else Path(".")
    book_dir = Path(data_dir) if data_dir is not None else root_guess / "data"
    hk_inputs = load_hakedaka_inputs(root_guess, data_dir=book_dir)
    hk_min = int(getattr(cfg.sizing, "hakedaka_min_hits", 2) or 2)
    alpha_fund_by = load_alpha_template_fundamentals(root_guess)
    price_idx = pd.DataFrame()
    if not prices_df.empty and "ticker" in prices_df.columns:
        work = prices_df.copy()
        work["ticker"] = work["ticker"].astype(str).str.zfill(6)
        if "date" in work.columns:
            work = work.sort_values("date")
        price_idx = work.drop_duplicates("ticker", keep="last").set_index("ticker")
    fund_by_ticker: dict[str, dict[str, Any]] = {}
    fund_for_peers = fundamentals_df
    if not fundamentals_df.empty and "ticker" in fundamentals_df.columns:
        for _, fr in fundamentals_df.iterrows():
            t = str(fr.get("ticker", "")).zfill(6)
            fund_by_ticker[t] = fr.to_dict()
        if "sector" not in fundamentals_df.columns:
            smap = {
                str(s.ticker).zfill(6): s.sector
                for s in blocked
                if getattr(s, "sector", "")
            }
            if smap:
                fund_for_peers = fundamentals_df.copy()
                fund_for_peers["ticker"] = fund_for_peers["ticker"].astype(str).str.zfill(6)
                fund_for_peers["sector"] = fund_for_peers["ticker"].map(
                    lambda t: smap.get(str(t).zfill(6), "")
                )

    rows: list[PortfolioRow] = []
    for sc in blocked:
        ticker = str(sc.ticker).zfill(6)
        cur_p = None
        if not price_idx.empty and ticker in price_idx.index:
            cur_p = _f(
                price_idx.loc[ticker].get("close")
                or price_idx.loc[ticker].get("price")
            )
        fund_row = fund_by_ticker.get(ticker, {})
        current_pbr = _f(fund_row.get("pbr"))
        sector = str(sc.sector or fund_row.get("sector") or "")
        reason = _blocked_proposal_reason(
            sc, min_q=min_q, above_target=gated, skip_reasons=skip_reasons
        )
        qextra = quant_portfolio_extra(
            ticker,
            fund_row=fund_row,
            price=cur_p,
            sector=sector,
            fundamentals_df=fund_for_peers,
            alpha_row=alpha_fund_by.get(ticker),
        )
        extra = {
            "book": "proposal",
            "selection_policy": "B",
            "proposal_eligible": False,
            "ineligible_reason": reason,
            **qextra,
        }
        hk = evaluate_hakedaka(ticker, hk_inputs, min_hits=hk_min)
        extra["hakedaka_detail"] = hits_label(hk)
        extra["hakedaka_hits"] = hk.hits
        extra["hakedaka_known"] = hk.known
        extra["cyclical_theme"] = is_cyclical_heavy(
            sector=sector, name=str(sc.name or "")
        )
        extra = attach_ladder_extra(
            extra,
            ticker=ticker,
            current=cur_p,
            target_price=None,
            lookback_lows=lookback_lows or {},
        )
        rows.append(
            PortfolioRow(
                ticker=ticker,
                name=sc.name or ticker,
                weight_pct=0.0,
                initial_weight_pct=0.0,
                avg_price=None,
                current_price=cur_p,
                target_price=None,
                target_progress=None,
                remaining_upside_pct=None,
                has_target=False,
                target_detail=reason,
                target_gap_kind="ineligible",
                cap_pct=cap,
                cap_headroom_pct=None,
                cap_near=False,
                cap_over=False,
                price_progress_pct=None,
                tranche_source="SCREEN",
                total_score=sc.total_score,
                sector=sector,
                current_pbr=current_pbr,
                pbr_max=None,
                extra=extra,
            )
        )
    rows.sort(key=lambda r: (-(r.total_score or 0), r.ticker))
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
    lookback_lows: dict | None = None,
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

    from src.alpha.price_ladder import attach_ladder_extra, load_lookback_lows
    from src.alpha.quant_target_estimate import (
        load_alpha_template_fundamentals,
        quant_portfolio_extra,
    )

    root_guess = exit_targets_path.parent.parent if exit_targets_path else Path(".")
    alpha_fund_by = load_alpha_template_fundamentals(root_guess)
    if lookback_lows is None:
        lookback_lows = load_lookback_lows(root_guess, prices_df)

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
        sector = str(pos.get("sector", "") or (sc.sector if sc else ""))
        qextra = quant_portfolio_extra(
            ticker,
            fund_row=fund_row,
            price=cur_p,
            sector=sector,
            fundamentals_df=fundamentals_df,
            alpha_row=alpha_fund_by.get(ticker),
        )
        extra = attach_ladder_extra(
            qextra,
            ticker=ticker,
            current=cur_p,
            target_price=target_price,
            lookback_lows=lookback_lows,
        )
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
                sector=sector,
                current_pbr=current_pbr,
                pbr_max=pbr_max,
                extra=extra,
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
