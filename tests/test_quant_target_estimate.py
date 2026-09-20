"""Residual-income / justified P/B draft — literature identity, not KR-optimal."""

from __future__ import annotations

import pandas as pd

from src.alpha.quant_target_estimate import (
    COST_OF_EQUITY,
    G_CAP,
    estimate_quant_target,
    justified_pbr,
    markdown_target_fields,
    quant_portfolio_extra,
    sustainable_g,
)


def test_justified_pbr_textbook_identity() -> None:
    """CFA/Damodaran: ROE=16%, r=12%, g=10% → P/B = 3."""
    assert justified_pbr(0.16, 0.12, 0.10) == 3.0


def test_g_cap_prevents_perpetuity_blowup() -> None:
    g = sustainable_g(0.30, 0.20, g_cap=G_CAP)
    assert g == G_CAP
    pb = justified_pbr(0.30, COST_OF_EQUITY, g)
    assert pb is not None
    assert pb <= 4.0


def test_estimate_mixes_justified_and_peer() -> None:
    est = estimate_quant_target(
        roe=18.2,
        pbr=1.97,
        price=100400,
        payout=40,
        peer_pbr_median=2.2,
    )
    assert est.ok
    assert est.pbr_justified is not None
    assert est.pbr_draft is not None
    assert est.price_mid is not None
    assert est.price_lo <= est.price_mid <= est.price_hi
    assert est.price_justified is not None
    assert est.pbr_justified != est.pbr_draft or est.price_justified == est.price_mid


def test_missing_roe_falls_back_to_peer() -> None:
    est = estimate_quant_target(pbr=1.0, price=10000, peer_pbr_median=0.9)
    assert est.ok
    assert est.pbr_justified is None
    assert est.pbr_draft == 0.9


def test_markdown_fields_blank_when_not_ok() -> None:
    lines = markdown_target_fields({"quant_ok": False})
    assert "- pbr_max: _____" in lines
    filled = markdown_target_fields(
        {"quant_ok": True, "quant_pbr_draft": 1.7, "quant_price_mid": 45000.4}
    )
    assert "- pbr_max: 1.70" in filled
    assert "- target_price: 45000" in filled
    assert "_____" not in "\n".join(filled)


def test_quant_extra_uses_alpha_roe_when_ops_blank() -> None:
    extra = quant_portfolio_extra(
        "021240",
        fund_row={"pbr": 1.97, "dividend_yield": 1.95},
        price=100400,
        sector="consumer",
        fundamentals_df=pd.DataFrame(),
        alpha_row={"roe": 18.2, "sector_pbr_median": 2.2, "sector": "consumer"},
    )
    assert extra["quant_ok"] is True
    assert extra["quant_pbr_draft"] is not None
    assert extra["quant_price_mid"] is not None


def test_literature_target_ignores_peer_only_draft() -> None:
    from src.alpha.quant_target_estimate import literature_target_from_extra

    assert literature_target_from_extra({"quant_pbr_draft": 1.5}) is None
    got = literature_target_from_extra(
        {"quant_pbr_justified": 1.8, "quant_price_justified": 50000}
    )
    assert got == (1.8, 50000.0)


def test_mix_target_prefers_draft_over_justified() -> None:
    from src.alpha.quant_target_estimate import mix_target_from_extra

    mixed = mix_target_from_extra(
        {
            "quant_pbr_justified": 1.7,
            "quant_price_justified": 72000,
            "quant_pbr_draft": 1.44,
            "quant_price_mid": 266677,
        }
    )
    assert mixed == (1.44, 266677.0)
    assert mix_target_from_extra(
        {"quant_pbr_justified": 1.8, "quant_price_justified": 50000}
    ) == (1.8, 50000.0)
    assert mix_target_from_extra({"quant_pbr_draft": 0.9}) == (0.9, None)


def test_cyclical_uses_through_cycle_roe_not_peak_trailing() -> None:
    from src.alpha.quant_target_estimate import estimate_from_maps, is_cyclical_sector

    assert is_cyclical_sector("semiconductor")
    assert is_cyclical_sector("전기전자/반도체")
    assert not is_cyclical_sector("consumer")
    assert not is_cyclical_sector("insurance")

    peak = estimate_from_maps(
        "000660",
        fund={"roe": 22.0, "roe_3y_avg": 18.0, "pbr": 9.62, "sector": "semiconductor"},
        price=1_674_000,
        sector="semiconductor",
    )
    assert peak.ok
    assert peak.roe_source == "cycle_3y"
    assert peak.pbr_justified == 2.80
    assert "순환주 중기ROE 18%" in peak.note
    assert "최근 22%" in peak.note
    staple = estimate_from_maps(
        "271560",
        fund={"roe": 15.0, "roe_3y_avg": 14.2, "pbr": 1.34, "sector": "consumer"},
        price=130_000,
        sector="consumer",
    )
    assert staple.roe_source == "trailing"
    assert "순환주" not in staple.note


def test_cyclical_history_median_beats_3y_when_three_years() -> None:
    from src.alpha.quant_target_estimate import pick_target_roe

    chosen, src = pick_target_roe(
        trailing=40.0,
        roe_3y_avg=18.0,
        sector="semiconductor",
        history_values=[8.0, 12.0, 22.0],
    )
    assert src == "cycle_hist"
    assert abs(float(chosen) - 0.12) < 1e-9 or abs(float(chosen) - 12.0) < 1e-9
