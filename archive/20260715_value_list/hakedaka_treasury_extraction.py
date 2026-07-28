from __future__ import annotations

import re
from typing import Any

from src.value_list.hakedaka_catalyst_calibration import (
    apply_catalyst_calibration,
    is_share_match_suspect,
    parse_korean_number_token,
)

_COMPLETION_KWS = ("소각완료", "취득완료", "이행완료", "완료보고", "소각 실시", "취득 실시")
_ANNOUNCED_KWS = ("결정", "계획", "공시", "보고")


def _parse_number(s: str) -> float | None:
    s = str(s).replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _scale_amount(val: float, unit: str) -> float:
    u = unit.strip()
    if u in ("억", "억원"):
        return val * 100_000_000
    if u in ("백만", "백만원"):
        return val * 1_000_000
    if u in ("천", "천원"):
        return val * 1_000
    if u in ("만", "만원"):
        return val * 10_000
    if u in ("조", "조원"):
        return val * 1_000_000_000_000
    return val


def _scale_shares(val: float, unit: str) -> float:
    u = unit.strip()
    if u in ("천", "천주"):
        return val * 1_000
    if u in ("만", "만주"):
        return val * 10_000
    return val


def extract_amount_from_text(text: str) -> float | None:
    """Extract monetary amount from disclosure title/body text."""
    if not text:
        return None
    patterns = [
        r"([\d,]+(?:\.\d+)?)\s*(억|백만|천|만|조)\s*원",
        r"([\d,]+(?:\.\d+)?)\s*원",
        r"(?:취득|소각|매입|환원)\s*(?:금액|규모|한도)?\s*[:\s]*([\d,]+(?:\.\d+)?)\s*(억|백만|천|만)?",
        r"([\d,]+(?:\.\d+)?)\s*(억|백만|천|만)\b",
        r"(?:취득예정금액|소각금액|매입금액|금\s*액)\s*[:\s]*([\d,]+(?:\.\d+)?)\s*(억|백만|천|만|원)?",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        val = _parse_number(m.group(1))
        if val is None:
            continue
        unit = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
        return _scale_amount(val, unit or "")
    return None


def extract_shares_from_text(text: str) -> float | None:
    """Extract share count from disclosure text."""
    if not text:
        return None
    patterns = [
        r"소각할\s*주식.*?보통주식\s*\([^\)]*\)\s*([\d,]+)",
        r"취득예정주식\s*\([^\)]*\)\s*(?:보통주식\s*)?([\d,]+)",
        r"([\d,]+(?:\.\d+)?)\s*(천|만)\s*주",
        r"([\d,]+(?:\.\d+)?)\s*주\s*(?!당)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            if is_share_match_suspect(text, m):
                continue
            val = _parse_number(m.group(1))
            if val is None:
                val = parse_korean_number_token(m.group(1))
            if val is None:
                continue
            unit = ""
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                unit = str(m.group(2))
            scaled = _scale_shares(val, unit)
            if scaled > 1:
                return scaled
    return None


def extract_period_from_text(text: str) -> tuple[str, str]:
    start, end = "", ""
    m = re.search(
        r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2}).*?(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})",
        text,
    )
    if m:
        start = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        end = f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"
    return start, end


def detect_completion_status(text: str) -> str:
    t = str(text)
    if any(k in t for k in _COMPLETION_KWS):
        return "completed"
    if any(k in t for k in _ANNOUNCED_KWS):
        return "announced"
    return "unknown"


def classify_treasury_event_confidence(
    *,
    amount: float | None,
    shares: float | None,
    period_start: str,
    period_end: str,
    completion_status: str,
    event_type: str,
) -> str:
    has_amt = amount is not None and amount > 0
    has_sh = shares is not None and shares > 0
    has_period = bool(period_start and period_end)
    if has_amt and has_sh:
        return "high"
    if has_amt or has_sh:
        return "medium" if (has_period or completion_status != "unknown") else "medium"
    if has_period and "acquire" in event_type:
        return "medium"
    if completion_status == "completed" and (has_amt or has_sh):
        return "high"
    return "low"


def extract_treasury_event_details(text: str, event_type: str) -> dict[str, Any]:
    """Parse treasury disclosure text into structured fields."""
    combined = str(text or "")
    amount = extract_amount_from_text(combined)
    shares = extract_shares_from_text(combined)
    p_start, p_end = extract_period_from_text(combined)
    completion = detect_completion_status(combined)
    missing: list[str] = []

    if "acquire" in event_type:
        if amount is None:
            missing.append("buyback_amount")
        if shares is None:
            missing.append("buyback_shares")
    elif "cancel" in event_type:
        if amount is None:
            missing.append("cancellation_amount")
        if shares is None:
            missing.append("cancellation_shares")
    elif "dispose" in event_type:
        if amount is None and shares is None:
            missing.append("dispose_qty")

    conf = classify_treasury_event_confidence(
        amount=amount,
        shares=shares,
        period_start=p_start,
        period_end=p_end,
        completion_status=completion,
        event_type=event_type,
    )

    return {
        "amount": amount,
        "shares": shares,
        "period_start": p_start,
        "period_end": p_end,
        "completion_status": completion,
        "treasury_event_confidence": conf,
        "missing_reason": ";".join(missing),
    }


def classify_catalyst_extraction_confidence(
    *,
    amount: float | None,
    shares: float | None,
    period_start: str,
    period_end: str,
    event_type: str,
) -> str:
    """Phase 4h confidence: high if 2+ of amount/shares/period."""
    signals = sum([
        amount is not None and amount > 0,
        shares is not None and shares > 0,
        bool(period_start and period_end),
    ])
    if signals >= 2:
        return "high"
    if signals == 1 and event_type:
        return "medium"
    if event_type:
        return "low"
    return "low"


def extract_board_resolution_date(text: str) -> str:
    patterns = [
        r"이사회\s*결의\s*일?\s*[:\s]*(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})",
        r"결의\s*일\s*[:\s]*(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def extract_purpose(text: str, event_type: str) -> str:
    patterns = [
        r"(?:취득|소각|매입)\s*목적\s*[:\s]*(.{5,80}?)(?:\.|\n|2\.|3\.|$)",
        r"목\s*적\s*[:\s]*(.{5,80}?)(?:\.|\n|2\.|3\.|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:120]
    if "acquire" in event_type:
        return "shareholder_return" if "주주환원" in text else ""
    if "cancel" in event_type:
        return "treasury_cancellation" if "소각" in text else ""
    return ""


def _extract_labeled_amount(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        patterns = [
            rf"{label}\s*\([^\)]*\)\s*(?:보통주식\s*)?([\d,]+)",
            rf"{label}\s*[:\s]*([\d,]+(?:\.\d+)?)\s*(억|백만|천|만|조|원)?",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if not m:
                continue
            val = _parse_number(m.group(1))
            if val is None:
                continue
            unit = ""
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                unit = str(m.group(2)).replace("원", "")
            scaled = _scale_amount(val, unit)
            if scaled >= 1_000_000 or unit:
                return scaled
            if scaled >= 10_000:
                return scaled
    return None


def _extract_labeled_shares(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        patterns = [
            rf"{label}.*?보통주식\s*\([^\)]*\)\s*([\d,]+)",
            rf"{label}\s*\([^\)]*\)\s*(?:보통주식\s*)?([\d,]+)",
            rf"{label}\s*[:\s]*([\d,]+(?:\.\d+)?)\s*(천|만)?\s*주\s*(?!당)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.S)
            if not m or is_share_match_suspect(text, m):
                continue
            val = _parse_number(m.group(1)) or parse_korean_number_token(m.group(1))
            if val is None:
                continue
            unit = ""
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                unit = str(m.group(2))
            scaled = _scale_shares(val, unit)
            if scaled > 1:
                return scaled
    return None


def extract_catalyst_from_body(
    text: str,
    event_type: str,
    *,
    market_cap: float | None = None,
    shares_outstanding: float | None = None,
) -> dict[str, Any]:
    """Extract catalyst fields from full disclosure body text."""
    combined = str(text or "")
    if shares_outstanding is None:
        m = re.search(r"발행주식\s*총수.*?보통주식\s*\([^\)]*\)\s*([\d,]+)", combined, re.S)
        if m:
            shares_outstanding = _parse_number(m.group(1))
    completion = detect_completion_status(combined)
    p_start, p_end = extract_period_from_text(combined)
    board_date = extract_board_resolution_date(combined)
    purpose = extract_purpose(combined, event_type)

    buy_amt = buy_sh = cancel_ann_amt = cancel_ann_sh = None
    cancel_comp_amt = cancel_comp_sh = None
    missing: list[str] = []

    if "acquire" in event_type:
        buy_amt = _extract_labeled_amount(
            combined,
            ("취득예정금액", "취득 금액", "매입금액", "취득금액", "취득 한도"),
        )
        buy_sh = _extract_labeled_shares(
            combined,
            ("취득예정주식", "취득예정주식수", "취득 주식수", "매입주식수", "취득주식수"),
        )
        if buy_amt is None:
            buy_amt = extract_amount_from_text(combined)
        if buy_sh is None:
            buy_sh = extract_shares_from_text(combined)
        if buy_amt is None:
            missing.append("buyback_amount")
        if buy_sh is None:
            missing.append("buyback_shares")
    elif "cancel" in event_type:
        cancel_ann_amt = _extract_labeled_amount(
            combined,
            ("소각예정금액", "소각 금액", "소각금액"),
        )
        cancel_ann_sh = _extract_labeled_shares(
            combined,
            ("소각할 주식", "소각예정주식", "소각예정주식수", "소각 주식수", "소각주식수"),
        )
        if cancel_ann_amt is None:
            cancel_ann_amt = extract_amount_from_text(combined)
        if cancel_ann_sh is None:
            cancel_ann_sh = extract_shares_from_text(combined)
        if cancel_ann_amt is None:
            missing.append("cancellation_amount")
        if cancel_ann_sh is None:
            missing.append("cancellation_shares")
        if completion == "completed":
            cancel_comp_amt = cancel_ann_amt
            cancel_comp_sh = cancel_ann_sh

    if not board_date and "cancel" in event_type:
        m = re.search(r"소각\s*예정일\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", combined)
        if m:
            board_date = board_date or f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            if not p_end:
                p_end = board_date

    raw = {
        "buyback_announced_amount": buy_amt,
        "buyback_announced_shares": buy_sh,
        "cancellation_announced_amount": cancel_ann_amt,
        "cancellation_announced_shares": cancel_ann_sh,
        "cancellation_completed_amount": cancel_comp_amt,
        "cancellation_completed_shares": cancel_comp_sh,
        "buyback_period_start": p_start,
        "buyback_period_end": p_end,
        "board_resolution_date": board_date,
        "completion_status": completion,
        "purpose": purpose,
        "extraction_confidence": classify_catalyst_extraction_confidence(
            amount=buy_amt or cancel_ann_amt,
            shares=buy_sh or cancel_ann_sh,
            period_start=p_start,
            period_end=p_end,
            event_type=event_type,
        ),
        "missing_reason": ";".join(missing),
    }
    return apply_catalyst_calibration(
        raw, event_type, market_cap=market_cap, shares_outstanding=shares_outstanding,
    )


def enrich_event_row(row: dict[str, Any], *, body_text: str = "") -> dict[str, Any]:
    """Re-analyze a treasury event row with improved extraction."""
    event_type = str(row.get("event_type", ""))
    if body_text.strip():
        catalyst = extract_catalyst_from_body(body_text, event_type)
        out = dict(row)
        field_map = {
            "buyback_announced_amount": "announced_amount",
            "buyback_announced_shares": "announced_share_count",
            "cancellation_announced_amount": "cancellation_amount",
            "cancellation_announced_shares": "cancellation_share_count",
        }
        if "acquire" in event_type:
            for src, dst in field_map.items():
                if catalyst.get(src) is not None and not out.get(dst):
                    out[dst] = catalyst[src]
                if catalyst.get(src) is not None:
                    out[src] = catalyst[src]
        if "cancel" in event_type:
            for key in (
                "cancellation_announced_amount", "cancellation_announced_shares",
                "cancellation_completed_amount", "cancellation_completed_shares",
            ):
                if catalyst.get(key) is not None:
                    out[key] = catalyst[key]
                    if key.endswith("_amount"):
                        out["cancellation_amount"] = catalyst[key]
                    if key.endswith("_shares"):
                        out["cancellation_share_count"] = catalyst[key]
        for key in ("buyback_period_start", "buyback_period_end", "completion_status"):
            if catalyst.get(key) and not out.get(key):
                out[key] = catalyst[key]
        out["board_resolution_date"] = catalyst.get("board_resolution_date", "")
        out["purpose"] = catalyst.get("purpose", "")
        out["treasury_event_confidence"] = catalyst.get("extraction_confidence", "low")
        out["extraction_confidence"] = catalyst.get("extraction_confidence", "low")
        prev = str(out.get("missing_reason", "")).strip()
        new = catalyst.get("missing_reason", "")
        out["missing_reason"] = f"{prev};{new}".strip(";") if prev and new else (new or prev)
        out["body_extraction_used"] = True
        return out

    text = " ".join(
        str(row.get(k, ""))
        for k in ("source_report_name", "text_evidence", "announced_amount", "announced_share_count")
    )
    event_type = str(row.get("event_type", ""))
    details = extract_treasury_event_details(text, event_type)
    out = dict(row)

    amt = details["amount"]
    shares = details["shares"]
    if "acquire" in event_type:
        if not out.get("announced_amount") and amt is not None:
            out["announced_amount"] = amt
        if not out.get("announced_share_count") and shares is not None:
            out["announced_share_count"] = shares
        if not out.get("buyback_announced_amount") and amt is not None:
            out["buyback_announced_amount"] = amt
        if not out.get("buyback_announced_shares") and shares is not None:
            out["buyback_announced_shares"] = shares
    if "cancel" in event_type:
        if not out.get("cancellation_amount") and amt is not None:
            out["cancellation_amount"] = amt
        if not out.get("cancellation_share_count") and shares is not None:
            out["cancellation_share_count"] = shares
        if not out.get("cancellation_announced_amount") and amt is not None:
            out["cancellation_announced_amount"] = amt
        if not out.get("cancellation_announced_shares") and shares is not None:
            out["cancellation_announced_shares"] = shares
        if completion := details["completion_status"]:
            if completion == "completed":
                if amt is not None:
                    out["cancellation_completed_amount"] = amt
                if shares is not None:
                    out["cancellation_completed_shares"] = shares

    if not out.get("buyback_period_start") and details["period_start"]:
        out["buyback_period_start"] = details["period_start"]
    if not out.get("buyback_period_end") and details["period_end"]:
        out["buyback_period_end"] = details["period_end"]

    out["completion_status"] = details["completion_status"]
    out["treasury_event_confidence"] = details["treasury_event_confidence"]
    prev_missing = str(out.get("missing_reason", "")).strip()
    new_missing = details["missing_reason"]
    if prev_missing and new_missing:
        out["missing_reason"] = f"{prev_missing};{new_missing}"
    elif new_missing:
        out["missing_reason"] = new_missing

    legacy = str(out.get("extraction_confidence", ""))
    if legacy == "text_only" and details["treasury_event_confidence"] != "low":
        out["extraction_confidence"] = details["treasury_event_confidence"]
    elif not legacy:
        out["extraction_confidence"] = details["treasury_event_confidence"]

    return out
