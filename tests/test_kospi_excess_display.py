from __future__ import annotations

from src.report.export_daily_brief import _fmt_kospi_excess, build_daily_report_v2_sections


def test_kospi_excess_line_hides_number_when_stale() -> None:
    metrics = {
        "kr_alpha_return_mtd": 1.2595,
        "kospi200_return_mtd": None,
        "kospi200_return_quality": "stale_price",
        "kr_alpha_excess_vs_kospi200_mtd": None,
        "weak_alpha_regime": True,
    }
    text = _fmt_kospi_excess(metrics)
    assert text.startswith("n/a")
    assert "stale_price" in text
    # Explicitly deny treating alpha MTD as a real excess number
    assert "not 1.2595" in text
    assert not text.startswith("1.2595%p")


def test_daily_report_section_does_not_show_fake_excess() -> None:
    brief = {
        "system_status": {},
        "saa_taa": {},
        "shadow_diagnostic": {},
        "duration_sleeve": {},
        "alpha_v0_2": {},
        "core_saa_reference": {},
        "alpha_performance": {
            "mode": "shadow_diagnostic_only",
            "metrics": {
                "core_saa_return_mtd": -0.5,
                "actual_portfolio_return_mtd": 1.26,
                "actual_return_source": "holdings_price_return",
                "excess_return_vs_core_mtd": 1.76,
                "raw_nav_return_mtd": 35.0,
                "adjusted_nav_return_mtd": 3.8,
                "estimated_external_flow_mtd_krw": 1,
                "kr_alpha_return_mtd": 1.2595,
                "kospi200_return_mtd": None,
                "kospi200_return_quality": "stale_price",
                "kr_alpha_excess_vs_kospi200_mtd": None,
                "weak_alpha_regime": True,
                "theoretical_buy_count": 0,
                "executable_buy_count": 0,
            },
            "gate_opportunity_cost_count": 0,
        },
    }
    joined = "\n".join(build_daily_report_v2_sections(brief))
    assert "kr_alpha vs KOSPI200 MTD**: n/a (stale_price)" in joined
    assert "kr_alpha vs KOSPI200 MTD**: 1.2595%p" not in joined
