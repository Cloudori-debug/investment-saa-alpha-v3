"""Row-level flow strip — readable cue, no sibling app."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.flow_review_board import flow_chip_html, flow_inline_html


def _write_flows(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    header = (
        "date,ticker,name,foreign_net_value,institution_net_value,"
        "retail_net_value,program_net_value,foreign_5d_sum,institution_5d_sum,"
        "foreign_20d_sum,institution_20d_sum,foreign_5d_mcap_pct,"
        "institution_5d_mcap_pct,foreign_20d_mcap_pct,institution_20d_mcap_pct,"
        "flow_score,flow_signal,source,staleness_days\n"
    )
    row_acc = (
        "2026-10-08,005930,삼성전자,,,,,,,,,"
        "0.12,0.05,0.20,0.10,80.0,ACCUMULATION,test,0\n"
    )
    row_dist = (
        "2026-10-08,000660,SK하이닉스,,,,,,,,,"
        "-0.20,-0.10,-0.30,-0.15,20.0,DISTRIBUTION,test,0\n"
    )
    (data_dir / "investor_flows.csv").write_text(
        header + row_acc + row_dist, encoding="utf-8"
    )


def test_flow_strip_layout(tmp_path: Path) -> None:
    _write_flows(tmp_path)
    assert flow_chip_html(tmp_path, "005930") == ""
    html = flow_inline_html(tmp_path, "000660")
    assert "pf-flow-strip" in html
    assert "분산" in html
    assert "외인 5일" in html
    assert "기관 5일" in html
    assert "−0.20%" in html
    assert "수급 분산 ·" not in html  # no dense prose line


def test_missing_flow_placeholder(tmp_path: Path) -> None:
    html = flow_inline_html(tmp_path, "999999")
    assert "데이터 없음" in html
    assert "pf-flow-strip-muted" in html


def test_portfolio_uses_flow_strip() -> None:
    import inspect

    from alpha_system.ui.services import portfolio_widgets as pw

    src = inspect.getsource(pw)
    assert "flow_inline_html" in src
    assert "flow_data_dir" in src
