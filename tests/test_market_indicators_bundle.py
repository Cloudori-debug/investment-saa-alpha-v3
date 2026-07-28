from pathlib import Path

import pandas as pd

from src.data_loader import load_market_indicators_bundle, normalize_market_row


def test_bundle_export_raw_vs_normalized(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    hist = pd.DataFrame(
        [
            {"date": "2026-06-17", "kospi": "8801.49", "kospi_200ma": "7724.72"},
        ]
    )
    hist.to_csv(data_dir / "market_indicators_history.csv", index=False)
    pd.DataFrame(
        [
            {
                "date": "2026-06-24",
                "kospi": "8471.02",
                "kospi_200ma": "5227.01",
                "sp500": "7365",
                "sp500_recent_high": "7600",
                "vix": "19",
                "usdkrw": "1547",
                "korea_10y": "2.2",
                "oil_brent": "75",
                "gold": "4000",
                "foreign_flow_3d": "neutral",
                "regime": "YELLOW_STABLE",
            }
        ]
    ).to_csv(data_dir / "market_indicators.csv", index=False)

    bundle = load_market_indicators_bundle(data_dir / "market_indicators.csv")
    exp = bundle.to_export_dict()
    assert bundle.repair_applied
    assert exp["market_indicators_raw"]["kospi_200ma"] == 5227.01
    assert exp["market_indicators_normalized"]["kospi_200ma"] == 7724.72
    assert abs(bundle.kospi_vs_200ma_pct - 9.7) < 0.2
    assert abs(bundle.kospi_vs_200ma_pct_raw - 62.06) < 0.2


def test_normalize_market_row_no_repair_when_ratio_ok():
    row = {"kospi": 8471.02, "kospi_200ma": 7724.72}
    repaired, meta = normalize_market_row(row, None)
    assert not meta["repair_applied"]
    assert repaired["kospi_200ma"] == 7724.72
