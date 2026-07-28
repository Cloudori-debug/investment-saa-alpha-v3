from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.data_refresh.dart_client import RateLimiter, dart_get

REPORT_CODES = {
    "11011": ("annual", "12-31"),
    "11012": ("semi", "06-30"),
    "11013": ("q1", "03-31"),
    "11014": ("q3", "09-30"),
}


@dataclass
class ReportMeta:
    corp_code: str
    bsns_year: str
    reprt_code: str
    rcept_no: str
    rcept_dt: str
    report_nm: str

    @property
    def period_end(self) -> str:
        suffix = REPORT_CODES[self.reprt_code][1]
        return f"{self.bsns_year}-{suffix}"

    @property
    def report_date(self) -> str:
        return f"{self.rcept_dt[:4]}-{self.rcept_dt[4:6]}-{self.rcept_dt[6:8]}"

    @property
    def usable_from_date(self) -> str:
        dt = datetime.strptime(self.report_date, "%Y-%m-%d") + timedelta(days=1)
        return dt.strftime("%Y-%m-%d")


def _parse_amount(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if not s or s == "-":
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _match_report_code(report_nm: str) -> str | None:
    name = report_nm or ""
    if "사업보고서" in name:
        return "11011"
    if "반기보고서" in name:
        return "11012"
    if "1분기" in name:
        return "11013"
    if "3분기" in name:
        return "11014"
    return None


def find_latest_report(
    corp_code: str,
    as_of: str,
    *,
    limiter: RateLimiter | None = None,
    lookback_years: int = 2,
) -> ReportMeta | None:
    as_of_dt = datetime.strptime(as_of[:10], "%Y-%m-%d")
    as_of_compact = as_of_dt.strftime("%Y%m%d")
    end_year = as_of_dt.year
    candidates: list[ReportMeta] = []

    for year in range(end_year, end_year - lookback_years, -1):
        bgn = f"{year}0101"
        end = f"{year}1231"
        if limiter:
            limiter.wait()
        data = dart_get(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": bgn,
                "end_de": end,
                "pblntf_ty": "A",
                "page_no": 1,
                "page_count": 100,
            },
        )
        for item in data.get("list", []) or []:
            report_nm = str(item.get("report_nm", ""))
            reprt_code = _match_report_code(report_nm)
            if not reprt_code:
                continue
            rcept_dt = str(item.get("rcept_dt", ""))
            if not rcept_dt or rcept_dt > as_of_compact:
                continue
            candidates.append(
                ReportMeta(
                    corp_code=corp_code,
                    bsns_year=str(year),
                    reprt_code=reprt_code,
                    rcept_no=str(item.get("rcept_no", "")),
                    rcept_dt=rcept_dt,
                    report_nm=report_nm,
                )
            )

    if not candidates:
        return None
    order = {"11014": 4, "11012": 3, "11013": 2, "11011": 1}
    candidates.sort(key=lambda x: (x.rcept_dt, order.get(x.reprt_code, 0)), reverse=True)
    return candidates[0]


def fetch_financial_accounts(
    meta: ReportMeta,
    *,
    limiter: RateLimiter | None = None,
    fs_div: str = "CFS",
) -> list[dict[str, Any]]:
    """Legacy single-meta fetch; prefer fetch_financial_accounts_with_fallback."""
    from src.data_refresh.dart_accounts_fetch import fetch_accounts_raw

    att = fetch_accounts_raw(
        meta.corp_code, meta.bsns_year, meta.reprt_code, fs_div, limiter=limiter,
    )
    if att.success:
        return att.rows
    if fs_div == "CFS":
        att_ofs = fetch_accounts_raw(
            meta.corp_code, meta.bsns_year, meta.reprt_code, "OFS", limiter=limiter,
        )
        return att_ofs.rows
    return []


def _find_amount(rows: list[dict], keywords: tuple[str, ...], *, sj_div: str | None = None, prefer: str = "thstrm") -> float | None:
    best = None
    for row in rows:
        if sj_div and row.get("sj_div") != sj_div:
            continue
        name = str(row.get("account_nm", ""))
        if not any(k in name for k in keywords):
            continue
        val = _parse_amount(row.get(f"{prefer}_amount") or row.get("thstrm_amount"))
        if val is not None:
            if name.strip() in keywords:
                return val
            best = val
    return best


def compute_metrics(rows: list[dict[str, Any]], meta: ReportMeta) -> dict[str, float | None]:
    revenue = _find_amount(rows, ("매출액", "영업수익", "수익(매출액)"), sj_div="IS")
    operating = _find_amount(rows, ("영업이익", "영업이익(손실)"), sj_div="IS")
    net_income = _find_amount(rows, ("당기순이익", "분기순이익", "당기순이익(손실)"), sj_div="IS")
    prior_net = _find_amount(rows, ("당기순이익", "분기순이익"), sj_div="IS", prefer="frmtrm")

    assets = _find_amount(rows, ("자산총계",), sj_div="BS")
    liabilities = _find_amount(rows, ("부채총계",), sj_div="BS")
    equity = _find_amount(rows, ("자본총계",), sj_div="BS")
    gross_profit = _find_amount(rows, ("매출총이익", "매출총이익(손실)"), sj_div="IS")
    interest = _find_amount(rows, ("이자비용", "금융비용"), sj_div="IS")
    ocf = _find_amount(
        rows,
        ("영업활동", "영업활동으로 인한 현금흐름", "영업활동현금흐름"),
        sj_div="CF",
    )
    capex = _find_amount(rows, ("유형자산의 취득", "유형자산 취득", "투자활동"), sj_div="CF")

    roe = round(net_income / equity * 100, 2) if net_income is not None and equity else None
    roa = round(net_income / assets * 100, 2) if net_income is not None and assets else None
    op_margin = round(operating / revenue * 100, 2) if operating is not None and revenue else None
    gross_prof = round(gross_profit / assets, 4) if gross_profit is not None and assets else None
    debt_ratio = round(liabilities / equity * 100, 2) if liabilities is not None and equity else None
    interest_cov = round(operating / interest, 2) if operating is not None and interest and interest != 0 else None
    fcf = None
    if ocf is not None and capex is not None:
        fcf = round(ocf - abs(capex), 2)
    elif ocf is not None:
        fcf = round(ocf, 2)

    earnings_yoy = None
    if net_income is not None and prior_net not in (None, 0):
        earnings_yoy = round((net_income - prior_net) / abs(prior_net), 4)

    return {
        "roe": roe,
        "roa": roa,
        "operating_margin": op_margin,
        "gross_profitability": gross_prof,
        "debt_ratio": debt_ratio,
        "interest_coverage": interest_cov,
        "fcf": fcf,
        "operating_cash_flow": ocf,
        "net_income": net_income,
        "earnings_yoy": earnings_yoy,
    }


def build_fundamental_record(
    ticker: str,
    meta: ReportMeta,
    metrics: dict[str, float | None],
    valuation: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    val = valuation or {}
    row: dict[str, Any] = {
        "ticker": ticker,
        "period_end": meta.period_end,
        "report_date": meta.report_date,
        "usable_from_date": meta.usable_from_date,
        "roe": metrics.get("roe"),
        "roa": metrics.get("roa"),
        "operating_margin": metrics.get("operating_margin"),
        "gross_profitability": metrics.get("gross_profitability"),
        "debt_ratio": metrics.get("debt_ratio"),
        "interest_coverage": metrics.get("interest_coverage"),
        "per": val.get("per"),
        "pbr": val.get("pbr"),
        "pcr": val.get("pcr"),
        "psr": val.get("psr"),
        "ev_ebitda": val.get("ev_ebitda"),
        "dividend_yield": val.get("dividend_yield"),
        "fcf": metrics.get("fcf"),
        "operating_cash_flow": metrics.get("operating_cash_flow"),
        "net_income": metrics.get("net_income"),
        "earnings_yoy": metrics.get("earnings_yoy"),
    }
    return row
