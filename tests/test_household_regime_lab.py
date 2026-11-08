"""가계 Lab · 금리/긴축 국면 슬라이스."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from alpha_system.shadow.household_regime_lab import (
    household_regime_table_html,
    run_household_regime_lab,
    save_report,
)


ROOT = Path(__file__).resolve().parents[1]


def test_regime_lab_with_injected(tmp_path: Path) -> None:
    src = ROOT / "data" / "household_static_alloc.yaml"
    dest = tmp_path / "data"
    dest.mkdir(parents=True)
    (dest / "household_static_alloc.yaml").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "data" / "local").mkdir(parents=True, exist_ok=True)

    from alpha_system.shadow.household_alloc_lab import collect_tickers, load_recipes

    raw = load_recipes(tmp_path)
    tickers = collect_tickers(raw)
    idx = pd.bdate_range("2019-01-02", periods=1200, freq="B")
    data = {}
    for i, tk in enumerate(tickers):
        rets = 0.00025 + (i * 0.00001)
        px = 100.0 * (1.0 + rets) ** pd.Series(range(len(idx)), index=idx)
        data[tk] = px.values
    panel = pd.DataFrame(data, index=idx)

    # rates: low then high from 2022
    r_idx = pd.date_range("2019-01-01", periods=90, freq="ME")
    real = pd.Series(0.2, index=r_idx)
    real.loc[real.index >= "2022-01-01"] = 1.6
    dff = pd.Series(0.1, index=r_idx)
    dff.loc[dff.index >= "2022-01-01"] = 4.5
    stages = pd.Series(2, index=r_idx, dtype="Int64")
    stages.loc[stages.index >= "2022-01-01"] = 4

    report = run_household_regime_lab(
        tmp_path,
        ensure_fetch=False,
        injected_panel=panel,
        injected_rates={"real": real, "dff": dff},
        injected_stages=stages,
    )
    assert report.writes_target is False
    assert report.ok
    dual = next(s for s in report.strategies if s.id == "dual_momentum")
    by = {x.regime: x for x in dual.slices}
    assert by["full"].ok
    assert by["high_real"].ok
    assert by["high_fed"].ok
    assert by["since_2022"].ok
    path = save_report(tmp_path, report)
    assert path.is_file()
    html = household_regime_table_html(report)
    assert "국면" in html
    assert "듀얼" in html or "dual" in html.lower() or dual.name_ko in html


def test_backtest_page_wires_regime_lab() -> None:
    page = (
        ROOT / "alpha_system" / "ui" / "pages" / "backtest.py"
    ).read_text(encoding="utf-8")
    assert "household_regime_lab" in page
    assert "_render_household_regime_lab" in page
