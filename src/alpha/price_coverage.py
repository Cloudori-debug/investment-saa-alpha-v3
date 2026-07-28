from __future__ import annotations

from typing import Any

from src.alpha.schemas import PriceRecord
from src.field_normalize import normalize_sector


def _norm_ticker(t: str) -> str:
    s = str(t).strip()
    return s.zfill(6) if s.isdigit() else s


def tickers_missing_prices(
    tickers: set[str] | list[str],
    prices_by_ticker: dict[str, PriceRecord],
) -> set[str]:
    """시세 dict에 없는 티커."""
    have = {_norm_ticker(t) for t in prices_by_ticker}
    normalized = {_norm_ticker(t) for t in tickers}
    return normalized - have


def apply_price_coverage_downgrade(
    rows: list[dict[str, Any]],
    prices_by_ticker: dict[str, PriceRecord],
) -> tuple[list[dict[str, Any]], list[str]]:
    """가격 미확보 종목 — proposal/target 편입 금지, research-only 고정."""
    missing = tickers_missing_prices({r["ticker"] for r in rows}, prices_by_ticker)
    warnings: list[str] = []
    out: list[dict[str, Any]] = []

    for row in rows:
        r = dict(row)
        ticker = str(r["ticker"])
        if ticker in missing:
            r["price_coverage_pass"] = False
            prev = str(r.get("eligible_action", ""))
            r["eligible_action"] = "NO_NEW"
            if str(r.get("grade", "")) in {"A", "B"}:
                r["grade"] = "C"
            note = "시세 미확보 — research-only"
            r["key_reason"] = f"{r.get('key_reason', '')}; {note}".strip("; ")
            warnings.append(f"{ticker}: {note} (eligible_action {prev}→NO_NEW)")
        else:
            r["price_coverage_pass"] = True
        out.append(r)

    return out, warnings


def adjust_gate_for_missing_prices(
    gate_status: str,
    *,
    missing_target_tickers: list[str],
    warn_threshold: int = 1,
) -> tuple[str, list[str]]:
    """목표 kr_alpha 시세 결측 시 gate 강화."""
    if not missing_target_tickers:
        return gate_status, []
    notes = [
        f"kr_alpha 목표 시세 미확보 {len(missing_target_tickers)}종 "
        f"({', '.join(missing_target_tickers[:5])}"
        f"{', …' if len(missing_target_tickers) > 5 else ''}) — proposal/target 편입 금지"
    ]
    if gate_status == "GREEN" and len(missing_target_tickers) >= warn_threshold:
        return "YELLOW", notes
    if gate_status != "RED":
        return gate_status, notes
    return gate_status, notes


def block_unknown_sector_proposal(row: dict[str, Any]) -> bool:
    """섹터 unknown + 시세 없음 — 제안 포트 제외."""
    sector = normalize_sector(row.get("sector", ""))
    if sector != "unknown":
        return False
    return row.get("price_coverage_pass") is False
