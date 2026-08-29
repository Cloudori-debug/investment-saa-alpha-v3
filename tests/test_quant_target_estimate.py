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
