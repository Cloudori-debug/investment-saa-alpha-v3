from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_refresh.tier_h import collect_tier_h_tickers
from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals
from src.value_list.dart_disclosure import load_hakedaka_dart_signals

DATA_QUALITY_DISCLAIMER = (
    "Shadow diagnostic only. Low data_quality_score candidates are preliminary research only, "
    "not buy recommendations. v1.0.2 execution authority unchanged."
)

STALE_PRICE_DAYS = 7
STALE_DART_DAYS = 14
STALE_FUND_DAYS = 10


def _f(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _has(val: Any) -> bool:
    return val not in (None, "", "nan", "None")


def _days_since(d: str, as_of: str) -> int | None:
    if not d or not as_of:
        return None
    try:
        return (datetime.strptime(as_of[:10], "%Y-%m-%d") - datetime.strptime(d[:10], "%Y-%m-%d")).days
    except ValueError:
        return None


@dataclass
class HakedakaDataQualityRow:
    ticker: str
    name: str
    price_fresh: bool
    missing_price_flag: bool
    dart_event_fresh: bool
    fundamentals_fresh: bool
    ocf_available: bool
    fcf_available: bool
    debt_available: bool
    net_cash_available: bool
    shareholder_return_available: bool
    governance_event_checked: bool
    financial_safety_verified: bool
    shareholder_return_verified: bool
    evidence_completeness_pct: float
    data_incomplete: bool
    data_quality_score: float
    hunt_tier: str
    missing_fields: str
    shadow_only: bool = True
    execution_authority: str = "none"


def compute_data_quality_row(
    *,
    ticker: str,
    name: str,
    as_of: str,
    has_price: bool,
    price_date: str,
    dart: dict[str, Any],
    hk_fund: dict[str, Any] | None,
    generic_fund: dict[str, Any] | None,
    governance_events: int,
    treasury_events: list[dict[str, Any]] | None = None,
    evidence_missing_critical: int = 0,
) -> HakedakaDataQualityRow:
    price_fresh = has_price and (_days_since(price_date, as_of) or 99) <= STALE_PRICE_DAYS
    dart_date = str(dart.get("latest_date", ""))
    dart_fresh = bool(dart_date) and (_days_since(dart_date, as_of) or 99) <= STALE_DART_DAYS
    fund_date = ""
    if hk_fund:
        fund_date = str(hk_fund.get("usable_from_date") or hk_fund.get("as_of") or "")
    elif generic_fund:
        fund_date = str(generic_fund.get("usable_from_date") or generic_fund.get("report_date") or "")
    fund_fresh = bool(fund_date) and (_days_since(fund_date, as_of) or 99) <= STALE_FUND_DAYS

    ocf = _f((hk_fund or {}).get("operating_cash_flow") or (generic_fund or {}).get("operating_cash_flow"))
    fcf = _f((hk_fund or {}).get("free_cash_flow") or (generic_fund or {}).get("fcf"))
    debt = _f((hk_fund or {}).get("debt_ratio") or (generic_fund or {}).get("debt_ratio"))
    net_cash = _f((hk_fund or {}).get("net_cash"))
    shr = bool(
        dart.get("cancel_disclosure")
        or dart.get("return_disclosure")
        or _f((hk_fund or {}).get("shareholder_return_yield"))
        or _f((generic_fund or {}).get("dividend_yield"))
    )

    fin_safety_count = sum(
        1 for ok in (ocf is not None, fcf is not None, debt is not None, net_cash is not None) if ok
    )
    financial_safety_verified = fin_safety_count >= 3

    treasury_qty = False
    for ev in treasury_events or []:
        if _has(ev.get("announced_share_count")) or _has(ev.get("cancellation_share_count")):
            treasury_qty = True
            break
    shareholder_return_verified = treasury_qty or bool(
        _f((hk_fund or {}).get("treasury_share_ratio"))
        or dart.get("cancel_disclosure")
    )

    flags = {
        "price_fresh": price_fresh,
        "dart_event_fresh": dart_fresh,
        "fundamentals_fresh": fund_fresh,
        "ocf_available": ocf is not None,
        "fcf_available": fcf is not None,
        "debt_available": debt is not None,
        "net_cash_available": net_cash is not None,
        "shareholder_return_available": shr,
        "governance_event_checked": governance_events > 0 or bool(dart.get("latest_date")),
    }
    weights = {
        "price_fresh": 15,
        "dart_event_fresh": 15,
        "fundamentals_fresh": 10,
        "ocf_available": 12,
        "fcf_available": 10,
        "debt_available": 10,
        "net_cash_available": 10,
        "shareholder_return_available": 10,
        "governance_event_checked": 8,
    }
    score = sum(weights[k] for k, v in flags.items() if v)
    evidence_bonus = 0.0
    if financial_safety_verified:
        evidence_bonus += 5.0
    if shareholder_return_verified:
        evidence_bonus += 5.0
    if evidence_missing_critical >= 3:
        evidence_bonus = max(0.0, evidence_bonus - 8.0)
    score = min(100.0, score + evidence_bonus)
    evidence_completeness = round(
        fin_safety_count / 4 * 50 + (25 if shareholder_return_verified else 0) + (25 if shr else 0),
        1,
    )

    missing: list[str] = []
    if not has_price:
        missing.append("price")
    if not flags["ocf_available"]:
        missing.append("ocf")
    if not flags["fcf_available"]:
        missing.append("fcf")
    if not flags["debt_available"]:
        missing.append("debt")
    if not flags["net_cash_available"]:
        missing.append("net_cash")
    if not dart_fresh:
        missing.append("dart_stale")

    hunt_tier = "preliminary"
    if score >= 60:
        hunt_tier = "verified"
    if (
        score >= 75
        and flags["ocf_available"]
        and flags["debt_available"]
        and financial_safety_verified
        and evidence_missing_critical < 3
    ):
        hunt_tier = "actionable_candidate"

    return HakedakaDataQualityRow(
        ticker=ticker,
        name=name,
        price_fresh=price_fresh,
        missing_price_flag=not has_price,
        dart_event_fresh=dart_fresh,
        fundamentals_fresh=fund_fresh,
        ocf_available=flags["ocf_available"],
        fcf_available=flags["fcf_available"],
        debt_available=flags["debt_available"],
        net_cash_available=flags["net_cash_available"],
        shareholder_return_available=shr,
        governance_event_checked=flags["governance_event_checked"],
        financial_safety_verified=financial_safety_verified,
        shareholder_return_verified=shareholder_return_verified,
        evidence_completeness_pct=evidence_completeness,
        data_incomplete=score < 40 or not has_price,
        data_quality_score=round(float(score), 1),
        hunt_tier=hunt_tier,
        missing_fields=";".join(missing),
    )


def build_hakedaka_data_quality_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> list[HakedakaDataQualityRow]:
    from src.value_list.pipeline import load_watchlist
    from src.value_list.ticker_registry import resolve_hakedaka_registry

    registry = {str(r["ticker"]).zfill(6): str(r.get("name", "")) for r in resolve_hakedaka_registry(data_dir) if r.get("ticker")}
    hk_funds = load_hakedaka_fundamentals(data_dir)
    dart_doc = load_hakedaka_dart_signals(data_dir)
    dart_by = dart_doc.get("tickers") or {}

    generic_fund: dict[str, dict] = {}
    gf_path = data_dir / "fundamentals.csv"
    if gf_path.exists():
        df = pd.read_csv(gf_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            t = str(row["ticker"]).zfill(6)
            generic_fund[t] = dict(row)

    prices: dict[str, str] = {}
    px_path = data_dir / "prices.csv"
    if px_path.exists():
        df = pd.read_csv(px_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            t = str(row["ticker"]).zfill(6)
            prices[t] = str(row.get("date", ""))

    gov_counts: dict[str, int] = {}
    ev_path = output_dir / "hakedaka_dart_events.csv"
    if ev_path.exists():
        ev = pd.read_csv(ev_path, dtype=str, keep_default_na=False)
        for t in ev["ticker"].astype(str).str.zfill(6).unique():
            sub = ev[ev["ticker"].astype(str).str.zfill(6) == t]
            gov_counts[t] = len(sub[sub["event_types"].str.contains("governance|major_shareholder", na=False)])

    treasury_by: dict[str, list[dict[str, Any]]] = {}
    tr_path = output_dir / "hakedaka_treasury_events.csv"
    if tr_path.exists():
        tr = pd.read_csv(tr_path, dtype=str, keep_default_na=False)
        for _, tr_row in tr.iterrows():
            t = str(tr_row.get("ticker", "")).zfill(6)
            treasury_by.setdefault(t, []).append(dict(tr_row))

    evidence_missing: dict[str, int] = {}
    pack_path = output_dir / "hakedaka_top10_evidence_pack.json"
    if pack_path.exists():
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            for c in pack.get("candidates") or []:
                t = str(c.get("ticker", "")).zfill(6)
                evidence_missing[t] = len(c.get("missing_critical_fields") or [])
        except (json.JSONDecodeError, OSError):
            pass

    from src.value_list.hakedaka_manual_overrides import apply_manual_to_fundamentals, load_manual_overrides

    manual = load_manual_overrides(data_dir)

    rows: list[HakedakaDataQualityRow] = []
    for ticker, name in sorted(registry.items()):
        hk = apply_manual_to_fundamentals(hk_funds.get(ticker), manual.get(ticker))
        rows.append(
            compute_data_quality_row(
                ticker=ticker,
                name=name,
                as_of=as_of,
                has_price=ticker in prices,
                price_date=prices.get(ticker, ""),
                dart=dart_by.get(ticker, {}),
                hk_fund=hk,
                generic_fund=generic_fund.get(ticker),
                governance_events=gov_counts.get(ticker, 0),
                treasury_events=treasury_by.get(ticker),
                evidence_missing_critical=evidence_missing.get(ticker, 0),
            )
        )
    return rows


def apply_score_caps(
    scores: dict[str, float],
    quality: HakedakaDataQualityRow,
    *,
    dart: dict[str, Any],
    hk_fund: dict[str, Any] | None,
) -> dict[str, float]:
    """Phase 4a 점수 — 데이터 품질 기반 상한."""
    out = dict(scores)
    q = quality.data_quality_score

    if not quality.ocf_available and not quality.fcf_available:
        out["value_trap_safety_score"] = min(out.get("value_trap_safety_score", 0), 55.0)
    elif not quality.debt_available:
        out["value_trap_safety_score"] = min(out.get("value_trap_safety_score", 0), 65.0)

    if not quality.net_cash_available:
        out["valuation_asset_score"] = min(out.get("valuation_asset_score", 0), 70.0)

    if not quality.shareholder_return_available:
        out["shareholder_return_score"] = min(out.get("shareholder_return_score", 0), 65.0)

    dart_age = _days_since(str(dart.get("latest_date", "")), date.today().isoformat())
    if dart_age is not None and dart_age > 60:
        penalty = min(15.0, dart_age / 10)
        out["shareholder_return_score"] = max(0, out.get("shareholder_return_score", 0) - penalty)

    if q < 40:
        for k in out:
            out[k] = min(out[k], 60.0)

    if quality.missing_price_flag:
        for k in out:
            out[k] = min(out[k], 50.0)

    return {k: round(v, 2) for k, v in out.items()}


def write_hakedaka_data_quality_report(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    tier_h_coverage_pct: float = 0.0,
) -> dict[str, Any]:
    rows = build_hakedaka_data_quality_rows(data_dir, output_dir, as_of=as_of)
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(r) for r in rows])
    df.to_csv(output_dir / "hakedaka_data_quality_report.csv", index=False, encoding="utf-8-sig")

    required = collect_tier_h_tickers(data_dir)
    missing_price = [r.ticker for r in rows if r.missing_price_flag]
    low_quality = [r.ticker for r in rows if r.data_quality_score < 60]
    summary = {
        "mode": "shadow_diagnostic_only",
        "authority": "none",
        "shadow_only": True,
        "as_of": as_of,
        "disclaimer": DATA_QUALITY_DISCLAIMER,
        "tier_h_count": len(required),
        "tier_h_price_coverage_pct": tier_h_coverage_pct,
        "missing_price_count": len(missing_price),
        "missing_price_tickers": missing_price,
        "ocf_missing_count": sum(1 for r in rows if not r.ocf_available),
        "fcf_missing_count": sum(1 for r in rows if not r.fcf_available),
        "debt_missing_count": sum(1 for r in rows if not r.debt_available),
        "net_cash_missing_count": sum(1 for r in rows if not r.net_cash_available),
        "data_quality_below_60": len(low_quality),
        "verified_hunt_count": sum(1 for r in rows if r.hunt_tier == "verified"),
        "preliminary_count": sum(1 for r in rows if r.hunt_tier == "preliminary"),
        "avg_data_quality_score": round(sum(r.data_quality_score for r in rows) / len(rows), 1) if rows else 0,
        "financial_safety_verified_count": sum(1 for r in rows if r.financial_safety_verified),
        "shareholder_return_verified_count": sum(1 for r in rows if r.shareholder_return_verified),
        "avg_evidence_completeness_pct": round(
            sum(r.evidence_completeness_pct for r in rows) / len(rows), 1,
        ) if rows else 0,
    }
    (output_dir / "hakedaka_data_quality_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
