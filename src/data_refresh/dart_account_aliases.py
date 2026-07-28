from __future__ import annotations

import re
from typing import Any

# field_key -> account name aliases (Korean + IFRS English labels seen in DART)
ACCOUNT_ALIASES: dict[str, tuple[str, ...]] = {
    "operating_cash_flow": (
        "영업활동현금흐름",
        "영업활동으로인한현금흐름",
        "영업활동으로 인한 현금흐름",
        "영업활동으로 인한 순현금흐름액",
        "영업활동에서창출된현금흐름",
        "CashFlowsFromUsedInOperatingActivities",
    ),
    "investing_cash_flow": (
        "투자활동현금흐름",
        "투자활동으로인한현금흐름",
        "CashFlowsFromUsedInInvestingActivities",
    ),
    "capex": (
        "유형자산의취득",
        "유형자산취득",
        "PurchaseOfPropertyPlantAndEquipment",
        "유형자산의 증가",
    ),
    "cash_and_equivalents": (
        "현금및현금성자산",
        "현금및현금성자산등",
        "CashAndCashEquivalents",
    ),
    "current_assets": ("유동자산",),
    "current_liabilities": ("유동부채",),
    "total_liabilities": ("부채총계",),
    "equity": ("자본총계", "지배기업소유주지분"),
    "short_term_borrowings": (
        "단기차입금",
        "단기차입",
        "단기차입부채",
        "유동성장기부채",
        "ShortTermBorrowings",
    ),
    "long_term_borrowings": (
        "장기차입금",
        "장기차입",
        "장기차입부채",
        "LongTermBorrowings",
    ),
    "bonds": ("사채", "회사채", "BondsIssued", "사채및회사채"),
    "treasury_shares": ("자기주식", "TreasuryShares"),
    "interest_expense": ("이자비용", "금융비용", "InterestExpense"),
    "operating_income": ("영업이익", "영업이익(손실)"),
    "net_income": ("당기순이익", "분기순이익", "당기순이익(손실)"),
    "short_term_financial_assets": (
        "단기금융상품",
        "단기금융자산",
        "기타금융자산",
    ),
}

IS_SJ_DIV = ("IS", "CIS")


def normalize_account_name(name: str) -> str:
    s = re.sub(r"[\s\u3000(),·\-]", "", str(name or ""))
    return s.lower()


def _alias_set(keywords: tuple[str, ...]) -> set[str]:
    return {normalize_account_name(k) for k in keywords}


def find_amount_aliases(
    rows: list[dict[str, Any]],
    field_key: str,
    *,
    sj_div: str | tuple[str, ...] | None = None,
    prefer: str = "thstrm",
) -> tuple[float | None, str]:
    """Return (amount, matched_account_name)."""
    from src.data_refresh.dart_financials import _parse_amount

    keywords = ACCOUNT_ALIASES.get(field_key, ())
    if not keywords:
        return None, ""
    targets = _alias_set(keywords)
    partial_best: tuple[float | None, str] | None = None
    sj_set: set[str] | None = None
    if sj_div is not None:
        sj_set = set(sj_div) if isinstance(sj_div, tuple) else {sj_div}

    for row in rows:
        row_sj = str(row.get("sj_div", ""))
        if sj_set is not None and row_sj not in sj_set:
            continue
        raw_name = str(row.get("account_nm", ""))
        norm = normalize_account_name(raw_name)
        val = _parse_amount(row.get(f"{prefer}_amount") or row.get("thstrm_amount"))
        if val is None:
            continue
        if norm in targets:
            return val, raw_name
        if any(t in norm or norm in t for t in targets):
            partial_best = (val, raw_name)

    if partial_best:
        return partial_best
    return None, ""


def compute_hakedaka_metrics(rows: list[dict[str, Any]], meta: Any) -> dict[str, Any]:
    """Alias-aware metrics for hakedaka fundamentals."""
    ocf, ocf_name = find_amount_aliases(rows, "operating_cash_flow", sj_div="CF")
    capex, capex_name = find_amount_aliases(rows, "capex", sj_div="CF")
    cash, _ = find_amount_aliases(rows, "cash_and_equivalents", sj_div="BS")
    cur_a, _ = find_amount_aliases(rows, "current_assets", sj_div="BS")
    cur_l, _ = find_amount_aliases(rows, "current_liabilities", sj_div="BS")
    liab, _ = find_amount_aliases(rows, "total_liabilities", sj_div="BS")
    equity, _ = find_amount_aliases(rows, "equity", sj_div="BS")
    st_b, _ = find_amount_aliases(rows, "short_term_borrowings", sj_div="BS")
    lt_b, _ = find_amount_aliases(rows, "long_term_borrowings", sj_div="BS")
    bonds, _ = find_amount_aliases(rows, "bonds", sj_div="BS")
    treasury, _ = find_amount_aliases(rows, "treasury_shares", sj_div="BS")
    interest, _ = find_amount_aliases(rows, "interest_expense", sj_div=IS_SJ_DIV)
    operating, _ = find_amount_aliases(rows, "operating_income", sj_div=IS_SJ_DIV)
    net_income, _ = find_amount_aliases(rows, "net_income", sj_div=IS_SJ_DIV)
    st_fin, _ = find_amount_aliases(rows, "short_term_financial_assets", sj_div="BS")

    total_debt = None
    parts = [x for x in (st_b, lt_b, bonds) if x is not None]
    if parts:
        total_debt = sum(parts)

    debt_ratio = round(liab / equity * 100, 2) if liab is not None and equity else None
    interest_cov = (
        round(operating / interest, 2) if operating is not None and interest and interest != 0 else None
    )

    fcf = None
    fcf_confidence = "none"
    if ocf is not None and capex is not None:
        fcf = round(ocf - abs(capex), 2)
        fcf_confidence = "high"
    elif ocf is not None:
        fcf = round(ocf, 2)
        fcf_confidence = "medium"

    net_cash = None
    cash_for_net = cash
    if cash is not None and st_fin is not None:
        cash_for_net = round(cash + st_fin, 2)
    if cash is not None and total_debt is not None:
        net_cash = round((cash_for_net or cash) - total_debt, 2)
    elif cash is not None:
        net_cash = round(cash_for_net or cash, 2)

    ncav = round(cur_a - cur_l, 2) if cur_a is not None and cur_l is not None else None
    treasury_ratio = round(abs(treasury) / equity * 100, 4) if treasury is not None and equity and equity > 0 else None

    missing: list[str] = []
    if ocf is None:
        missing.append("ocf")
    if fcf is None:
        missing.append("fcf")
    if debt_ratio is None:
        missing.append("debt_ratio")
    if net_cash is None:
        missing.append("net_cash")
    if cash is None:
        missing.append("cash")
    if total_debt is None:
        missing.append("total_debt")

    return {
        "operating_cash_flow": ocf,
        "fcf": fcf,
        "debt_ratio": debt_ratio,
        "interest_coverage": interest_cov,
        "cash_and_equivalents": cash,
        "total_debt": total_debt,
        "net_cash": net_cash,
        "ncav": ncav,
        "treasury_share_ratio": treasury_ratio,
        "treasury_shares_value_or_ratio": treasury_ratio if treasury_ratio is not None else treasury,
        "capital_expenditure": capex,
        "net_income": net_income,
        "short_term_financial_assets": st_fin,
        "current_assets": cur_a,
        "total_liabilities": liab,
        "fcf_confidence": fcf_confidence,
        "matched_ocf_account": ocf_name,
        "matched_capex_account": capex_name,
        "missing_reason": ";".join(missing),
    }
