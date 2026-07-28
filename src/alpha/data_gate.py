from __future__ import annotations

from datetime import datetime
from typing import Any

from src.alpha.schemas import FundamentalRecord, make_excluded


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def apply_data_gate(
    fundamentals: list[FundamentalRecord],
    config: dict[str, Any],
    as_of: str,
):
    """Point-in-time 재무 사용 가능 종목만 통과."""
    gate_cfg = config.get("data_gate", {})
    require_pit = bool(gate_cfg.get("require_point_in_time", True))
    stale_max = int(gate_cfg.get("stale_data_max_days", 120))

    as_of_dt = _parse_date(as_of)
    usable: dict[str, FundamentalRecord] = {}
    excluded = []
    limitations: list[str] = []

    for fund in fundamentals:
        if require_pit:
            usable_dt = _parse_date(fund.usable_from_date)
            if not usable_dt or not as_of_dt or as_of_dt < usable_dt:
                excluded.append(
                    make_excluded(
                        fund.ticker,
                        fund.ticker,
                        f"usable_from_date {fund.usable_from_date} 미도래",
                        "point_in_time",
                    )
                )
                continue
            report_dt = _parse_date(fund.report_date)
            if report_dt and as_of_dt and (as_of_dt - report_dt).days > stale_max:
                excluded.append(make_excluded(fund.ticker, fund.ticker, "재무 데이터 stale", "stale_data"))
                continue
        usable[fund.ticker] = fund

    if not usable:
        gate_status = "RED"
        limitations.append("사용 가능 재무 데이터 없음")
    elif len(excluded) > len(usable) * 0.5:
        gate_status = "YELLOW"
        limitations.append("재무 데이터 결측/지연 다수")
    else:
        gate_status = "GREEN"

    return usable, excluded, gate_status, limitations


def adjust_gate_for_sector_coverage(
    gate_status: str,
    kr_meta: dict[str, Any],
    *,
    unknown_threshold: float = 0.20,
) -> tuple[str, list[str]]:
    """섹터 미분류 비중이 크면 GREEN → YELLOW."""
    if gate_status != "GREEN":
        return gate_status, []
    weights = kr_meta.get("sector_weights") or {}
    total = sum(weights.values()) or 1.0
    unknown_w = float(weights.get("unknown", 0))
    if unknown_w / total >= unknown_threshold:
        share = unknown_w / total
        return (
            "YELLOW",
            [f"섹터 미분류(unknown) 비중 {share:.0%} ≥ {unknown_threshold:.0%} — alpha gate YELLOW"],
        )
    return gate_status, []


def evaluate_candidate_sector_data_gate(
    shortlist_unknown_rate: float,
    top10_unknown_rate: float,
    *,
    warn_threshold: float = 0.10,
    yellow_threshold: float = 0.30,
    data_limited_threshold: float = 0.50,
) -> tuple[str, list[str]]:
    """Display gate for alpha candidate sector quality — does not change PIT fundamentals gate."""
    notes: list[str] = []
    if top10_unknown_rate >= 1.0:
        notes.append(
            "상위 10 후보 sector 전부 unknown — alpha 자동매수 차단 (research/WATCH 유지)"
        )
        return "YELLOW_DATA_LIMITED", notes
    if shortlist_unknown_rate >= data_limited_threshold:
        share = shortlist_unknown_rate
        notes.append(
            f"shortlist sector unknown {share:.0%} ≥ {data_limited_threshold:.0%} — YELLOW_DATA_LIMITED"
        )
        return "YELLOW_DATA_LIMITED", notes
    if shortlist_unknown_rate > yellow_threshold:
        share = shortlist_unknown_rate
        notes.append(
            f"shortlist sector unknown {share:.0%} > {yellow_threshold:.0%} — alpha proposal 제한"
        )
        return "YELLOW", notes
    if shortlist_unknown_rate > warn_threshold:
        share = shortlist_unknown_rate
        notes.append(f"shortlist sector unknown {share:.0%} > {warn_threshold:.0%} — WARN")
        return "GREEN_WITH_WARN", notes
    return "GREEN", notes
