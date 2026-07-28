from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.benchmark_data import load_combined_prices
from src.alpha.gate_forward_enrich import _forward_return_combined
from src.decision.shadow_performance import add_business_days
from src.value_list.dart_disclosure import load_hakedaka_dart_signals
from src.value_list.pipeline import load_watchlist
from src.value_list.seed_stocks import GROUP_LABELS
from src.value_list.ticker_resolver import build_name_ticker_map, resolve_ticker
from src.value_list.hakedaka_data_quality import (
    apply_score_caps,
    build_hakedaka_data_quality_rows,
    HakedakaDataQualityRow,
)
from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals
from src.value_list.value_up_alignment import compute_alignment_score

RERATING_DISCLAIMER = (
    "Shadow diagnostic only — not a buy/sell recommendation. "
    "v1.0.2 execution authority remains trade_actions / allowed_actions only. "
    "90-120 day forward return required before any QVM ranking or target integration."
)

FORWARD_HORIZONS = (5, 20, 60, 120)

GROUP_ID_TAGS: dict[int, list[str]] = {
    1: ["holding_company_discount", "governance_activism", "dividend_payout_reform"],
    2: ["net_net_cash_rich", "treasury_share_cancellation"],
    3: ["asset_play_real_estate", "korea_discount_rerating"],
    4: ["treasury_share_cancellation", "governance_activism", "dividend_payout_reform"],
    5: ["dividend_payout_reform", "korea_discount_rerating"],
}

SCORE_WEIGHTS = {
    "valuation_asset_score": 0.25,
    "shareholder_return_score": 0.25,
    "governance_catalyst_score": 0.20,
    "accounting_transparency_score": 0.10,
    "market_rerating_score": 0.10,
    "value_trap_safety_score": 0.10,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _f(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _candidate_group_tags(stock: dict[str, Any]) -> str:
    gid = int(stock.get("group_id", 5))
    tags = list(GROUP_ID_TAGS.get(gid, []))
    invest = str(stock.get("invest_type", ""))
    if any(k in invest for k in ("행동", "지배", "환원", "소각")):
        for t in ("governance_activism", "treasury_share_cancellation", "dividend_payout_reform"):
            if t not in tags:
                tags.append(t)
    tags.append("accounting_transparency_ifrs18")
    return "|".join(sorted(set(tags)))


def _load_fundamentals(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / "fundamentals.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        if t:
            out[t] = dict(row)
    return out


def _load_qvm_maps(output_dir: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    shortlist: set[str] = set()
    sl_path = output_dir / "alpha_shortlist.csv"
    if sl_path.exists():
        df = pd.read_csv(sl_path, dtype=str)
        shortlist = {str(r).zfill(6) for r in df["ticker"].tolist() if str(r).strip()}

    qvm: dict[str, dict[str, Any]] = {}
    diag_path = output_dir / "hakedaka_overlap_diagnostics.csv"
    if diag_path.exists():
        df = pd.read_csv(diag_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            t = str(row.get("ticker", "")).zfill(6)
            if not t:
                continue
            rank = row.get("qvm_rank", "")
            qvm[t] = {
                "qvm_rank": int(float(rank)) if rank not in ("", None) else None,
                "qvm_grade": str(row.get("qvm_grade", "")),
                "qvm_score": _f(row.get("qvm_score")),
                "in_shortlist": t in shortlist,
            }
    return qvm, shortlist


def _load_macro_scenario(output_dir: Path) -> str:
    path = output_dir / "macro_scenario.json"
    if not path.exists():
        return "reform_delay"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return str(doc.get("scenario_id", "reform_delay"))
    except (json.JSONDecodeError, OSError):
        return "reform_delay"


def _dart_event_count(sig: dict[str, Any]) -> int:
    return sum(
        1
        for k in ("cancel_disclosure", "acquire_disclosure", "dispose_disclosure", "return_disclosure")
        if sig.get(k)
    )


def score_valuation_asset(stock: dict[str, Any], fund: dict[str, Any] | None) -> float:
    score = 45.0
    gid = int(stock.get("group_id", 5))
    if gid in (1, 2):
        score += 12.0
    if gid == 3:
        score += 8.0
    pbr = _f(fund.get("pbr") if fund else None)
    if pbr is not None and pbr > 0:
        if pbr < 0.5:
            score += 35.0
        elif pbr < 1.0:
            score += 28.0
        elif pbr < 1.5:
            score += 18.0
        elif pbr < 2.5:
            score += 8.0
        else:
            score -= 5.0
    pdf = _f(stock.get("pdf_total"))
    if pdf is not None:
        score += _clamp((pdf + 10) / 77 * 25, 0, 25)
    return _clamp(score)


def score_shareholder_return(
    fund: dict[str, Any] | None,
    dart: dict[str, Any] | None,
    alignment: float | None,
) -> tuple[float, bool, bool]:
    score = 40.0
    buyback_flag = False
    div_change_flag = False
    if fund:
        div = _f(fund.get("dividend_yield"))
        if div is not None:
            if div >= 5:
                score += 30.0
                div_change_flag = True
            elif div >= 3:
                score += 22.0
                div_change_flag = True
            elif div >= 1.5:
                score += 12.0
    if dart:
        if dart.get("cancel_disclosure"):
            score += 25.0
            buyback_flag = True
        elif dart.get("signal") == "strong":
            score += 18.0
            buyback_flag = True
        if dart.get("return_disclosure"):
            score += 10.0
            div_change_flag = True
        if dart.get("signal") == "weak":
            score -= 12.0
    if alignment is not None:
        score += (alignment - 50) * 0.25
    return _clamp(score), buyback_flag, div_change_flag


def score_governance_catalyst(stock: dict[str, Any]) -> float:
    grade_pts = {"A": 78.0, "B": 62.0, "C": 45.0, "W": 22.0}
    score = grade_pts.get(str(stock.get("grade", "C"))[:1], 40.0)
    gid = int(stock.get("group_id", 5))
    if gid == 4:
        score += 12.0
    if str(stock.get("priority_bucket", "")) == "핵심":
        score += 10.0
    invest = str(stock.get("invest_type", ""))
    if any(k in invest for k in ("행동", "지배", "환원", "소각")):
        score += 8.0
    return _clamp(score)


def score_accounting_transparency(fund: dict[str, Any] | None, stock: dict[str, Any]) -> float:
    score = 52.0
    if fund:
        ocf = _f(fund.get("operating_cash_flow"))
        if ocf is not None and ocf > 0:
            score += 18.0
        elif ocf is not None and ocf < 0:
            score -= 12.0
        roe = _f(fund.get("roe"))
        if roe is not None and roe >= 5:
            score += 12.0
    if str(stock.get("complexity", "")) == "낮음":
        score += 12.0
    elif str(stock.get("complexity", "")) == "높음":
        score -= 10.0
    return _clamp(score)


def score_market_rerating(
    fund: dict[str, Any] | None,
    scenario_id: str,
) -> tuple[float, str]:
    base = {"reform_success": 72.0, "reform_delay": 48.0, "stress_failure": 28.0}.get(scenario_id, 48.0)
    sensitivity = "medium"
    pbr = _f(fund.get("pbr") if fund else None)
    if pbr is not None and 0 < pbr < 1.0:
        base += 12.0
        sensitivity = "high"
    elif pbr is not None and pbr < 1.5:
        sensitivity = "medium"
    else:
        sensitivity = "low"
    if scenario_id == "reform_success":
        sensitivity = "high" if sensitivity != "low" else "medium"
    return _clamp(base), sensitivity


def score_value_trap_safety(
    stock: dict[str, Any],
    fund: dict[str, Any] | None,
    hk_fund: dict[str, Any] | None,
    dart: dict[str, Any] | None,
) -> float:
    score = 72.0
    if str(stock.get("grade", "")) == "W":
        score -= 28.0
    if str(stock.get("complexity", "")) == "높음":
        score -= 18.0
    merged = hk_fund or fund or {}
    if merged:
        debt = _f(merged.get("debt_ratio"))
        if debt is not None and debt > 200:
            score -= 22.0
        ocf = _f(merged.get("operating_cash_flow"))
        if ocf is not None and ocf < 0:
            score -= 15.0
        elif ocf is not None and ocf > 0:
            score += 8.0
        fcf = _f(merged.get("free_cash_flow") or merged.get("fcf"))
        if fcf is not None and fcf > 0:
            score += 6.0
    if dart and dart.get("signal") == "weak":
        score -= 12.0
    return _clamp(score)


def _total_score(row: dict[str, Any]) -> float:
    total = 0.0
    for key, w in SCORE_WEIGHTS.items():
        total += float(row.get(key, 0)) * w
    return round(total, 2)


def _forward_returns(
    prices: pd.DataFrame,
    ticker: str,
    as_of: str,
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for h in FORWARD_HORIZONS:
        target = add_business_days(as_of, h)
        if not target:
            out[f"forward_return_{h}d"] = None
            continue
        out[f"forward_return_{h}d"] = _forward_return_combined(prices, ticker, as_of, h)
    return out


def _kospi_excess(
    prices: pd.DataFrame,
    ticker: str,
    as_of: str,
    horizon: int = 20,
) -> float | None:
    stock_ret = _forward_return_combined(prices, ticker, as_of, horizon)
    bench_ret = _forward_return_combined(prices, "069500", as_of, horizon)
    if stock_ret is None or bench_ret is None:
        return None
    return round(stock_ret - bench_ret, 4)


def _catalyst_evidence(
    stock: dict[str, Any],
    dart: dict[str, Any] | None,
    flags: dict[str, bool],
) -> str:
    parts: list[str] = []
    parts.append(str(stock.get("invest_type", "")))
    if dart:
        if dart.get("cancel_disclosure"):
            parts.append("dart:cancel")
        if dart.get("return_disclosure"):
            parts.append("dart:return")
        if dart.get("signal"):
            parts.append(f"dart:{dart.get('signal')}")
    if flags.get("ifrs18_relevance_flag"):
        parts.append("ifrs18:2027")
    if flags.get("dividend_policy_change_flag"):
        parts.append("dividend_signal")
    return ";".join(p for p in parts if p)


def _overlap_status(ticker: str, qvm: dict[str, dict[str, Any]], shortlist: set[str]) -> str:
    info = qvm.get(ticker, {})
    in_sl = ticker in shortlist or info.get("in_shortlist")
    if in_sl:
        return "overlap"
    if info.get("qvm_rank") or info.get("qvm_grade"):
        return "qvm_scored_not_shortlist"
    return "hakedaka_only"


@dataclass
class ReratingRow:
    ticker: str
    name: str
    group_id: int
    group_label: str
    candidate_groups: str
    hakedaka_total_score: float
    valuation_asset_score: float
    shareholder_return_score: float
    governance_catalyst_score: float
    accounting_transparency_score: float
    market_rerating_score: float
    value_trap_safety_score: float
    data_quality_score: float
    hunt_tier: str
    data_incomplete: bool
    missing_price_flag: bool
    catalyst_evidence: str
    dart_event_count: int
    buyback_or_cancellation_flag: bool
    dividend_policy_change_flag: bool
    ifrs18_relevance_flag: bool
    msci_rerating_sensitivity: str
    qvm_rank: int | None
    qvm_grade: str
    overlap_status: str
    forward_return_5d: float | None = None
    forward_return_20d: float | None = None
    forward_return_60d: float | None = None
    forward_return_120d: float | None = None
    excess_vs_kospi200_20d: float | None = None
    shadow_only: bool = True
    execution_authority: str = "none"


def build_rerating_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> list[ReratingRow]:
    stocks = load_watchlist(data_dir)
    name_map = build_name_ticker_map(data_dir / "universe.csv")
    overrides_path = data_dir / "hakedaka_ticker_overrides.yaml"
    overrides: dict[str, str] = {}
    if overrides_path.exists():
        import yaml

        raw = yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or {}
        overrides = raw.get("overrides", raw) if isinstance(raw, dict) else {}

    fund_map = _load_fundamentals(data_dir)
    dart_doc = load_hakedaka_dart_signals(data_dir)
    dart_by = dart_doc.get("tickers") or {}
    qvm_map, shortlist = _load_qvm_maps(output_dir)
    scenario_id = _load_macro_scenario(output_dir)
    prices = load_combined_prices(data_dir)

    hk_fund_map = load_hakedaka_fundamentals(data_dir)
    quality_rows = build_hakedaka_data_quality_rows(data_dir, output_dir, as_of=as_of)
    quality_by = {q.ticker: q for q in quality_rows}

    rows: list[ReratingRow] = []
    for stock in stocks:
        if not stock.get("ticker"):
            raw = resolve_ticker(str(stock["name"]), name_map, overrides)
            stock["ticker"] = raw.zfill(6) if raw else ""
        ticker = str(stock.get("ticker", "")).zfill(6)
        if not ticker:
            continue

        fund = fund_map.get(ticker)
        hk_fund = hk_fund_map.get(ticker)
        merged_fund = hk_fund or fund
        dart = dart_by.get(ticker) or {}
        quality = quality_by.get(ticker)
        alignment = compute_alignment_score(fund=merged_fund, dart=dart)

        val = score_valuation_asset(stock, merged_fund)
        shr, buyback_flag, div_flag = score_shareholder_return(merged_fund, dart, alignment)
        gov = score_governance_catalyst(stock)
        acc = score_accounting_transparency(merged_fund, stock)
        mkt, msci_sens = score_market_rerating(merged_fund, scenario_id)
        trap = score_value_trap_safety(stock, fund, hk_fund, dart)

        sub = {
            "valuation_asset_score": val,
            "shareholder_return_score": shr,
            "governance_catalyst_score": gov,
            "accounting_transparency_score": acc,
            "market_rerating_score": mkt,
            "value_trap_safety_score": trap,
        }
        if quality:
            sub = apply_score_caps(sub, quality, dart=dart, hk_fund=hk_fund)
        total = _total_score(sub)
        ifrs18_flag = True
        flags = {
            "ifrs18_relevance_flag": ifrs18_flag,
            "dividend_policy_change_flag": div_flag,
            "buyback_or_cancellation_flag": buyback_flag,
        }
        qvm = qvm_map.get(ticker, {})
        fwd = _forward_returns(prices, ticker, as_of) if not prices.empty else {}
        excess = _kospi_excess(prices, ticker, as_of, 20) if not prices.empty else None

        rows.append(
            ReratingRow(
                ticker=ticker,
                name=str(stock.get("name", ticker)),
                group_id=int(stock.get("group_id", 5)),
                group_label=GROUP_LABELS.get(int(stock.get("group_id", 5)), ""),
                candidate_groups=_candidate_group_tags(stock),
                hakedaka_total_score=total,
                valuation_asset_score=sub["valuation_asset_score"],
                shareholder_return_score=sub["shareholder_return_score"],
                governance_catalyst_score=sub["governance_catalyst_score"],
                accounting_transparency_score=sub["accounting_transparency_score"],
                market_rerating_score=sub["market_rerating_score"],
                value_trap_safety_score=sub["value_trap_safety_score"],
                data_quality_score=quality.data_quality_score if quality else 0.0,
                hunt_tier=quality.hunt_tier if quality else "preliminary",
                data_incomplete=quality.data_incomplete if quality else True,
                missing_price_flag=quality.missing_price_flag if quality else True,
                catalyst_evidence=_catalyst_evidence(stock, dart, flags),
                dart_event_count=_dart_event_count(dart),
                buyback_or_cancellation_flag=buyback_flag,
                dividend_policy_change_flag=div_flag,
                ifrs18_relevance_flag=ifrs18_flag,
                msci_rerating_sensitivity=msci_sens,
                qvm_rank=qvm.get("qvm_rank"),
                qvm_grade=str(qvm.get("qvm_grade", "")),
                overlap_status=_overlap_status(ticker, qvm_map, shortlist),
                forward_return_5d=fwd.get("forward_return_5d"),
                forward_return_20d=fwd.get("forward_return_20d"),
                forward_return_60d=fwd.get("forward_return_60d"),
                forward_return_120d=fwd.get("forward_return_120d"),
                excess_vs_kospi200_20d=excess,
            )
        )

    rows.sort(key=lambda r: (-r.hakedaka_total_score, r.group_id, r.ticker))
    return rows


def _append_group_forward_csv(
    path: Path,
    rows: list[ReratingRow],
    *,
    as_of: str,
    run_id: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "date", "run_id", "group_id", "group_label", "candidate_count",
        "avg_forward_5d", "avg_forward_20d", "avg_forward_60d", "avg_forward_120d",
        "avg_excess_vs_kospi_20d",
        "top_quintile_avg_20d", "bottom_quintile_avg_20d",
        "overlap_avg_20d", "hakedaka_only_avg_20d",
    ]
    write_header = not path.exists()

    by_group: dict[int, list[ReratingRow]] = {}
    for r in rows:
        by_group.setdefault(r.group_id, []).append(r)

    def _avg(vals: list[float | None]) -> float | None:
        clean = [v for v in vals if v is not None]
        return round(sum(clean) / len(clean), 4) if clean else None

    sorted_rows = sorted(rows, key=lambda r: r.hakedaka_total_score, reverse=True)
    n = len(sorted_rows)
    q_size = max(1, n // 5)
    top_q = sorted_rows[:q_size]
    bottom_q = sorted_rows[-q_size:]
    overlap_rows = [r for r in rows if r.overlap_status == "overlap"]
    hk_only = [r for r in rows if r.overlap_status == "hakedaka_only"]

    out_rows: list[dict[str, Any]] = []
    for gid, grp in sorted(by_group.items()):
        out_rows.append({
            "date": as_of,
            "run_id": run_id,
            "group_id": gid,
            "group_label": GROUP_LABELS.get(gid, ""),
            "candidate_count": len(grp),
            "avg_forward_5d": _avg([r.forward_return_5d for r in grp]),
            "avg_forward_20d": _avg([r.forward_return_20d for r in grp]),
            "avg_forward_60d": _avg([r.forward_return_60d for r in grp]),
            "avg_forward_120d": _avg([r.forward_return_120d for r in grp]),
            "avg_excess_vs_kospi_20d": _avg([r.excess_vs_kospi200_20d for r in grp]),
            "top_quintile_avg_20d": _avg([r.forward_return_20d for r in top_q]),
            "bottom_quintile_avg_20d": _avg([r.forward_return_20d for r in bottom_q]),
            "overlap_avg_20d": _avg([r.forward_return_20d for r in overlap_rows]),
            "hakedaka_only_avg_20d": _avg([r.forward_return_20d for r in hk_only]),
        })

    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in out_rows:
            writer.writerow(row)


def write_hakedaka_rerating_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_id: str = "",
) -> dict[str, Any]:
    rows = build_rerating_rows(data_dir, output_dir, as_of=as_of)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame([asdict(r) for r in rows])
    df.to_csv(output_dir / "hakedaka_catalyst_scores.csv", index=False, encoding="utf-8-sig")

    preliminary = df[
        (df["hakedaka_total_score"].astype(float) >= 55.0)
        | (df["governance_catalyst_score"].astype(float) >= 70.0)
    ].copy()
    if preliminary.empty:
        preliminary = df.head(15)
    else:
        preliminary = preliminary.sort_values("hakedaka_total_score", ascending=False).head(25)
    preliminary.to_csv(output_dir / "hakedaka_preliminary_hunt_list.csv", index=False, encoding="utf-8-sig")

    primary = df[df["data_quality_score"].astype(float) >= 60.0].copy()
    primary = primary.sort_values("hakedaka_total_score", ascending=False).head(25)
    primary.to_csv(output_dir / "hakedaka_primary_hunt_list.csv", index=False, encoding="utf-8-sig")

    overlap_cols = [
        "ticker", "name", "group_id", "hakedaka_total_score",
        "qvm_rank", "qvm_grade", "overlap_status",
        "forward_return_5d", "forward_return_20d", "forward_return_60d", "forward_return_120d",
        "excess_vs_kospi200_20d", "shadow_only", "execution_authority",
    ]
    df[overlap_cols].to_csv(output_dir / "hakedaka_qvm_overlap.csv", index=False, encoding="utf-8-sig")

    _append_group_forward_csv(
        output_dir / "hakedaka_group_forward_return.csv",
        rows,
        as_of=as_of,
        run_id=run_id,
    )

    overlap_count = sum(1 for r in rows if r.overlap_status == "overlap")
    top5 = [
        {"ticker": r.ticker, "name": r.name, "score": r.hakedaka_total_score, "overlap": r.overlap_status}
        for r in rows[:5]
    ]

    summary = {
        "mode": "shadow_diagnostic_only",
        "authority": "none",
        "execution_authority": "none",
        "shadow_only": True,
        "diagnostic_only": True,
        "as_of": as_of,
        "run_id": run_id,
        "disclaimer": RERATING_DISCLAIMER,
        "candidate_count": len(rows),
        "preliminary_hunt_count": len(preliminary),
        "primary_hunt_count": len(primary),
        "verified_hunt_count": len(primary),
        "overlap_count": overlap_count,
        "hakedaka_only_count": sum(1 for r in rows if r.overlap_status == "hakedaka_only"),
        "top_quintile_threshold_score": rows[max(0, len(rows) // 5 - 1)].hakedaka_total_score if rows else None,
        "top_candidates": top5,
    }
    (output_dir / "hakedaka_rerating_shadow.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def build_daily_report_rerating_section(output_dir: Path | None) -> list[str]:
    if not output_dir:
        return []
    path = output_dir / "hakedaka_rerating_shadow.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    top = doc.get("top_candidates") or []
    lines = [
        "## Hakedaka Re-rating Screener (shadow only)",
        f"> {RERATING_DISCLAIMER}",
        f"- **후보**: {doc.get('candidate_count', 0)}종 · preliminary {doc.get('preliminary_hunt_count', 0)} · "
        f"verified primary {doc.get('primary_hunt_count', 0)} · "
        f"QVM overlap {doc.get('overlap_count', 0)} · hakedaka-only {doc.get('hakedaka_only_count', 0)}",
        f"- **shadow_only**: `{doc.get('shadow_only', True)}` · authority `{doc.get('execution_authority', 'none')}`",
    ]
    if top:
        lines.append("- **Top 5 (score)**: " + ", ".join(
            f"{t.get('name')}({t.get('score')})" for t in top[:5]
        ))
    lines.append("")
    return lines
