from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HORIZON_SCORE = {"추천": 8, "조건부": 4, "조건부추천": 4, "관찰": 1, "비추천": -4}
GRADE_SCORE = {"A": 40, "B": 30, "C": 20, "W": 10}
COMPLEXITY_SCORE = {"낮음": 5, "중간": 0, "높음": -8}
GROUP_PRIORITY = {2: 5, 4: 4, 1: 3, 3: 2, 5: 1}


@dataclass
class HakedakaScoreRow:
    no: int
    name: str
    ticker: str
    group_id: int
    group_label: str
    grade: str
    priority_bucket: str
    thesis_score: float
    pdf_total: float
    alpha_score: float | None
    market_score: float | None
    alignment_score: float | None
    dart_signal: str
    tracking_score: float
    rank: int
    in_positions: bool
    in_kr_alpha_target: bool
    in_alpha_shortlist: bool
    data_coverage: str
    horizon_short: str
    horizon_mid: str
    horizon_long: str
    complexity: str
    invest_type: str
    memo: str
    pbr: float | None = None
    per: float | None = None
    dividend_yield: float | None = None


def _horizon_points(short: str, mid: str, long: str) -> int:
    vals = [HORIZON_SCORE.get(short, 0), HORIZON_SCORE.get(mid, 0), HORIZON_SCORE.get(long, 0)]
    return max(vals) + sum(v for v in vals if v > 0) // 3


def compute_thesis_score(stock: dict[str, Any]) -> float:
    if stock.get("pdf_total") is not None:
        raw = float(stock["pdf_total"])
        return max(0.0, min(100.0, (raw + 10) / 77 * 100))
    base = GRADE_SCORE.get(str(stock.get("grade", "C"))[:1], 20)
    hp = _horizon_points(
        stock.get("horizon_short", "관찰"),
        stock.get("horizon_mid", "관찰"),
        stock.get("horizon_long", "관찰"),
    )
    cx = COMPLEXITY_SCORE.get(stock.get("complexity", "중간"), 0)
    gp = GROUP_PRIORITY.get(int(stock.get("group_id", 5)), 0)
    raw = base + hp + cx + gp
    return max(0.0, min(100.0, raw / 60 * 100))


def _market_score_from_fundamentals(fund: dict[str, Any] | None) -> float | None:
    if not fund:
        return None
    score = 50.0
    pbr = fund.get("pbr")
    per = fund.get("per")
    div = fund.get("dividend_yield")
    if pbr is not None and float(pbr) > 0:
        if float(pbr) < 0.5:
            score += 20
        elif float(pbr) < 1.0:
            score += 12
        elif float(pbr) < 1.5:
            score += 5
        elif float(pbr) > 3:
            score -= 10
    if per is not None and float(per) > 0:
        if float(per) < 8:
            score += 8
        elif float(per) > 25:
            score -= 5
    if div is not None and float(div) > 0:
        if float(div) >= 5:
            score += 10
        elif float(div) >= 3:
            score += 5
    return max(0.0, min(100.0, score))


def score_watchlist(
    stocks: list[dict[str, Any]],
    *,
    alpha_by_ticker: dict[str, dict[str, Any]],
    fundamentals_by_ticker: dict[str, dict[str, Any]],
    alignment_by_ticker: dict[str, float] | None = None,
    dart_signal_by_ticker: dict[str, str] | None = None,
    position_tickers: set[str],
    target_tickers: set[str],
    shortlist_tickers: set[str],
    group_labels: dict[int, str],
) -> list[HakedakaScoreRow]:
    rows: list[HakedakaScoreRow] = []
    for s in stocks:
        ticker = str(s.get("ticker", "")).strip()
        if ticker:
            ticker = ticker.zfill(6)
        else:
            ticker = ""
        thesis = compute_thesis_score(s)
        alpha = alpha_by_ticker.get(ticker)
        alpha_score = float(alpha["total_score"]) if alpha and alpha.get("total_score") is not None else None
        fund = fundamentals_by_ticker.get(ticker)
        market_score = _market_score_from_fundamentals(fund)
        align_map = alignment_by_ticker or {}
        dart_map = dart_signal_by_ticker or {}
        alignment_score = align_map.get(ticker)
        dart_signal = dart_map.get(ticker, "unknown")

        parts: list[tuple[float, float]] = [(thesis, 0.40)]
        if alpha_score is not None:
            parts.append((alpha_score, 0.30))
        if market_score is not None:
            parts.append((market_score, 0.15))
        if alignment_score is not None:
            parts.append((alignment_score, 0.15))
        wsum = sum(w for _, w in parts)
        tracking = sum(v * w for v, w in parts) / wsum if wsum else thesis

        coverage = []
        if fund:
            coverage.append("fund")
        if alignment_score is not None:
            coverage.append("align")
        if dart_signal not in ("", "unknown"):
            coverage.append(f"dart:{dart_signal}")
        if alpha_score is not None:
            coverage.append("alpha")
        if ticker in position_tickers:
            coverage.append("held")

        rows.append(
            HakedakaScoreRow(
                no=int(s["no"]),
                name=str(s["name"]),
                ticker=ticker,
                group_id=int(s["group_id"]),
                group_label=group_labels.get(int(s["group_id"]), ""),
                grade=str(s.get("grade", "")),
                priority_bucket=str(s.get("priority_bucket", "")),
                thesis_score=round(thesis, 1),
                pdf_total=float(s.get("pdf_total", 0)),
                alpha_score=round(alpha_score, 1) if alpha_score is not None else None,
                market_score=round(market_score, 1) if market_score is not None else None,
                alignment_score=round(alignment_score, 1) if alignment_score is not None else None,
                dart_signal=dart_signal,
                tracking_score=round(tracking, 1),
                rank=0,
                in_positions=ticker in position_tickers,
                in_kr_alpha_target=ticker in target_tickers,
                in_alpha_shortlist=ticker in shortlist_tickers,
                data_coverage=",".join(coverage) or "none",
                horizon_short=str(s.get("horizon_short", "")),
                horizon_mid=str(s.get("horizon_mid", "")),
                horizon_long=str(s.get("horizon_long", "")),
                complexity=str(s.get("complexity", "")),
                invest_type=str(s.get("invest_type", "")),
                memo=str(s.get("memo", "")),
                pbr=float(fund["pbr"]) if fund and fund.get("pbr") not in (None, "") else None,
                per=float(fund["per"]) if fund and fund.get("per") not in (None, "") else None,
                dividend_yield=float(fund["dividend_yield"]) if fund and fund.get("dividend_yield") not in (None, "") else None,
            )
        )

    rows.sort(key=lambda r: (-r.tracking_score, -r.thesis_score, r.no))
    for i, row in enumerate(rows, start=1):
        row.rank = i
    return rows
