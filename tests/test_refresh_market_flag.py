"""--refresh-market forces Tier-1 refresh even in standard (cache-first) mode."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.main import main
from src.runtime.run_mode import RunMode, resolve_run_config


def test_standard_mode_is_cache_first_by_default() -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    assert cfg.refresh_network is False


def test_main_refresh_market_overrides_standard(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_dir.mkdir()

    fake_pipe = MagicMock()
    fake_pipe.run_mode = "standard"
    fake_pipe.actual_buy_allowed = False
    fake_pipe.advisory_note = ""
    fake_pipe.data_gate = "GREEN"

    fake_health = MagicMock()
    fake_health.overall = "pass"
    fake_health.summary = {"pass": 1, "warn": 0, "fail": 0}

    with (
        patch("src.main.bootstrap_target_if_needed"),
        patch("src.main.execute_pipeline_with_run_mode", return_value=fake_pipe) as exec_pipe,
        patch("src.validation.system_health.run_system_health", return_value=fake_health),
        patch("src.validation.system_health.write_health_report"),
    ):
        code = main(
            [
                "--data-dir",
                str(data_dir),
                "--output-dir",
                str(output_dir),
                "--run-mode",
                "standard",
                "--refresh-market",
                "--no-backtest",
            ]
        )

    assert code == 0
    assert exec_pipe.call_args.kwargs["refresh_market"] is True


def test_run_compass_analysis_command_includes_refresh_market() -> None:
    from alpha_system.ui.services import refresh as refresh_mod

    source = Path(refresh_mod.__file__).read_text(encoding="utf-8")
    assert '"--refresh-market"' in source or "'--refresh-market'" in source


def test_regime_snapshot_reads_market_and_health(tmp_path: Path) -> None:
    from alpha_system.ui.services.refresh import _regime_snapshot

    data = tmp_path / "data"
    outputs = tmp_path / "outputs"
    data.mkdir()
    outputs.mkdir()
    (data / "market_indicators.csv").write_text(
        "date,regime,regime_expires_date\n2026-07-24,CRISIS,2026-07-31\n",
        encoding="utf-8",
    )
    (outputs / "regime_auto_suggestion.json").write_text(
        '{"auto_synced": true, "computed_regime": "CRISIS", "applied_regime": "CRISIS"}\n',
        encoding="utf-8",
    )
    (outputs / "system_health.json").write_text(
        '{"overall":"fail","checks":[{"name":"core_price_gate","status":"fail","message":"stale"}]}',
        encoding="utf-8",
    )
    snap = _regime_snapshot(tmp_path)
    assert snap["market_as_of"] == "2026-07-24"
    assert snap["regime_synced"] is True
    assert snap["core_price_gate"] == "fail"
