"""가계 본체 Lab · 정적 차용 yaml · synthetic BT."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from alpha_system.shadow.household_alloc_lab import (
    collect_tickers,
    household_alloc_table_html,
    load_recipes,
    run_household_alloc_lab,
    save_report,
    validate_recipes,
)


ROOT = Path(__file__).resolve().parents[1]


def test_recipes_validate_and_sum_100() -> None:
    raw = load_recipes(ROOT)
    assert raw.get("writes_target") is False
    assert validate_recipes(raw) == []
    tickers = collect_tickers(raw)
    assert "360750" in tickers
    assert "453850" in tickers  # US long (TLT proxy) · not KR 10Y as core
    assert "329750" in tickers  # USD short cash
    assert "437080" in tickers  # US agg safe for dual
    # no leverage names
    for st in raw["strategies"]:
        if st.get("kind") != "static":
            continue
        for sl in st["sleeves"]:
            name = str(sl.get("name") or "")
            assert "레버리지" not in name
            assert "인버스" not in name


def test_lab_with_synthetic_panel(tmp_path: Path) -> None:
    # copy recipes into tmp root
    src = ROOT / "data" / "household_static_alloc.yaml"
    dest = tmp_path / "data"
    dest.mkdir(parents=True)
    (dest / "household_static_alloc.yaml").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "data" / "local").mkdir(parents=True, exist_ok=True)

    raw = load_recipes(tmp_path)
    tickers = collect_tickers(raw)
    idx = pd.bdate_range("2020-01-02", periods=800, freq="B")
    data = {}
    for i, tk in enumerate(tickers):
        # mild upward drift + different vol
        rets = 0.0003 + (i * 0.00002)
        px = 100.0 * (1.0 + rets) ** pd.Series(range(len(idx)), index=idx)
        # add tiny noise via cumulative
        data[tk] = px.values
    panel = pd.DataFrame(data, index=idx)

    report = run_household_alloc_lab(
        tmp_path, ensure_fetch=False, injected_panel=panel
    )
    assert report.writes_target is False
    assert report.ok
    assert any(s.ok and s.id == "sixty_forty" for s in report.strategies)
    assert any(s.id == "dual_momentum" for s in report.strategies)
    path = save_report(tmp_path, report)
    assert path.is_file()
    assert "writes_target" in path.read_text(encoding="utf-8")
    html = household_alloc_table_html(report)
    assert "pf-hh-lab" in html
    assert "60/40" in html


def test_backtest_page_wires_household_lab() -> None:
    page = (
        ROOT / "alpha_system" / "ui" / "pages" / "backtest.py"
    ).read_text(encoding="utf-8")
    assert "household_alloc_lab" in page
    assert "_render_household_alloc_lab" in page
