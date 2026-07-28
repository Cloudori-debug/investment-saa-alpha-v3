"""Holdings paste parse / upsert tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from alpha_system.ui.services.holdings_input import (
    parse_holdings_paste,
    upsert_kr_alpha_positions,
)


def test_parse_simple_lines() -> None:
    r = parse_holdings_paste("030200 100 45000\n021240 50 52000\n")
    assert not r.errors
    assert len(r.drafts) == 2
    by = {d.ticker: d for d in r.drafts}
    assert by["030200"].quantity == 100
    assert by["030200"].avg_price == 45000


def test_parse_name_prefix_and_comma() -> None:
    r = parse_holdings_paste("KT,030200,100,45000")
    assert len(r.drafts) == 1
    assert r.drafts[0].ticker == "030200"
    assert r.drafts[0].name == "KT"


def test_upsert_preserves_non_alpha(tmp_path: Path) -> None:
    root = tmp_path
    data = root / "data"
    data.mkdir()
    (data / "positions.csv").write_text(
        "ticker,name,asset_group,sector,style,quantity,current_value,avg_price,current_price\n"
        "CASH,예수금,cash_short_bond,cash,cash,1,1000000,,\n"
        "005830,DB손보,kr_alpha,, ,10,1000000,100000,\n",
        encoding="utf-8",
    )
    (data / "prices.csv").write_text(
        "date,ticker,close\n2026-07-28,030200,50000\n",
        encoding="utf-8",
    )
    parsed = parse_holdings_paste("030200 100 45000")
    result = upsert_kr_alpha_positions(
        data / "positions.csv",
        parsed.drafts,
        root=root,
        replace_alpha=True,
    )
    assert result["ok"] is True
    df = pd.read_csv(data / "positions.csv", dtype=str)
    assert (df["asset_group"] == "cash_short_bond").sum() == 1
    kr = df[df["asset_group"] == "kr_alpha"]
    assert len(kr) == 1
    assert str(kr.iloc[0]["ticker"]).zfill(6) == "030200"
    # old alpha gone
    assert "005830" not in set(kr["ticker"].astype(str).str.zfill(6))


def test_drafts_from_tickers_and_keep_zero(tmp_path: Path) -> None:
    from alpha_system.ui.services.holdings_input import drafts_from_tickers

    root = tmp_path
    data = root / "data"
    data.mkdir()
    (data / "positions.csv").write_text(
        "ticker,name,asset_group,sector,style,quantity,current_value,avg_price,current_price\n"
        "CASH,예수금,cash_short_bond,cash,cash,1,1000000,,\n",
        encoding="utf-8",
    )
    drafts = drafts_from_tickers(["030200", "021240"], root=root, quantity=0)
    result = upsert_kr_alpha_positions(
        data / "positions.csv",
        drafts,
        root=root,
        replace_alpha=True,
        keep_zero_qty=True,
    )
    assert result["alpha_count"] == 2
    df = pd.read_csv(data / "positions.csv", dtype=str)
    assert (df["asset_group"] == "cash_short_bond").sum() == 1
    assert (df["asset_group"] == "kr_alpha").sum() == 2


def test_load_positions_skips_zero_value(tmp_path: Path) -> None:
    from src.data_loader import load_positions

    path = tmp_path / "positions.csv"
    path.write_text(
        "ticker,name,asset_group,sector,style,quantity,current_value,avg_price,current_price\n"
        "CASH,예수금,cash_short_bond,cash,cash,1,1000000,,\n"
        "030200,KT,kr_alpha,,,0,0.0,,50000\n"
        "005830,DB손보,kr_alpha,,,10,1000000,100000,100000\n",
        encoding="utf-8",
    )
    rows = load_positions(path)
    tickers = {r.ticker for r in rows}
    assert tickers == {"CASH", "005830"}
    assert all(r.current_value > 0 for r in rows)
