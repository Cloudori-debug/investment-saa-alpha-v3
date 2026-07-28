from pathlib import Path


def test_hakedaka_alpha_bonus():
    from src.value_list.alpha_bridge import compute_hakedaka_alpha_bonus
    from src.value_list.ticker_registry import load_integration_config

    data = Path(__file__).resolve().parents[1] / "data"
    cfg = load_integration_config(data)
    meta = {"009680": {"name": "모토닉", "grade": "A", "priority_bucket": "핵심"}}
    ver = {
        "009680": {
            "verification_status": "verified",
            "dart_signal": "strong",
        }
    }
    bonus, tags = compute_hakedaka_alpha_bonus("009680", meta=meta, verification=ver, cfg=cfg)
    assert bonus <= 16
    assert bonus > 10
    assert tags["in_hakedaka"] is True
    assert tags["dart_verified"] is True


def test_liquidity_not_restored_to_scored_pool():
    from src.alpha.schemas import make_excluded
    from src.value_list.alpha_bridge import build_liquidity_pass_map

    data = Path(__file__).resolve().parents[1] / "data"
    hk = "009680"
    passed = []
    excluded = [make_excluded(hk, "모토닉", "20일 거래대금 부족", "min_20d_trading_value")]
    liq = build_liquidity_pass_map(passed, excluded, data)
    if hk in liq:
        assert liq[hk] is False


def test_overlap_diagnostics_writes(tmp_path):
    from src.alpha.schemas import UniverseRecord
    from src.value_list.overlap_diagnostics import write_hakedaka_overlap_diagnostics

    data = Path(__file__).resolve().parents[1] / "data"
    out = tmp_path / "outputs"
    path = write_hakedaka_overlap_diagnostics(
        data,
        out,
        universe=[UniverseRecord(ticker="005930", name="삼성전자")],
        excluded=[],
        graded=[],
        shortlist_tickers=set(),
        proposal_tickers=set(),
        prices_by_ticker={},
        filter_cfg={},
        as_of="2026-06-24",
        usable_fund_tickers=set(),
        scoring_cfg={"selection": {"min_pillar_score": {}, "min_pillars_pass": 3, "min_all_pillar_floor": 45}},
    )
    assert path.exists()
    import pandas as pd

    df = pd.read_csv(path)
    assert len(df) >= 49


def test_merge_hakedaka_universe(tmp_path):
    from src.alpha.schemas import UniverseRecord
    from src.value_list.alpha_bridge import merge_hakedaka_into_universe

    data = Path(__file__).resolve().parents[1] / "data"
    universe = [
        UniverseRecord(ticker="005930", name="삼성전자"),
    ]
    merged = merge_hakedaka_into_universe(universe, data)
    assert len(merged) > len(universe)


def test_verification_rows():
    from src.value_list.dart_verification import build_verification_rows

    data = Path(__file__).resolve().parents[1] / "data"
    rows = build_verification_rows(data, dart_payload={"as_of": "2026-06-24", "tickers": {}})
    assert len(rows) == 50
    assert all(r.name for r in rows)
