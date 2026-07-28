from __future__ import annotations

from src.value_list.hakedaka_catalyst_calibration import (
    REGRESSION_KOMERON_BODY,
    REGRESSION_SHINIL_BODY,
    apply_catalyst_calibration,
    run_catalyst_sanity_check,
)
from src.value_list.hakedaka_catalyst_calibration_runner import _regression_check
from src.value_list.hakedaka_treasury_extraction import extract_catalyst_from_body


def test_komeron_regression_not_one_share() -> None:
    cat = extract_catalyst_from_body(REGRESSION_KOMERON_BODY, "treasury_cancel")
    assert cat.get("cancellation_announced_shares") == 600_000.0
    assert cat.get("cancellation_announced_shares") != 1.0
    assert cat.get("cancellation_announced_amount") == 7_230_000_000.0
    assert cat.get("parse_suspect") is False
    assert cat.get("extraction_confidence") in ("high", "medium")


def test_shinil_regression_positive() -> None:
    cat = extract_catalyst_from_body(REGRESSION_SHINIL_BODY, "treasury_acquire")
    assert cat.get("buyback_announced_amount") == 1_999_361_000.0
    assert cat.get("buyback_announced_shares") == 1_651_000.0
    assert cat.get("extraction_confidence") == "high"
    assert cat.get("parse_suspect") is False


def test_sanity_downgrade_one_share_with_amount() -> None:
    raw = {
        "cancellation_announced_amount": 7_230_000_000.0,
        "cancellation_announced_shares": 1.0,
        "buyback_period_start": "",
        "buyback_period_end": "",
        "board_resolution_date": "2026-06-16",
        "extraction_confidence": "high",
    }
    out = apply_catalyst_calibration(raw, "treasury_cancel")
    assert out["parse_suspect"] is True
    assert out["extraction_confidence"] in ("low", "needs_review")


def test_regression_check_helpers() -> None:
    assert _regression_check("017890")["pass"] is True
    assert _regression_check("002700")["pass"] is True


def test_sanity_buyback_to_mcap_over_100() -> None:
    sanity = run_catalyst_sanity_check(
        {"buyback_announced_amount": 2_000_000_000_000.0, "buyback_announced_shares": 1_000_000.0},
        "treasury_acquire",
        market_cap=1_000_000_000_000.0,
    )
    assert sanity["parse_suspect"] is True
    assert "buyback_amount_to_market_cap_over_100pct" in sanity["sanity_reasons"]
