from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

FUNDAMENTAL_COLUMNS = [
    "ticker", "period_end", "report_date", "usable_from_date",
    "roe", "roa", "operating_margin", "gross_profitability", "debt_ratio",
    "interest_coverage", "per", "pbr", "pcr", "psr", "ev_ebitda", "dividend_yield",
    "fcf", "operating_cash_flow", "net_income", "earnings_yoy",
]


@dataclass
class FundamentalsValidateResult:
    row_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def validate_fundamentals(data_dir: Path) -> FundamentalsValidateResult:
    path = data_dir / "fundamentals.csv"
    if not path.exists():
        return FundamentalsValidateResult(row_count=0, errors=["fundamentals.csv 없음"])

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    errors: list[str] = []
    warnings: list[str] = []

    missing = [c for c in FUNDAMENTAL_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"컬럼 누락: {', '.join(missing)}")

    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        usable = _parse_date(str(row.get("usable_from_date", "")))
        report = _parse_date(str(row.get("report_date", "")))
        if not usable:
            errors.append(f"{ticker}: usable_from_date 없음/형식 오류")
        elif report and usable < report:
            warnings.append(f"{ticker}: usable_from_date가 report_date보다 이름")
        if not str(row.get("period_end", "")).strip():
            warnings.append(f"{ticker}: period_end 없음")

    tickers = df["ticker"].astype(str).str.strip()
    if tickers.duplicated().any():
        dupes = tickers[tickers.duplicated()].unique().tolist()
        warnings.append(f"중복 ticker: {', '.join(dupes)}")

    return FundamentalsValidateResult(row_count=len(df), errors=errors, warnings=warnings)


def ensure_fundamentals_for_universe(data_dir: Path) -> list[str]:
    """universe 종목 중 fundamentals 없는 ticker 목록 반환 (자동 생성하지 않음)."""
    universe_path = data_dir / "universe.csv"
    fund_path = data_dir / "fundamentals.csv"
    if not universe_path.exists():
        return []
    universe = pd.read_csv(universe_path, dtype=str, keep_default_na=False)
    if fund_path.exists():
        fund = pd.read_csv(fund_path, dtype=str, keep_default_na=False)
        have = set(fund["ticker"].astype(str).str.strip())
    else:
        have = set()
    missing = []
    for t in universe["ticker"].astype(str).str.strip():
        if t not in have and t.isdigit():
            missing.append(t)
    return missing
