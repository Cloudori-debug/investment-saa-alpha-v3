from pathlib import Path

import pandas as pd

from src.data_loader import _parse_market_row, _repair_kospi_200ma
from src.data_refresh.market_indicators_refresh import _compute_kospi_metrics


def test_repair_kospi_200ma_from_history(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    hist = pd.DataFrame(
        [
            {"date": "2026-06-17", "kospi": "8801.49", "kospi_200ma": "7724.72"},
            {"date": "2026-06-24", "kospi": "8471.02", "kospi_200ma": "5227.01"},
        ]
    )
    hist.to_csv(data_dir / "market_indicators_history.csv", index=False)
    row = {"date": "2026-06-24", "kospi": 8471.02, "kospi_200ma": 5227.01}
    fixed = _repair_kospi_200ma(row, data_dir / "market_indicators.csv")
    assert fixed["kospi_200ma"] == 7724.72


def test_compute_kospi_metrics_preserves_prev_on_jump():
    import numpy as np

    # 급등 구간 + 짧은 lookback으로 200MA가 비정상적으로 낮게 나오는 경우
    closes = pd.DataFrame({"종가": np.concatenate([np.full(180, 5200.0), np.full(20, 8471.0)])})
    existing = {"kospi_200ma": "7724.72"}
    metrics, warnings = _compute_kospi_metrics(closes, existing=existing)
    assert metrics["kospi_200ma"] == 7724.72
    assert warnings
