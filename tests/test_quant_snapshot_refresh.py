"""One-click quant refresh orchestration without network calls."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from alpha_system.ui.services import refresh
from alpha_system.ui.services.refresh import RefreshResult, run_quant_snapshot_refresh


def test_one_click_refresh_runs_operational_then_quant(
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
    monkeypatch.setattr(
        refresh,
        "run_data_refresh",
        lambda *_args, **_kwargs: RefreshResult(
            ok=True,
            message="ok",
            detail={"tickers": 9},
        ),
    )
    called: dict = {}

    def fake_run(command, **kwargs):
        called["command"] = command
        called["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(refresh.subprocess, "run", fake_run)

    result = run_quant_snapshot_refresh(tmp_path, collect_scope="liquid")

    assert result.ok is True
    assert "--collect" in called["command"]
    assert called["command"][-1] == "liquid"
    assert result.detail["provenance"]["run_id"] == "R1"
    assert result.detail["target_portfolio_written"] is False


def test_one_click_refresh_stops_when_operational_collect_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        refresh,
        "run_data_refresh",
        lambda *_args, **_kwargs: RefreshResult(
            ok=False,
            message="network down",
            detail={"error": "network down"},
        ),
    )

    result = run_quant_snapshot_refresh(tmp_path)

    assert result.ok is False
    assert "운용 데이터 갱신 실패" in result.message
