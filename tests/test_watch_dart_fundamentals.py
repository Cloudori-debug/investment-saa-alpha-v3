from __future__ import annotations

import pandas as pd

from alpha_system.ui.services.watch_dart_fundamentals import (
    apply_watch_dart_rows,
    collect_watch_dart_financials,
    merge_watch_dart_row,
    watch_depth_tickers,
    watch_round_tickers,
)


def test_watch_depth_is_top_n_gate_pass() -> None:
    scores = pd.DataFrame(
        [
            {"ticker": "000003", "composite_score": 90.0, "gate_pass": True},
            {"ticker": "000001", "composite_score": 80.0, "gate_pass": True},
            {"ticker": "000002", "composite_score": 99.0, "gate_pass": False},
            {"ticker": "000004", "composite_score": 70.0, "gate_pass": True},
        ]
    )
    assert watch_depth_tickers(scores, depth=2) == ["000003", "000001"]


def test_second_round_darts_only_new_watch_names() -> None:
    first = ["000003", "000001"]
    after = pd.DataFrame(
        [
            {"ticker": "000004", "composite_score": 88.0, "gate_pass": True},
            {"ticker": "000003", "composite_score": 80.0, "gate_pass": True},
            {"ticker": "000001", "composite_score": 70.0, "gate_pass": True},
        ]
    )
    extra = watch_round_tickers(after, already=set(first), depth=2)
    assert extra == ["000004"]
    assert watch_round_tickers(after, already=set(first) | {"000004"}, depth=2) == []


def test_merge_watch_dart_fills_stub_quality_fields() -> None:
    row = pd.Series(
        {
            "ticker": "017800",
            "source": "liquid_stub",
            "verified": "stub",
            "roe": 7.0,
            "roe_3y_avg": 10.0,
            "opm": "",
            "debt_ratio": "",
            "per": 8.1,
            "pbr": 0.7,
        }
    )
    out = merge_watch_dart_row(
        row,
        {"opm": 12.5, "debt_ratio": 90.0, "roe": 11.2, "net_income_y1": 1e9, "net_income_y2": 8e8},
    )
    assert out["opm"] == 12.5
    assert out["debt_ratio"] == 90.0
    assert out["roe"] == 11.2
    assert out["per"] == 8.1
    assert out["source"] == "opendart_watch"
    assert out["verified"] == "dart"
    assert pd.isna(out["roe_3y_avg"])


def test_collect_watch_dart_uses_injected_fetch() -> None:
    def fake(ticker: str, as_of: str) -> dict:
        if ticker == "017800":
            return {"opm": 10.0, "debt_ratio": 40.0, "roe": 15.0}
        return {}

    filled, info = collect_watch_dart_financials(
        ["017800", "000001"],
        as_of="2026-09-05",
        fetch_one=fake,
    )
    assert info.requested == 2
    assert info.filled == 1
    assert "017800" in filled
    universe = pd.DataFrame(
        [{"ticker": "017800", "source": "liquid_stub", "opm": "", "debt_ratio": "", "roe": 7.0}]
    )
    merged = apply_watch_dart_rows(universe, filled)
    assert float(merged.iloc[0]["opm"]) == 10.0


def test_collect_copies_hakedaka_fields_from_fetch() -> None:
    def fake(ticker: str, as_of: str) -> dict:
        return {
            "opm": 10.0,
            "debt_ratio": 40.0,
            "roe": 15.0,
            "net_cash": 1e10,
            "treasury_share_ratio": 0.3,
            "largest_shareholder_pct": 16.1,
        }

    filled, info = collect_watch_dart_financials(
        ["017800"],
        as_of="2026-09-06",
        fetch_one=fake,
    )
    assert filled["017800"]["opm"] == 10.0
    assert info.hakedaka["017800"]["net_cash"] == 1e10
    assert info.hakedaka["017800"]["treasury_share_ratio"] == 0.3
    assert info.hakedaka["017800"]["largest_shareholder_pct"] == 16.1


def test_persist_hakedaka_upserts_and_keeps_extra(tmp_path) -> None:
    from alpha_system.sizing.hakedaka_screen import load_hakedaka_inputs
    from alpha_system.ui.services.watch_dart_fundamentals import persist_hakedaka_watch_rows

    path = tmp_path / "hakedaka_fundamentals.csv"
    path.write_text(
        "ticker,as_of,net_cash,net_cash_to_market_cap,free_cash_flow,"
        "related_party_risk_flag\n"
        "003240,2026-07-15,1,94.0,9,false\n",
        encoding="utf-8",
    )
    wrote = persist_hakedaka_watch_rows(
        path,
        {
            "100840": {
                "net_cash": 50_000_000_000,
                "treasury_share_ratio": 0.4,
                "largest_shareholder_pct": 15.2,
            }
        },
        market_caps={"100840": 1_000_000_000_000},
        as_of="2026-09-06",
    )
    assert wrote == 1
    text = path.read_text(encoding="utf-8-sig")
    assert "free_cash_flow" in text
    assert "003240" in text
    assert "100840" in text
    inputs = load_hakedaka_inputs(tmp_path, data_dir=tmp_path)
    assert inputs.net_cash_to_mcap["100840"] == 5.0
    assert inputs.treasury_ratio["100840"] == 0.4
    assert inputs.owner_pct["100840"] == 15.2
    assert inputs.net_cash_to_mcap["003240"] == 94.0


def test_hakedaka_from_accounts_owner_and_aliases() -> None:
    from alpha_system.ui.services.watch_dart_fundamentals import _hakedaka_from_accounts

    class _Limiter:
        def wait(self) -> None:
            return None

    def compute(accounts, meta):
        return {"net_cash": 1e9, "treasury_share_ratio": 0.5}

    def dart_get(path, params, **kwargs):
        assert path == "hyslrSttus.json"
        return {
            "list": [
                {"nm": "홍길동", "stock_knd": "보통주", "trmend_posesn_stock_rt": "16.2"},
            ]
        }

    out = _hakedaka_from_accounts(
        [],
        object(),
        corp="00123456",
        as_of="2026-09-06",
        limiter=_Limiter(),
        dart_get_fn=dart_get,
        compute_hakedaka_metrics=compute,
    )
    assert out["net_cash"] == 1e9
    assert out["treasury_share_ratio"] == 0.5
    assert out["largest_shareholder_pct"] == 16.2


def test_sync_hakedaka_from_payout_and_owners(tmp_path) -> None:
    import json

    from alpha_system.sizing.hakedaka_screen import evaluate_hakedaka, load_hakedaka_inputs
    from alpha_system.ui.services.watch_dart_fundamentals import (
        sync_hakedaka_from_opendart_caches,
    )

    data = tmp_path / "data"
    data.mkdir()
    (data / "opendart_payout_sr4.json").write_text(
        json.dumps({"rows": {"005930": {"buyback_3y": True, "quarters_hit": 2}}}),
        encoding="utf-8",
    )
    (data / "opendart_proposal_watch.json").write_text(
        json.dumps(
            {
                "metrics": [
                    {"ticker": "005930", "largest_shareholder_pct": 18.5},
                    {"ticker": "000660", "largest_shareholder_pct": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    n = sync_hakedaka_from_opendart_caches(
        tmp_path, data_dir=data, as_of="2026-09-24", owner_rows={}
    )
    assert n >= 1
    inputs = load_hakedaka_inputs(tmp_path, data_dir=data)
    assert inputs.owner_pct["005930"] == 18.5
    assert inputs.buyback["005930"] is True
    v = evaluate_hakedaka("005930", inputs, min_hits=2)
    assert v.treasury is True
    assert v.owner_band is True
    assert v.known >= 2


def test_hyslr_prefers_total_row() -> None:
    from datetime import date

    from alpha_system.ui.services.cecs_opendart_pack import _hyslr_owner_pct

    def dart_get(path, params, **kwargs):
        assert path == "hyslrSttus.json"
        return {
            "list": [
                {"nm": "홍길동", "stock_knd": "보통주", "trmend_posesn_stock_rt": "10"},
                {"nm": "합계", "trmend_posesn_stock_rt": "21.5"},
            ]
        }

    assert _hyslr_owner_pct(dart_get, "001", date(2026, 9, 24)) == 21.5
