from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_loader import load_positions, load_target_portfolio


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_execution_context(output_dir: Path) -> dict[str, Any]:
    final = _read_json(output_dir / "final_execution_decision.json")
    from src.report.execution_metrics import count_executable_actions

    metrics = count_executable_actions(final)
    scope = str(final.get("execution_scope") or "NO_TRADE")
    return {
        "actual_buy_allowed": int(metrics.get("actual_buy_allowed_count") or 0),
        "no_trade": scope == "NO_TRADE",
        "execution_scope": scope,
    }


def _held_target_tickers(data_dir: Path) -> tuple[set[str], set[str]]:
    held: set[str] = set()
    target: set[str] = set()
    for row in load_positions(data_dir / "positions.csv"):
        if float(row.quantity or 0) > 0 and str(row.ticker).upper() != "CASH":
            if row.asset_group == "kr_alpha":
                held.add(str(row.ticker).zfill(6))
    for row in load_target_portfolio(data_dir / "target_portfolio.csv"):
        if row.asset_group == "kr_alpha":
            target.add(str(row.ticker).zfill(6))
    return held, target


def _merge_on_ticker(base: pd.DataFrame, extra: pd.DataFrame, suffix: str = "_x") -> pd.DataFrame:
    if base.empty:
        return extra.copy()
    if extra.empty:
        return base.copy()
    left = base.copy()
    right = extra.copy()
    left["ticker"] = left["ticker"].astype(str).str.zfill(6)
    right["ticker"] = right["ticker"].astype(str).str.zfill(6)
    overlap = set(left.columns) & set(right.columns) - {"ticker"}
    if overlap:
        right = right.rename(columns={c: f"{c}{suffix}" for c in overlap if c != "ticker"})
    return left.merge(right, on="ticker", how="left")


def build_holdings_target_flow_table(data_dir: Path, output_dir: Path) -> pd.DataFrame:
    held, target = _held_target_tickers(data_dir)
    tickers = sorted(held | target)
    if not tickers:
        return pd.DataFrame()

    board = _read_csv(output_dir / "alpha_signal_board.csv")
    scored = _read_csv(output_dir / "alpha_v2_scored.csv")
    triggers = _read_csv(output_dir / "alpha_v2_flow_triggers.csv")

    rows: list[dict[str, str]] = []
    for tk in tickers:
        row: dict[str, str] = {
            "ticker": tk,
            "holding_flag": str(tk in held),
            "target_flag": str(tk in target),
        }
        if not board.empty and "ticker" in board.columns:
            br = board[board["ticker"].astype(str).str.zfill(6) == tk]
            if not br.empty:
                b = br.iloc[0]
                row.update({
                    "name": str(b.get("name", "")),
                    "action_state": str(b.get("action_state", "")),
                    "flow_signal": str(b.get("flow_signal", "")),
                    "current_weight": str(b.get("current_weight_pct", "")),
                    "target_weight": str(b.get("target_weight_pct", "")),
                })
        if not scored.empty and "ticker" in scored.columns:
            sr = scored[scored["ticker"].astype(str).str.zfill(6) == tk]
            if not sr.empty:
                s = sr.iloc[0]
                for col in (
                    "pension_net_buy_20d", "foreign_net_buy_20d",
                    "pension_flow_to_market_cap", "pension_flow_to_turnover",
                    "pension_streak_direction", "pension_streak_days",
                    "flow_confidence", "flow_data_stale", "flow_signal_state",
                    "buy_watch", "trim_watch", "market",
                ):
                    if col in s.index:
                        row[col] = str(s.get(col, ""))
                if "name" not in row or not row["name"]:
                    row["name"] = str(s.get("name", ""))
        if not triggers.empty and "ticker" in triggers.columns:
            tr = triggers[triggers["ticker"].astype(str).str.zfill(6) == tk]
            if not tr.empty:
                t = tr.iloc[0]
                row["buy_watch"] = str(t.get("buy_watch", row.get("buy_watch", "")))
                row["trim_watch"] = str(t.get("trim_watch", row.get("trim_watch", "")))
                row["review_only"] = str(t.get("review_only", ""))
        ctx = load_execution_context(output_dir)
        row["review_only"] = str(
            row.get("review_only", "True" if ctx["no_trade"] else "False")
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_v2_candidate_flow_table(output_dir: Path) -> pd.DataFrame:
    path = output_dir / "alpha_v2_final_candidates.csv"
    if not path.exists():
        path = output_dir / "alpha_v2_top30.csv"
    df = _read_csv(path)
    if df.empty:
        return df
    cols = [
        "final_rank", "rank", "ticker", "name", "market", "sector", "grade",
        "total_score_v1", "flow_score", "total_score_v2_shadow",
        "pension_net_buy_20d", "foreign_net_buy_20d",
        "pension_foreign_co_buy", "pension_foreign_co_sell",
        "flow_signal_state", "buy_permission", "review_only", "key_reason",
        "shadow_watch", "flow_data_stale",
    ]
    present = [c for c in cols if c in df.columns]
    out = df[present].copy()
    if "final_rank" not in out.columns and "rank" in out.columns:
        out["final_rank"] = out["rank"]
    return out


def load_trim_watch_tables(output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    held = _read_csv(output_dir / "alpha_v2_trim_watch_held.csv")
    info = _read_csv(output_dir / "alpha_v2_trim_watch_informational.csv")
    if held.empty and info.empty:
        detail = _read_csv(output_dir / "alpha_v2_trim_watch_detail.csv")
        if not detail.empty and "trim_category" in detail.columns:
            held = detail[detail["trim_category"] == "held_or_target"].copy()
            info = detail[detail["trim_category"] == "informational"].copy()
    return held, info


def load_freshness_summary(output_dir: Path) -> dict[str, Any]:
    summary = _read_json(output_dir / "alpha_v2_summary.json")
    dash = _read_json(output_dir / "flow_dashboard_summary.json")
    cov = summary.get("coverage") or {}
    cache_meta = dash.get("cache_meta") or dash
    # Prefer watched-universe counts when available
    stale = int(
        dash.get("stale_flow_count")
        or cov.get("watched_stale_flow_count")
        or cov.get("stale_flow_count")
        or 0
    )
    fresh = int(
        dash.get("fresh_flow_count")
        or cov.get("watched_fresh_flow_count")
        or cov.get("fresh_flow_count")
        or 0
    )
    total = stale + fresh
    return {
        "stale_flow_count": stale,
        "fresh_flow_count": fresh,
        "fresh_ratio": dash.get("fresh_ratio") or (round(fresh / total, 3) if total else None),
        "stale_ratio": dash.get("stale_ratio") or (round(stale / total, 3) if total else None),
        "stale_reason_summary": dash.get("stale_reason_summary") or cache_meta.get("stale_reason_summary") or {},
        "pykrx_failed_tickers": dash.get("pykrx_failed_tickers") or cache_meta.get("pykrx_failed_tickers") or [],
        "last_successful_flow_refresh": dash.get("last_successful_flow_refresh") or cache_meta.get("last_successful_flow_refresh", "—"),
        "coverage_scope": dash.get("coverage_scope") or "watched_universe",
        "cache_hit_count": dash.get("cache_hit_count") or cache_meta.get("cache_hit_count", 0),
        "cache_miss_count": dash.get("cache_miss_count") or cache_meta.get("cache_miss_count", 0),
        "stale_ratio_legacy_v2_all": round(
            int(cov.get("stale_flow_count") or 0) / max(int(cov.get("scored_count") or 1), 1), 3
        ),
        "validation_status": summary.get("validation_status", "—"),
        "last_flow_update": dash.get("as_of") or summary.get("as_of", "—"),
        "actual_consecutive_days_available": bool(dash.get("actual_consecutive_days")),
        "flow_dashboard": dash,
        "cache_meta": cache_meta,
    }


def load_leaderboard_tables(output_dir: Path) -> dict[str, pd.DataFrame]:
    keys = {
        "pension_buy": "flow_leaderboard_pension.csv",
        "foreign_buy": "flow_leaderboard_foreign.csv",
        "cobuy": "flow_leaderboard_cobuy.csv",
        "pension_sell": "flow_leaderboard_pension_sell.csv",
        "foreign_sell": "flow_leaderboard_foreign_sell.csv",
        "streak_buy": "flow_leaderboard_streak_buy.csv",
        "streak_sell": "flow_leaderboard_streak_sell.csv",
    }
    return {k: _read_csv(output_dir / fname) for k, fname in keys.items()}


def load_streaks_table(output_dir: Path) -> pd.DataFrame:
    return _read_csv(output_dir / "flow_streaks.csv")


def build_daily_report_flow_section(output_dir: Path) -> list[str]:
    from src.alpha_flow.policy import FLOW_UI_POLICY_LINES

    cards = compute_dashboard_cards(output_dir)
    fresh = load_freshness_summary(output_dir)
    lines = [
        "## Alpha 수급 현황 (review-only)",
        "",
    ]
    for line in FLOW_UI_POLICY_LINES[:3]:
        lines.append(f"- {line}")
    lines.extend([
        "",
        f"- **Fresh / Stale flow**: {cards.get('fresh_flow_count', 0)} / {cards.get('stale_flow_count', 0)}",
        f"- **Buy Watch / Trim Watch**: {cards.get('buy_watch_count', 0)} / {cards.get('trim_watch_count', 0)}",
        f"- **Actual Buy Allowed**: {cards.get('actual_buy_allowed', 0)} · **NO_TRADE**: {cards.get('no_trade', True)}",
        f"- **actual_consecutive_days**: {fresh.get('actual_consecutive_days_available', False)}",
        "",
    ])
    return lines


def compute_dashboard_cards(output_dir: Path) -> dict[str, Any]:
    ctx = load_execution_context(output_dir)
    fresh = load_freshness_summary(output_dir)
    streaks = load_streaks_table(output_dir)
    triggers = _read_csv(output_dir / "alpha_v2_flow_triggers.csv")
    held, info = load_trim_watch_tables(output_dir)

    buy_n = 0
    trim_n = 0
    if not triggers.empty:
        if "buy_watch" in triggers.columns:
            buy_n = int(triggers["buy_watch"].astype(str).str.lower().isin({"true", "1"}).sum())
        if "trim_watch" in triggers.columns:
            trim_n = int(triggers["trim_watch"].astype(str).str.lower().isin({"true", "1"}).sum())

    pension_acc = pension_dist = co_buy = co_sell = 0
    if not streaks.empty:
        if "pension_consecutive_days" in streaks.columns and "pension_streak_direction" in streaks.columns:
            pdir = streaks["pension_streak_direction"].astype(str)
            pdays = pd.to_numeric(streaks["pension_consecutive_days"], errors="coerce").fillna(0)
            pension_acc = int(((pdir == "buy") & (pdays >= 3)).sum())
            pension_dist = int(((pdir == "sell") & (pdays >= 3)).sum())
        if "cobuy_consecutive_days" in streaks.columns:
            co_buy = int((pd.to_numeric(streaks["cobuy_consecutive_days"], errors="coerce").fillna(0) >= 2).sum())
        if "cosell_consecutive_days" in streaks.columns:
            co_sell = int((pd.to_numeric(streaks["cosell_consecutive_days"], errors="coerce").fillna(0) >= 2).sum())

    return {
        **ctx,
        "fresh_flow_count": fresh.get("fresh_flow_count", 0),
        "stale_flow_count": fresh.get("stale_flow_count", 0),
        "pension_accumulation_candidates": pension_acc,
        "pension_distribution_warnings": pension_dist,
        "cobuy_candidates": co_buy,
        "cosell_warnings": co_sell,
        "buy_watch_count": buy_n,
        "trim_watch_count": trim_n,
        "trim_watch_held_count": len(held),
        "trim_watch_informational_count": len(info),
        "actual_consecutive_days": fresh.get("actual_consecutive_days_available", False),
    }
