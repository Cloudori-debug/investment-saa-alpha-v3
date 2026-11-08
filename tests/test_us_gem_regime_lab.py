"""미국 ETF GEM 국면 Lab."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from alpha_system.shadow.us_gem_regime_lab import (
    US_STRATEGIES,
    run_us_gem_regime_lab,
    save_report,
    us_gem_regime_table_html,
)
from alpha_system.shadow.us_etf_prices import norm_us_ticker


ROOT = Path(__file__).resolve().parents[1]


def test_norm_us_ticker() -> None:
    assert norm_us_ticker("spy") == "SPY"
    assert norm_us_ticker("VXUS") == "VXUS"


def test_us_gem_regime_injected(tmp_path: Path) -> None:
    (tmp_path / "data" / "local").mkdir(parents=True)
    tickers = ["SPY", "EFA", "VXUS", "BIL", "AGG", "TLT", "GLD"]
    idx = pd.bdate_range("2012-01-03", periods=3600, freq="B")
    rng = np.random.default_rng(0)
    data = {}
    for i, tk in enumerate(tickers):
        rets = 0.0002 + i * 0.00001 + rng.normal(0, 0.005, size=len(idx))
        if tk == "BIL":
            rets = np.full(len(idx), 0.00005)
        px = 100.0 * np.cumprod(1.0 + rets)
        data[tk] = px
    panel = pd.DataFrame(data, index=idx)

    r_idx = pd.date_range("2012-01-01", periods=180, freq="ME")
    real = pd.Series(0.3, index=r_idx)
    real.loc[real.index >= "2022-01-01"] = 1.7
    dff = pd.Series(0.2, index=r_idx)
    dff.loc[dff.index >= "2022-01-01"] = 4.8
    stages = pd.Series(2, index=r_idx, dtype="Int64")
    stages.loc[stages.index >= "2022-01-01"] = 4

    report = run_us_gem_regime_lab(
        tmp_path,
        ensure_fetch=False,
        injected_panel=panel,
        injected_rates={"real": real, "dff": dff},
        injected_stages=stages,
    )
    assert report.writes_target is False
    assert report.ok
    ids = {s.id for s in report.strategies if s.ok}
    assert "dual_efa" in ids
    assert "dual_vxus" in ids
    assert "sixty_forty_us" in ids
    dual = next(s for s in report.strategies if s.id == "dual_efa")
    by = {x.regime: x for x in dual.slices}
    assert by["full"].ok
    assert by["high_fed"].ok
    path = save_report(tmp_path, report)
    assert path.is_file()
    html = us_gem_regime_table_html(report)
    assert "미국 ETF" in html
    assert len(US_STRATEGIES) >= 4


def test_backtest_wires_us_gem() -> None:
    page = (
        ROOT / "alpha_system" / "ui" / "pages" / "backtest.py"
    ).read_text(encoding="utf-8")
    assert "us_gem_regime_lab" in page
    assert "_render_us_gem_regime_lab" in page
