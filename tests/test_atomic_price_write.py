from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_refresh.price_store import atomic_write_csv, inspect_csv_bytes


def test_inspect_csv_detects_nul(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_bytes(b"date,ticker\n2026-01-01,069500\n" + b"\x00" * 50)
    info = inspect_csv_bytes(p)
    assert info["nul_bytes"] == 50
    assert info["ok"] is False
    assert info["first_nul_at"] > 0


def test_atomic_write_replaces_and_has_no_nul(tmp_path: Path) -> None:
    path = tmp_path / "prices_history.csv"
    path.write_text("date,ticker,close\n2026-01-01,000001,1\n", encoding="utf-8-sig")
    df = pd.DataFrame([
        {"date": "2026-01-01", "ticker": "000001", "close": 1},
        {"date": "2026-01-02", "ticker": "069500", "close": 2},
    ])
    info = atomic_write_csv(path, df, required_tickers=["069500"])
    assert info["replaced"] is True
    raw = path.read_bytes()
    assert b"\x00" not in raw
    assert inspect_csv_bytes(path)["ok"] is True
    out = pd.read_csv(path, dtype={"ticker": str})
    assert len(out) == 2
    assert "069500" in set(out["ticker"])


def test_atomic_write_aborts_on_row_shrink(tmp_path: Path) -> None:
    path = tmp_path / "prices_history.csv"
    original = "date,ticker,close\n2026-01-01,000001,1\n2026-01-02,000002,2\n"
    path.write_text(original, encoding="utf-8-sig")
    before = path.read_bytes()
    df = pd.DataFrame([{"date": "2026-01-01", "ticker": "000001", "close": 1}])
    try:
        atomic_write_csv(path, df, min_rows=2)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    assert path.read_bytes() == before  # destination untouched

