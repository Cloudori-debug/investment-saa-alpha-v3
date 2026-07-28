import pandas as pd

from src.ui.table_display import _format_cell_value, _column_header, trade_actions_column_config


def test_format_cell_number():
    cfg = trade_actions_column_config()
    assert _format_cell_value(1.5, "allowed_size_pct", cfg) == "1.50"
    assert _format_cell_value(None, "name", cfg) == ""


def test_column_header_uses_label():
    cfg = trade_actions_column_config()
    assert _column_header("ticker", cfg) == "코드"
