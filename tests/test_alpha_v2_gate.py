"""Alpha v2 gate stubs (cleanup phase 2) — alpha_v2/alpha_flow may be archived."""

from __future__ import annotations

from pathlib import Path

from src.alpha_v2_gate import (
    ENABLE_ALPHA_V2,
    alpha_v2_enabled,
    build_daily_report_alpha_v2_section,
    build_daily_report_flow_section,
    evaluate_standard_price_fetch,
    get_flow_for_ticker_unified,
    run_alpha_v2_shadow,
)


def test_alpha_v2_disabled_by_default() -> None:
    assert ENABLE_ALPHA_V2 is False
    assert alpha_v2_enabled() is False


def test_price_fetch_does_not_skip_when_disabled(tmp_path: Path) -> None:
    skip, reason = evaluate_standard_price_fetch(
        tmp_path, tmp_path, as_of="2026-07-15", run_mode="standard",
    )
    assert skip is False
    assert reason == "alpha_v2_disabled"


def test_shadow_runner_noops() -> None:
    assert run_alpha_v2_shadow(Path("data"), Path("outputs")) is None


def test_report_sections_show_disabled_note() -> None:
    v2 = "\n".join(build_daily_report_alpha_v2_section(Path("outputs")))
    flow = "\n".join(build_daily_report_flow_section(Path("outputs")))
    assert "ENABLE_ALPHA_V2=False" in v2
    assert "ENABLE_ALPHA_V2=False" in flow


def test_flow_unified_falls_back_to_legacy() -> None:
    # Should not ImportError even with packages archived.
    row = get_flow_for_ticker_unified(Path("data"), "005930")
    assert isinstance(row, dict)
