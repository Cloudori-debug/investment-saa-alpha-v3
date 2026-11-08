"""장기 월간 GEM · 대공황 구간."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from alpha_system.shadow.long_gem_regime_lab import (
    long_gem_table_html,
    run_long_gem_regime_lab,
    save_report,
)


ROOT = Path(__file__).resolve().parents[1]


def test_long_gem_depression_window(tmp_path: Path) -> None:
    (tmp_path / "data" / "local").mkdir(parents=True)
    idx = pd.date_range("1926-07-31", periods=900, freq="ME")
    # crash 1929-1932 then recover
    rets = np.full(len(idx), 0.006)
    for i, dt in enumerate(idx):
        if pd.Timestamp("1929-09-01") <= dt <= pd.Timestamp("1932-06-30"):
            rets[i] = -0.04
        elif pd.Timestamp("1932-07-01") <= dt <= pd.Timestamp("1933-03-31"):
            rets[i] = 0.05
    us = 100 * np.cumprod(1.0 + rets)
    bil = 100 * np.cumprod(1.0 + np.full(len(idx), 0.002))
    panel = pd.DataFrame({"US": us, "BIL": bil}, index=idx)
    # EXUS only late
    panel["EXUS"] = panel["US"] * 0.95
    panel.loc[panel.index < "1990-07-01", "EXUS"] = np.nan
    rf = pd.Series(0.25, index=idx)
    rf.loc[rf.index >= "1975-01-01"] = 0.6  # ~7% ann

    report = run_long_gem_regime_lab(
        tmp_path,
        ensure_fetch=False,
        injected_panel=panel,
        injected_rf=rf,
        injected_rates={
            "real": pd.Series(dtype=float),
            "dff": pd.Series(dtype=float),
        },
        injected_stages=pd.Series(dtype="Int64"),
    )
    assert report.writes_target is False
    assert report.ok
    abs_row = next(s for s in report.strategies if s.id == "abs_us")
    us_row = next(s for s in report.strategies if s.id == "us_buyhold")
    by_abs = {x.regime: x for x in abs_row.slices}
    by_us = {x.regime: x for x in us_row.slices}
    assert by_abs["depression_core"].ok
    assert by_us["depression_core"].ok
    # absolute should lose less than buyhold in depression core
    assert by_abs["depression_core"].total_ret > by_us["depression_core"].total_ret
    path = save_report(tmp_path, report)
    assert path.is_file()
    html = long_gem_table_html(report)
    assert "대공황" in html


def test_backtest_wires_long_gem() -> None:
    page = (
        ROOT / "alpha_system" / "ui" / "pages" / "backtest.py"
    ).read_text(encoding="utf-8")
    assert "long_gem_regime_lab" in page
