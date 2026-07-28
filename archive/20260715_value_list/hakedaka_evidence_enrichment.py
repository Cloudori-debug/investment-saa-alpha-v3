from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.value_list.hakedaka_fundamentals import (
    enrich_hakedaka_fundamentals,
    load_hakedaka_fundamentals,
)
from src.value_list.hakedaka_manual_overrides import (
    apply_manual_to_fundamentals,
    ensure_manual_overrides_template,
    load_manual_overrides,
    validate_manual_overrides,
)
from src.value_list.hakedaka_treasury_events import scan_hakedaka_treasury_events
from src.value_list.ticker_registry import resolve_hakedaka_registry

EVIDENCE_DISCLAIMER = (
    "Shadow evidence pack for human review only. No execution authority. "
    "v1.0.2 trade_actions and target_portfolio unchanged."
)

CRITICAL_FIELDS = (
    "operating_cash_flow",
    "free_cash_flow",
    "debt_ratio",
    "net_cash",
    "treasury_share_ratio",
    "holding_company_discount_proxy",
)


def write_hakedaka_financial_enrich_report(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> dict[str, Any]:
    """OCF/FCF/debt/net_cash 커버리지 및 missing_reason 리포트."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manual = load_manual_overrides(data_dir)
    funds_raw = load_hakedaka_fundamentals(data_dir)
    registry = {
        str(r["ticker"]).zfill(6): str(r.get("name", ""))
        for r in resolve_hakedaka_registry(data_dir)
        if r.get("ticker")
    }

    per_ticker: list[dict[str, Any]] = []
    ocf_ok = fcf_ok = debt_ok = net_cash_ok = 0
    total = len(registry) or 1

    for ticker, name in sorted(registry.items()):
        fund = apply_manual_to_fundamentals(funds_raw.get(ticker), manual.get(ticker))
        ocf = fund.get("operating_cash_flow")
        fcf = fund.get("free_cash_flow")
        debt = fund.get("debt_ratio")
        net_cash = fund.get("net_cash")
        if ocf not in (None, ""):
            ocf_ok += 1
        if fcf not in (None, ""):
            fcf_ok += 1
        if debt not in (None, ""):
            debt_ok += 1
        if net_cash not in (None, ""):
            net_cash_ok += 1
        per_ticker.append({
            "ticker": ticker,
            "name": name,
            "operating_cash_flow": ocf,
            "free_cash_flow": fcf,
            "debt_ratio": debt,
            "total_debt": fund.get("total_debt"),
            "cash_and_equivalents": fund.get("cash_and_equivalents"),
            "net_cash": net_cash,
            "capital_expenditure": fund.get("capital_expenditure"),
            "interest_coverage": fund.get("interest_coverage"),
            "missing_reason": fund.get("missing_reason", ""),
            "manual_override": bool(manual.get(ticker)),
        })

    report = {
        "mode": "shadow_only",
        "authority": "none",
        "as_of": as_of,
        "disclaimer": EVIDENCE_DISCLAIMER,
        "tier_h_count": len(registry),
        "coverage": {
            "ocf_pct": round(ocf_ok / total * 100, 1),
            "fcf_pct": round(fcf_ok / total * 100, 1),
            "debt_pct": round(debt_ok / total * 100, 1),
            "net_cash_pct": round(net_cash_ok / total * 100, 1),
            "ocf_count": ocf_ok,
            "fcf_count": fcf_ok,
            "debt_count": debt_ok,
            "net_cash_count": net_cash_ok,
        },
        "targets": {"ocf_pct": 70, "debt_pct": 70, "net_cash_pct": 60},
        "tickers": per_ticker,
    }
    (output_dir / "hakedaka_financial_enrich_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def _load_treasury_by_ticker(output_dir: Path) -> dict[str, list[dict[str, Any]]]:
    path = output_dir / "hakedaka_treasury_events.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, list[dict[str, Any]]] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        out.setdefault(t, []).append(dict(row))
    return out


def _load_treasury_precision(output_dir: Path, ticker: str) -> dict[str, Any]:
    path = output_dir / "hakedaka_treasury_precision.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    row = df[df["ticker"].astype(str).str.zfill(6) == ticker.zfill(6)]
    if row.empty:
        return {}
    return dict(row.iloc[0])


def _load_nav_proxy(output_dir: Path, ticker: str) -> dict[str, Any]:
    path = output_dir / "hakedaka_nav_proxy.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for r in doc.get("rows") or []:
            if str(r.get("ticker", "")).zfill(6) == ticker.zfill(6):
                return r
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _manual_review_items(
    fund: dict[str, Any],
    manual: dict[str, Any] | None,
    missing: list[str],
) -> list[str]:
    items: list[str] = list(missing)
    if not manual and "holding_company_discount_proxy" in missing:
        items.append("holding_company_nav_manual")
    if fund.get("fcf_confidence") == "medium":
        items.append("fcf_capex_unverified")
    return items


def _missing_critical(fund: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in CRITICAL_FIELDS:
        if fund.get(field) in (None, ""):
            missing.append(field)
    return missing


def _why_not_actionable(
    *,
    quality_score: float,
    missing: list[str],
    financial_safety_verified: bool,
    shareholder_return_verified: bool,
    hunt_tier: str,
) -> str:
    reasons: list[str] = []
    if quality_score < 75:
        reasons.append(f"data_quality_score={quality_score} (<75)")
    if not financial_safety_verified:
        reasons.append("financial_safety_not_verified (need 3+ of OCF/FCF/debt/net_cash)")
    if not shareholder_return_verified:
        reasons.append("shareholder_return_not_verified")
    if len(missing) >= 3:
        reasons.append(f"missing_critical_fields={len(missing)}")
    if hunt_tier != "actionable_candidate":
        reasons.append(f"hunt_tier={hunt_tier}")
    if not reasons:
        return "Still shadow-only — execution gate not connected in v1.0.2"
    return "; ".join(reasons)


def build_hakedaka_top10_evidence_pack(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> dict[str, Any]:
    """preliminary/verified 상위 10 evidence pack (human review, no execution)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pre_path = output_dir / "hakedaka_preliminary_hunt_list.csv"
    pri_path = output_dir / "hakedaka_primary_hunt_list.csv"
    if not pre_path.exists() and not pri_path.exists():
        return {"as_of": as_of, "skipped": "no_hunt_lists"}

    frames: list[pd.DataFrame] = []
    if pri_path.exists():
        frames.append(pd.read_csv(pri_path, dtype=str, keep_default_na=False))
    if pre_path.exists():
        frames.append(pd.read_csv(pre_path, dtype=str, keep_default_na=False))
    df = pd.concat(frames, ignore_index=True)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df = df.drop_duplicates(subset=["ticker"], keep="first")
    score_col = "hakedaka_total_score" if "hakedaka_total_score" in df.columns else "total_score"
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
    top = df.sort_values(score_col, ascending=False).head(10)

    manual = load_manual_overrides(data_dir)
    funds_raw = load_hakedaka_fundamentals(data_dir)
    treasury_by = _load_treasury_by_ticker(output_dir)
    from src.value_list.dart_disclosure import load_hakedaka_dart_signals

    dart_doc = load_hakedaka_dart_signals(data_dir)
    dart_by = dart_doc.get("tickers") or {}

    candidates: list[dict[str, Any]] = []
    for _, row in top.iterrows():
        ticker = str(row["ticker"]).zfill(6)
        name = str(row.get("name", ticker))
        fund = apply_manual_to_fundamentals(funds_raw.get(ticker), manual.get(ticker))
        dart = dart_by.get(ticker, {})
        treasury = treasury_by.get(ticker, [])
        missing = _missing_critical(fund)
        tr_prec = _load_treasury_precision(output_dir, ticker)
        nav_doc = _load_nav_proxy(output_dir, ticker)

        fin_count = sum(
            1 for k in ("operating_cash_flow", "free_cash_flow", "debt_ratio", "net_cash")
            if fund.get(k) not in (None, "")
        )
        financial_safety_verified = fin_count >= 3
        shr_qty = any(
            e.get("announced_share_count") not in (None, "")
            or e.get("cancellation_share_count") not in (None, "")
            or str(e.get("treasury_event_confidence", "")) in ("high", "medium")
            for e in treasury
        )
        shareholder_return_verified = shr_qty or bool(
            dart.get("cancel_disclosure") or fund.get("treasury_share_ratio")
        )

        quality_score = float(row.get("data_quality_score") or 0)
        hunt_tier = str(row.get("hunt_tier") or "preliminary")
        if len(missing) >= 3:
            hunt_tier = "preliminary" if hunt_tier == "actionable_candidate" else hunt_tier

        evidence_completeness = round(
            (6 - len(missing)) / 6 * 100
            + (10 if financial_safety_verified else 0)
            + (10 if shareholder_return_verified else 0),
            1,
        )

        candidates.append({
            "ticker": ticker,
            "name": name,
            "hakedaka_total_score": float(row.get(score_col) or 0),
            "data_quality_score": quality_score,
            "hunt_tier": hunt_tier,
            "financial_safety_verified": financial_safety_verified,
            "shareholder_return_verified": shareholder_return_verified,
            "evidence_completeness_pct": min(100.0, evidence_completeness),
            "valuation_summary": {
                "pbr_proxy": fund.get("asset_value_discount_proxy"),
                "holding_company_discount_proxy": fund.get("holding_company_discount_proxy"),
                "net_cash": fund.get("net_cash"),
                "net_cash_to_market_cap": fund.get("net_cash_to_market_cap"),
                "manual_override": bool(manual.get(ticker)),
            },
            "shareholder_return_evidence": {
                "treasury_events": treasury[:5],
                "treasury_share_ratio": fund.get("treasury_share_ratio"),
                "buyback_cancellation_progress": fund.get("buyback_cancellation_progress"),
                "dividend_policy_change_flag": fund.get("dividend_policy_change_flag"),
                "shareholder_return_yield": fund.get("shareholder_return_yield"),
            },
            "governance_evidence": {
                "governance_event_flag": fund.get("governance_event_flag"),
                "dart_cancel": dart.get("cancel_disclosure"),
                "dart_return": dart.get("return_disclosure"),
                "activist_manual": manual.get(ticker, {}).get("activist_event_override"),
            },
            "financial_safety_evidence": {
                "operating_cash_flow": fund.get("operating_cash_flow"),
                "free_cash_flow": fund.get("free_cash_flow"),
                "debt_ratio": fund.get("debt_ratio"),
                "total_debt": fund.get("total_debt"),
                "interest_coverage": fund.get("interest_coverage"),
                "missing_reason": fund.get("missing_reason"),
            },
            "missing_critical_fields": missing,
            "financial_latest_vs_annual_summary": {
                "ocf_latest_quarter": fund.get("ocf_latest_quarter"),
                "ocf_annual": fund.get("ocf_annual"),
                "fcf_latest_quarter": fund.get("fcf_latest_quarter"),
                "fcf_annual": fund.get("fcf_annual"),
                "debt_latest_quarter": fund.get("debt_latest_quarter"),
                "debt_annual": fund.get("debt_annual"),
                "fcf_confidence": fund.get("fcf_confidence"),
            },
            "treasury_precision_summary": tr_prec,
            "net_cash_summary": {
                "net_cash": fund.get("net_cash"),
                "net_cash_to_market_cap": fund.get("net_cash_to_market_cap"),
                "ncav": fund.get("ncav"),
                "ncav_to_market_cap": fund.get("ncav_to_market_cap"),
                "cash_and_equivalents": fund.get("cash_and_equivalents"),
                "short_term_financial_assets": fund.get("short_term_financial_assets"),
                "total_debt": fund.get("total_debt"),
            },
            "nav_discount_summary": nav_doc or {
                "nav_discount_proxy_pct": fund.get("nav_discount_proxy_pct"),
                "holding_company_discount_proxy": fund.get("holding_company_discount_proxy"),
            },
            "remaining_manual_review_items": _manual_review_items(fund, manual.get(ticker), missing),
            "why_not_actionable_yet": _why_not_actionable(
                quality_score=quality_score,
                missing=missing,
                financial_safety_verified=financial_safety_verified,
                shareholder_return_verified=shareholder_return_verified,
                hunt_tier=hunt_tier,
            ),
        })

    doc = {
        "mode": "shadow_evidence_pack",
        "authority": "none",
        "shadow_only": True,
        "as_of": as_of,
        "disclaimer": EVIDENCE_DISCLAIMER,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    (output_dir / "hakedaka_top10_evidence_pack.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return doc


def run_hakedaka_evidence_enrichment(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    force_fundamentals: bool = True,
    build_evidence_pack: bool = True,
    fetch_treasury: bool = True,
) -> dict[str, Any]:
    """Phase 4c — Hakedaka Evidence Enrichment (shadow only)."""
    as_of_date = as_of or date.today().isoformat()
    registry = resolve_hakedaka_registry(data_dir)
    tickers = [str(r["ticker"]).zfill(6) for r in registry if r.get("ticker")]
    report: dict[str, Any] = {"as_of": as_of_date, "mode": "shadow_only", "phase": "4c", "steps": {}}

    import os
    in_pytest = os.environ.get("PYTEST_CURRENT_TEST") is not None

    ensure_manual_overrides_template(data_dir)
    manual_warnings = validate_manual_overrides(data_dir)
    report["steps"]["manual_overrides"] = {"warnings": manual_warnings}

    fund_result: dict[str, Any] = {"ran": False}
    if not in_pytest or force_fundamentals:
        try:
            fr = enrich_hakedaka_fundamentals(
                data_dir, tickers, as_of=as_of_date, force=force_fundamentals,
            )
            fund_result = {
                "ran": fr.ran,
                "enriched": fr.enriched,
                "skipped": fr.skipped,
                "reason": fr.reason,
                "alias_enrich": True,
            }
        except Exception as exc:
            fund_result = {"error": str(exc)}
    report["steps"]["financial_enrich"] = fund_result

    treasury_result: dict[str, Any] = {"skipped": "pytest"}
    if fetch_treasury and not in_pytest:
        try:
            treasury_result = scan_hakedaka_treasury_events(
                data_dir, output_dir, registry, as_of=as_of_date,
            )
        except Exception as exc:
            treasury_result = {"error": str(exc)}
    report["steps"]["treasury_events"] = treasury_result

    fin_report = write_hakedaka_financial_enrich_report(data_dir, output_dir, as_of=as_of_date)
    report["steps"]["financial_enrich_report"] = fin_report.get("coverage", {})

    pack: dict[str, Any] = {"skipped": "build_evidence_pack=False"}
    if build_evidence_pack:
        pack = build_hakedaka_top10_evidence_pack(data_dir, output_dir, as_of=as_of_date)
    report["steps"]["evidence_pack"] = {
        "candidate_count": pack.get("candidate_count", 0),
        "skipped": pack.get("skipped"),
    }

    from src.value_list.hakedaka_data_quality import write_hakedaka_data_quality_report

    tier_h_cov = 0.0
    q_path = output_dir / "hakedaka_data_quality_report.json"
    if q_path.exists():
        try:
            tier_h_cov = float(json.loads(q_path.read_text(encoding="utf-8")).get("tier_h_price_coverage_pct", 0))
        except (json.JSONDecodeError, ValueError):
            pass
    quality = write_hakedaka_data_quality_report(
        data_dir, output_dir, as_of=as_of_date, tier_h_coverage_pct=tier_h_cov,
    )
    report["steps"]["data_quality_refresh"] = {
        "ocf_missing_count": quality.get("ocf_missing_count"),
        "financial_safety_verified_count": quality.get("financial_safety_verified_count"),
        "shareholder_return_verified_count": quality.get("shareholder_return_verified_count"),
    }
    return report
