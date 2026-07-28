from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd
import yaml

from src.data_loader import load_positions, load_target_portfolio
from src.value_list.scorer import HakedakaScoreRow, score_watchlist
from src.value_list.seed_stocks import GROUP_LABELS, STOCKS
from src.value_list.ticker_resolver import build_name_ticker_map, resolve_ticker


def load_watchlist(data_dir: Path) -> list[dict]:
    path = data_dir / "hakedaka_watchlist.yaml"
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("stocks"):
            return list(raw["stocks"])
        if isinstance(raw, list):
            return raw
    return [dict(s) for s in STOCKS]


def _load_alpha_map(output_dir: Path) -> dict[str, dict]:
    path = output_dir / "alpha_shortlist.csv"
    if not path.exists():
        path = output_dir / "alpha_candidates.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str)
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        if not t:
            continue
        out[t] = {
            "total_score": float(row["total_score"]) if row.get("total_score") not in (None, "") else None,
            "grade": row.get("grade", ""),
        }
    return out


def _load_fundamentals_map(data_dir: Path) -> dict[str, dict]:
    path = data_dir / "fundamentals.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str)
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        if not t:
            continue
        out[t] = {
            k: row.get(k)
            for k in (
                "pbr", "per", "dividend_yield", "roe", "debt_ratio",
                "operating_cash_flow", "fcf",
            )
        }
    return out


def _build_alignment_maps(data_dir: Path) -> tuple[dict[str, float], dict[str, str]]:
    from src.value_list.dart_disclosure import load_hakedaka_dart_signals
    from src.value_list.value_up_alignment import compute_alignment_score

    dart = load_hakedaka_dart_signals(data_dir)
    tickers_data = dart.get("tickers") or {}
    fund_map = _load_fundamentals_map(data_dir)
    align: dict[str, float] = {}
    signals: dict[str, str] = {}
    for t, sig in tickers_data.items():
        ticker = str(t).zfill(6)
        fund = fund_map.get(ticker)
        align[ticker] = compute_alignment_score(fund=fund, dart=sig)
        signals[ticker] = str(sig.get("signal", "unknown"))
    return align, signals


def run_hakedaka_tracker(data_dir: Path, output_dir: Path) -> list[HakedakaScoreRow]:
    stocks = load_watchlist(data_dir)
    name_map = build_name_ticker_map(data_dir / "universe.csv")
    overrides_path = data_dir / "hakedaka_ticker_overrides.yaml"
    overrides: dict[str, str] = {}
    if overrides_path.exists():
        raw = yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or {}
        overrides = raw.get("overrides", raw) if isinstance(raw, dict) else {}

    for s in stocks:
        if not s.get("ticker"):
            raw = resolve_ticker(str(s["name"]), name_map, overrides)
            s["ticker"] = raw.zfill(6) if raw else ""

    positions = load_positions(data_dir / "positions.csv") if (data_dir / "positions.csv").exists() else []
    targets = load_target_portfolio(data_dir / "target_portfolio.csv") if (data_dir / "target_portfolio.csv").exists() else []
    pos_tickers = {p.ticker.zfill(6) for p in positions if p.ticker != "CASH"}
    tgt_tickers = {t.ticker.zfill(6) for t in targets if t.asset_group == "kr_alpha"}

    align_map, dart_signals = _build_alignment_maps(data_dir)

    rows = score_watchlist(
        stocks,
        alpha_by_ticker=_load_alpha_map(output_dir),
        fundamentals_by_ticker=_load_fundamentals_map(data_dir),
        alignment_by_ticker=align_map,
        dart_signal_by_ticker=dart_signals,
        position_tickers=pos_tickers,
        target_tickers=tgt_tickers,
        shortlist_tickers=set(_load_alpha_map(output_dir)),
        group_labels=GROUP_LABELS,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(r) for r in rows])
    df.to_csv(output_dir / "hakedaka_scores.csv", index=False, encoding="utf-8-sig")

    from src.value_list.report import write_hakedaka_report

    write_hakedaka_report(rows, output_dir / "hakedaka_report.md")
    return rows
