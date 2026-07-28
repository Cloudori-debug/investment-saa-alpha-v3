from __future__ import annotations

import html as html_module

import pandas as pd

from src.ui.copyable_table import dataframe_column_to_text, dataframe_to_tsv
from src.ui.table_display import target_portfolio_column_config


def test_render_copyable_table_escapes_html():
    """HTML 이스케이프 — escape 확인."""
    assert html_module.escape("<test>&") == "&lt;test&gt;&amp;"


def test_dataframe_to_tsv_includes_header_and_rows():
    df = pd.DataFrame(
        [
            {"ticker": "005830", "name": "DB손해보험", "target_weight": 5.5},
            {"ticker": "000660", "name": "SK하이닉스", "target_weight": 3.0},
        ]
    )
    cfg = target_portfolio_column_config()
    tsv = dataframe_to_tsv(df, column_config=cfg)
    lines = tsv.splitlines()
    assert lines[0].startswith("코드\t")
    assert "005830" in lines[1]
    assert "DB손해보험" in lines[1]
    assert len(lines) == 3


def test_dataframe_column_to_text_vertical():
    df = pd.DataFrame([{"ticker": "005830", "target_weight": 5.5}])
    cfg = target_portfolio_column_config()
    col_text = dataframe_column_to_text(df, "ticker", column_config=cfg)
    assert col_text.splitlines() == ["코드", "005830"]

    weight_text = dataframe_column_to_text(df, "target_weight", column_config=cfg)
    assert weight_text.splitlines()[0] == "목표(%)"
    assert weight_text.splitlines()[1] == "5.50"


def test_dataframe_to_tsv_empty():
    assert dataframe_to_tsv(pd.DataFrame(), column_config=None) == ""
