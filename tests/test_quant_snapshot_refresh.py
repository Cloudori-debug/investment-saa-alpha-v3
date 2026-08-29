"""One-click quant refresh orchestration without network calls."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from alpha_system.ui.services import refresh
from alpha_system.ui.services.refresh import (
    RefreshResult,
    _sync_operational_prices_from_alpha_snapshot,
    run_quant_snapshot_refresh,
)


def test_liquid_quant_skips_operational_krx(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "scripts" / "run_alpha_quant_snapshot.py").write_text(
        "# test",
        encoding="utf-8",
    )
    (tmp_path / "data" / "alpha_quant_snapshot_provenance.json").write_text(
        json.dumps({"run_id": "R1", "scored_rows": 30}),
        encoding="utf-8",
    )
    ops = {"n": 0}

    def _ops(*_a, **_k):
        ops["n"] += 1
        return RefreshResult(ok=True, message="ok", detail={})

    monkeypatch.setattr(refresh, "run_data_refresh", _ops)
    called: dict = {}

    def fake_run(command, **kwargs):
        called["command"] = command
        called["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(refresh.subprocess, "run", fake_run)

    result = run_quant_snapshot_refresh(tmp_path, collect_scope="liquid")

    assert result.ok is True
    assert ops["n"] == 0
    assert result.detail["krx_pass"] == "single"
    assert "--collect" in called["command"]
    assert called["command"][-1] == "liquid"
    assert result.detail["provenance"]["run_id"] == "R1"
    assert result.detail["target_portfolio_written"] is False


def test_one_click_refresh_stops_when_snapshot_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_alpha_quant_snapshot.py").write_text("#", encoding="utf-8")
    monkeypatch.setattr(
        refresh.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    result = run_quant_snapshot_refresh(tmp_path)
    assert result.ok is False
    assert "정량 스냅샷 생성 실패" in result.message


def test_sync_operational_prices_from_snapshot(tmp_path: Path) -> None:
    raw = tmp_path / "alpha_portfolio" / "data" / "raw"
    data = tmp_path / "data"
    raw.mkdir(parents=True)
    data.mkdir()
    pd.DataFrame(
        {
            "ticker": ["005930"],
            "as_of": ["2026-08-28"],
            "close": ["72000"],
            "market_cap": ["400000000000000"],
            "avg_trading_value_20d": ["1200000000000"],
        }
    ).to_csv(raw / "price_snapshot.csv", index=False)
    pd.DataFrame(
        {
            "date": ["2026-08-01"],
            "ticker": ["005930"],
            "close": ["70000"],
            "market_cap": ["1"],
            "trading_value_20d": ["1"],
        }
    ).to_csv(data / "prices.csv", index=False)
    n = _sync_operational_prices_from_alpha_snapshot(tmp_path)
    assert n == 1
    out = pd.read_csv(data / "prices.csv", dtype=str)
    assert out.iloc[0]["date"] == "2026-08-28"
    assert out.iloc[0]["close"] == "72000"
