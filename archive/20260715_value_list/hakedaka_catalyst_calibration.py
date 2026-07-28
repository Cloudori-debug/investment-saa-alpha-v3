from __future__ import annotations

import re
from typing import Any

# Regression fixture texts (Phase 4h-1)
REGRESSION_KOMERON_BODY = (
    "한국알콜/주식소각 결정/(2026.06.16)주식소각 결정 "
    "1. 소각할 주식의 종류와 수 보통주식(주) 600,000 종류주식(주) - "
    "2. 발행주식총수 보통주식(주) 21,273,506 "
    "3. 1주당 가액(원) 500 "
    "4. 소각예정금액(원) 7,230,000,000 "
    "9. 이사회결의일 2026-06-16 "
    "7. 소각 예정일 2026-06-24"
)

REGRESSION_SHINIL_BODY = (
    "취득예정주식(주) 보통주식 1,651,000 "
    "취득예정금액(원) 보통주식 1,999,361,000 "
    "취득예상기간 시작일 2026년 06월 18일 종료일 2026년 09월 17일 "
    "9. 취득결정일 2026년 06월 17일"
)

_SHARE_FALSE_POSITIVE = re.compile(r"\d+\s*주\s*당")


def _f(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_korean_number_token(raw: str) -> float | None:
    """Parse 600,000 / 60만 / 600천 style tokens."""
    s = str(raw).strip().replace(",", "")
    if not s:
        return None
    m = re.match(r"^([\d.]+)\s*(만|천|억|백만)?$", s)
    if not m:
        try:
            return float(s)
        except ValueError:
            return None
    val = float(m.group(1))
    unit = m.group(2) or ""
    if unit == "만":
        return val * 10_000
    if unit == "천":
        return val * 1_000
    if unit == "억":
        return val * 100_000_000
    if unit == "백만":
        return val * 1_000_000
    return val


def run_catalyst_sanity_check(
    catalyst: dict[str, Any],
    event_type: str,
    *,
    market_cap: float | None = None,
    shares_outstanding: float | None = None,
) -> dict[str, Any]:
    """Return parse_suspect flag and sanity_reason list."""
    reasons: list[str] = []
    event_type = str(event_type)

    if "acquire" in event_type:
        amt = _f(catalyst.get("buyback_announced_amount"))
        sh = _f(catalyst.get("buyback_announced_shares"))
    elif "cancel" in event_type:
        amt = _f(catalyst.get("cancellation_announced_amount"))
        sh = _f(catalyst.get("cancellation_announced_shares"))
    else:
        amt = _f(catalyst.get("buyback_announced_amount") or catalyst.get("cancellation_announced_amount"))
        sh = _f(catalyst.get("buyback_announced_shares") or catalyst.get("cancellation_announced_shares"))

    buyback_to_mcap = None
    share_to_mcap = None
    if market_cap and market_cap > 0:
        if "acquire" in event_type and _f(catalyst.get("buyback_announced_amount")):
            buyback_to_mcap = _f(catalyst.get("buyback_announced_amount")) / market_cap * 100
        if sh and sh > 0 and shares_outstanding and shares_outstanding > 0:
            share_to_mcap = sh / shares_outstanding * 100

    if sh is not None and sh <= 1:
        reasons.append("share_count_unrealistically_small")
    if amt is not None and amt > 0 and (sh is None or sh <= 1):
        if "cancel" in event_type or "acquire" in event_type:
            reasons.append("amount_without_valid_share_count")
    if amt and sh and sh > 1:
        implied_price = amt / sh
        if implied_price > 50_000_000 or implied_price < 50:
            reasons.append("implied_price_out_of_range")
    if buyback_to_mcap is not None and buyback_to_mcap >= 100:
        reasons.append("buyback_amount_to_market_cap_over_100pct")
    if amt and amt > 0 and sh and sh > 1 and market_cap and market_cap > 0:
        if buyback_to_mcap is None and "acquire" in event_type:
            buyback_to_mcap = amt / market_cap * 100

    parse_suspect = bool(reasons)
    return {
        "parse_suspect": parse_suspect,
        "sanity_reasons": reasons,
        "buyback_amount_to_market_cap": round(buyback_to_mcap, 4) if buyback_to_mcap is not None else None,
        "share_count_to_market_cap": round(share_to_mcap, 4) if share_to_mcap is not None else None,
    }


def classify_calibrated_confidence(
    catalyst: dict[str, Any],
    event_type: str,
    sanity: dict[str, Any],
) -> str:
    """Phase 4h-1 confidence with downgrade rules."""
    if sanity.get("parse_suspect"):
        has_partial = any(
            _f(catalyst.get(k)) not in (None, 0)
            for k in (
                "buyback_announced_amount", "buyback_announced_shares",
                "cancellation_announced_amount", "cancellation_announced_shares",
            )
        )
        return "needs_review" if has_partial else "low"

    event_type = str(event_type)
    if "acquire" in event_type:
        amt_ok = _f(catalyst.get("buyback_announced_amount")) not in (None, 0)
        sh_ok = _f(catalyst.get("buyback_announced_shares")) not in (None, 0) and _f(catalyst.get("buyback_announced_shares")) > 1
    elif "cancel" in event_type:
        amt_ok = _f(catalyst.get("cancellation_announced_amount")) not in (None, 0)
        sh_ok = _f(catalyst.get("cancellation_announced_shares")) not in (None, 0) and _f(catalyst.get("cancellation_announced_shares")) > 1
    else:
        amt_ok = sh_ok = False

    period_ok = bool(catalyst.get("buyback_period_start") and catalyst.get("buyback_period_end"))
    board_ok = bool(catalyst.get("board_resolution_date"))
    timing_ok = period_ok or board_ok

    has_signal = amt_ok or sh_ok
    both_ok = amt_ok and sh_ok

    if not event_type:
        return "low"
    if not has_signal:
        return "low"
    if both_ok and timing_ok:
        return "high"
    if has_signal and timing_ok:
        return "high" if both_ok else "medium"
    if has_signal:
        return "medium"
    return "low"


def apply_catalyst_calibration(
    catalyst: dict[str, Any],
    event_type: str,
    *,
    market_cap: float | None = None,
    shares_outstanding: float | None = None,
) -> dict[str, Any]:
    """Merge sanity + calibrated confidence into catalyst dict."""
    out = dict(catalyst)
    sanity = run_catalyst_sanity_check(
        out, event_type, market_cap=market_cap, shares_outstanding=shares_outstanding,
    )
    conf = classify_calibrated_confidence(out, event_type, sanity)
    out["parse_suspect"] = sanity["parse_suspect"]
    out["sanity_reasons"] = ";".join(sanity["sanity_reasons"])
    out["buyback_amount_to_market_cap"] = sanity.get("buyback_amount_to_market_cap")
    out["share_count_to_market_cap"] = sanity.get("share_count_to_market_cap")
    out["extraction_confidence"] = conf
    out["extraction_confidence_raw"] = catalyst.get("extraction_confidence", conf)
    if sanity["parse_suspect"]:
        prev = str(out.get("missing_reason", "")).strip()
        extra = f"sanity:{sanity['sanity_reasons']}"
        out["missing_reason"] = f"{prev};{extra}".strip(";") if prev else extra
    return out


def is_share_match_suspect(text: str, match: re.Match[str]) -> bool:
    """Detect false positives like '1주당 가액'."""
    start = match.start()
    window = text[max(0, start - 2): match.end() + 2]
    return bool(_SHARE_FALSE_POSITIVE.search(window))
