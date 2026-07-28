from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.value_list.hakedaka_manual_overrides import load_manual_overrides
from src.value_list.hakedaka_treasury_events import scan_hakedaka_treasury_events
from src.value_list.ticker_registry import hakedaka_meta_by_ticker, resolve_hakedaka_registry

NAV_TREASURY_DISCLAIMER = (
    "Shadow diagnostic only. NAV/treasury metrics are not buy/sell recommendations. "
    "Execution authority remains v1.0.2 trade_actions only."
)

TREASURY_PRECISION_FIELDS = [
    "as_of", "ticker", "name",
    "treasury_share_count", "treasury_share_ratio", "treasury_share_value",
    "buyback_announced_amount", "buyback_announced_shares",
    "cancellation_announced_amount", "cancellation_announced_shares",
    "cancellation_completed_amount", "cancellation_completed_shares",
    "cancellation_progress_pct",
    "buyback_period_start", "buyback_period_end",
    "extraction_confidence", "text_evidence", "missing_reason",
]

NAV_PROXY_FIELDS = [
    "as_of", "ticker", "name", "group_id",
    "listed_subsidiary_ticker", "ownership_pct",
    "subsidiary_market_value", "ownership_adjusted_value",
    "holding_company_market_cap", "nav_discount_proxy_pct",
    "source", "manual_override",
]


def _f(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def build_treasury_precision_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> list[dict[str, Any]]:
    from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals

    funds = load_hakedaka_fundamentals(data_dir)
    registry = {
        str(r["ticker"]).zfill(6): str(r.get("name", ""))
        for r in resolve_hakedaka_registry(data_dir) if r.get("ticker")
    }
    events_by: dict[str, list[dict[str, Any]]] = {}
    ev_path = output_dir / "hakedaka_treasury_events.csv"
    if ev_path.exists():
        df = pd.read_csv(ev_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            t = str(row["ticker"]).zfill(6)
            events_by.setdefault(t, []).append(dict(row))

    rows: list[dict[str, Any]] = []
    for ticker, name in sorted(registry.items()):
        fund = funds.get(ticker, {})
        events = events_by.get(ticker, [])
        buybacks = [e for e in events if "acquire" in str(e.get("event_type", ""))]
        cancels = [e for e in events if "cancel" in str(e.get("event_type", ""))]

        buy_ann_amt = buy_ann_sh = cancel_ann_amt = cancel_ann_sh = None
        cancel_comp_amt = cancel_comp_sh = None
        p_start = p_end = ""
        conf = "none"
        text_parts: list[str] = []
        missing: list[str] = []

        if buybacks:
            latest = buybacks[0]
            buy_ann_amt = _f(latest.get("announced_amount"))
            buy_ann_sh = _f(latest.get("announced_share_count"))
            p_start = str(latest.get("buyback_period_start", ""))
            p_end = str(latest.get("buyback_period_end", ""))
            text_parts.append(str(latest.get("text_evidence", "")))
            conf = str(latest.get("extraction_confidence", "text_only"))
        if cancels:
            latest_c = cancels[0]
            cancel_ann_amt = _f(latest_c.get("cancellation_amount") or latest_c.get("announced_amount"))
            cancel_ann_sh = _f(latest_c.get("cancellation_share_count") or latest_c.get("announced_share_count"))
            text_parts.append(str(latest_c.get("text_evidence", "")))
            if conf == "none":
                conf = str(latest_c.get("extraction_confidence", "text_only"))

        treasury_ratio = _f(fund.get("treasury_share_ratio"))
        treasury_count = None
        treasury_value = _f(fund.get("treasury_shares_value_or_ratio"))
        if treasury_ratio is None and not buybacks and not cancels:
            missing.append("treasury_events")
        if treasury_ratio is None:
            missing.append("treasury_share_ratio")

        progress = None
        if cancel_ann_sh and cancel_comp_sh:
            progress = round(cancel_comp_sh / cancel_ann_sh * 100, 2)

        rows.append({
            "as_of": as_of,
            "ticker": ticker,
            "name": name,
            "treasury_share_count": treasury_count,
            "treasury_share_ratio": treasury_ratio,
            "treasury_share_value": treasury_value,
            "buyback_announced_amount": buy_ann_amt,
            "buyback_announced_shares": buy_ann_sh,
            "cancellation_announced_amount": cancel_ann_amt,
            "cancellation_announced_shares": cancel_ann_sh,
            "cancellation_completed_amount": cancel_comp_amt,
            "cancellation_completed_shares": cancel_comp_sh,
            "cancellation_progress_pct": progress,
            "buyback_period_start": p_start,
            "buyback_period_end": p_end,
            "extraction_confidence": conf,
            "text_evidence": " | ".join(p for p in text_parts if p)[:500],
            "missing_reason": ";".join(missing),
        })
    return rows


def build_nav_proxy_rows(
    data_dir: Path,
    *,
    as_of: str,
) -> list[dict[str, Any]]:
    from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals
    from src.value_list.hakedaka_manual_overrides import apply_manual_to_fundamentals

    meta_by = hakedaka_meta_by_ticker(data_dir)
    funds = load_hakedaka_fundamentals(data_dir)
    manual = load_manual_overrides(data_dir)
    px_path = data_dir / "prices.csv"
    mcap_by: dict[str, float] = {}
    if px_path.exists():
        df = pd.read_csv(px_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            try:
                mcap_by[str(row["ticker"]).zfill(6)] = float(row.get("market_cap") or 0)
            except (TypeError, ValueError):
                pass

    rows: list[dict[str, Any]] = []
    for ticker, meta in sorted(meta_by.items()):
        if int(meta.get("group_id", 0)) != 1:
            continue
        name = str(meta.get("name", ticker))
        fund = apply_manual_to_fundamentals(funds.get(ticker), manual.get(ticker))
        m = manual.get(ticker, {})
        nav_manual = _f(m.get("holding_company_nav_discount_override"))
        pbr = _f(fund.get("asset_value_discount_proxy"))
        nav_pct = nav_manual
        source = "manual" if nav_manual is not None else "pbr_proxy"
        if nav_pct is None and pbr is not None and pbr < 1:
            nav_pct = round((1 - pbr) * 100, 2)
        rows.append({
            "as_of": as_of,
            "ticker": ticker,
            "name": name,
            "group_id": 1,
            "listed_subsidiary_ticker": str(m.get("listed_subsidiary_ticker", "")),
            "ownership_pct": m.get("ownership_pct", ""),
            "subsidiary_market_value": m.get("subsidiary_market_value", ""),
            "ownership_adjusted_value": m.get("ownership_adjusted_value", ""),
            "holding_company_market_cap": mcap_by.get(ticker),
            "nav_discount_proxy_pct": nav_pct,
            "source": source if nav_pct is not None else "missing",
            "manual_override": bool(nav_manual is not None),
        })
    return rows


def merge_treasury_events_with_precision(
    output_dir: Path,
    precision_rows: list[dict[str, Any]],
) -> Path | None:
    """Extend hakedaka_treasury_events.csv with Phase 4f precision columns."""
    from src.value_list.hakedaka_treasury_events import TREASURY_CSV_FIELDS_EXTENDED

    events_path = output_dir / "hakedaka_treasury_events.csv"
    if not events_path.exists():
        return None
    prec_by = {str(r["ticker"]).zfill(6): r for r in precision_rows}
    df = pd.read_csv(events_path, dtype=str, keep_default_na=False)
    merged: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        out = dict(row)
        ticker = str(row.get("ticker", "")).zfill(6)
        prec = prec_by.get(ticker, {})
        for key in TREASURY_CSV_FIELDS_EXTENDED:
            if key not in out:
                out[key] = ""
        if "acquire" in str(out.get("event_type", "")):
            if not out.get("buyback_announced_amount"):
                out["buyback_announced_amount"] = out.get("announced_amount", "")
            if not out.get("buyback_announced_shares"):
                out["buyback_announced_shares"] = out.get("announced_share_count", "")
        if "cancel" in str(out.get("event_type", "")):
            if not out.get("cancellation_announced_amount"):
                out["cancellation_announced_amount"] = out.get("cancellation_amount", "")
            if not out.get("cancellation_announced_shares"):
                out["cancellation_announced_shares"] = out.get("cancellation_share_count", "")
        for key, val in prec.items():
            if key in ("as_of", "ticker", "name", "text_evidence"):
                continue
            if key in TREASURY_CSV_FIELDS_EXTENDED and str(out.get(key, "")).strip() in ("", "nan"):
                out[key] = val if val is not None else ""
        merged.append(out)
    with events_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TREASURY_CSV_FIELDS_EXTENDED, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)
    return events_path


def write_treasury_precision_csv(output_dir: Path, rows: list[dict[str, Any]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "hakedaka_treasury_precision.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TREASURY_PRECISION_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_nav_proxy_json(output_dir: Path, rows: list[dict[str, Any]], *, as_of: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "hakedaka_nav_proxy.json"
    with_nav = sum(1 for r in rows if r.get("nav_discount_proxy_pct") not in (None, ""))
    doc = {
        "as_of": as_of,
        "mode": "shadow_nav_proxy",
        "holding_company_count": len(rows),
        "nav_proxy_coverage_pct": round(with_nav / len(rows) * 100, 1) if rows else 0,
        "rows": rows,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_hakedaka_nav_treasury_precision(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    force_fundamentals: bool = True,
    rescan_treasury: bool = True,
) -> dict[str, Any]:
    """Phase 4f — NAV & Treasury Precision (shadow only)."""
    from src.settings.user_secrets import apply_secrets_to_env, credential_status
    from src.value_list.hakedaka_coverage_audit import write_hakedaka_coverage_audit
    from src.value_list.hakedaka_evidence_enrichment import build_hakedaka_top10_evidence_pack
    from src.value_list.hakedaka_fundamentals import enrich_hakedaka_fundamentals
    from src.value_list.hakedaka_manual_overrides import validate_manual_overrides

    as_of_date = as_of or date.today().isoformat()
    apply_secrets_to_env(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    registry = resolve_hakedaka_registry(data_dir)
    tickers = [str(r["ticker"]).zfill(6) for r in registry if r.get("ticker")]

    report: dict[str, Any] = {
        "as_of": as_of_date,
        "mode": "shadow_only",
        "phase": "4f",
        "disclaimer": NAV_TREASURY_DISCLAIMER,
        "steps": {},
    }

    cov_before: dict[str, Any] = {}
    audit_path = output_dir / "hakedaka_coverage_audit.json"
    if audit_path.exists():
        try:
            cov_before = json.loads(audit_path.read_text(encoding="utf-8")).get("coverage") or {}
        except (json.JSONDecodeError, OSError):
            pass
    report["coverage_before"] = cov_before

    if force_fundamentals:
        try:
            fr = enrich_hakedaka_fundamentals(data_dir, tickers, as_of=as_of_date, force=True)
            report["steps"]["fundamentals"] = {"enriched": fr.enriched, "skipped": fr.skipped}
        except Exception as exc:
            report["steps"]["fundamentals"] = {"error": str(exc)}

    if rescan_treasury and credential_status(data_dir).get("dart"):
        try:
            tr = scan_hakedaka_treasury_events(data_dir, output_dir, registry, as_of=as_of_date)
            report["steps"]["treasury_scan"] = tr
        except Exception as exc:
            report["steps"]["treasury_scan"] = {"error": str(exc)}

    treasury_rows = build_treasury_precision_rows(data_dir, output_dir, as_of=as_of_date)
    write_treasury_precision_csv(output_dir, treasury_rows)
    merge_treasury_events_with_precision(output_dir, treasury_rows)
    nav_rows = build_nav_proxy_rows(data_dir, as_of=as_of_date)
    write_nav_proxy_json(output_dir, nav_rows, as_of=as_of_date)

    with_precision = sum(
        1 for r in treasury_rows
        if r.get("treasury_share_ratio") not in (None, "")
        or r.get("buyback_announced_shares") not in (None, "")
        or r.get("cancellation_announced_shares") not in (None, "")
    )
    with_net_cash = 0
    ocf_annual_count = 0
    fund_path = data_dir / "hakedaka_fundamentals.csv"
    fund_total = 0
    if fund_path.exists():
        df = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
        fund_total = len(df)
        with_net_cash = sum(1 for v in df.get("net_cash", []) if str(v).strip() not in ("", "nan"))
        ocf_annual_count = sum(
            1 for v in df.get("ocf_annual", []) if str(v).strip() not in ("", "nan")
        )

    audit = write_hakedaka_coverage_audit(data_dir, output_dir, as_of=as_of_date)
    pack = build_hakedaka_top10_evidence_pack(data_dir, output_dir, as_of=as_of_date)

    report["coverage_after"] = audit.get("coverage") or {}
    manual_warnings = validate_manual_overrides(data_dir)
    report["manual_override_warnings"] = manual_warnings
    report["summary"] = {
        "treasury_precision_coverage_pct": round(with_precision / len(treasury_rows) * 100, 1) if treasury_rows else 0,
        "net_cash_ticker_count": with_net_cash,
        "nav_proxy_coverage_pct": round(
            sum(1 for r in nav_rows if r.get("nav_discount_proxy_pct") not in (None, "")) / len(nav_rows) * 100, 1,
        ) if nav_rows else 0,
        "holding_company_count": len(nav_rows),
        "evidence_pack_candidates": pack.get("candidate_count", 0),
        "alias_fix_ticker": "178320",
        "alias_fix_note": "영업활동으로 인한 순현금흐름액 + CIS + 단기/장기차입부채",
        "manual_override_warning_count": len(manual_warnings),
        "ocf_annual_coverage_pct": round(ocf_annual_count / fund_total * 100, 1) if fund_total else 0,
        "annual_vs_quarter_note": (
            "Dual-period fields: latest quarter for timeliness, annual for stability"
        ),
    }
    (output_dir / "hakedaka_phase4f_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report
