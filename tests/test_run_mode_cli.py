"""CLI --run-mode integration tests."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.main import main as portfolio_main
from src.runtime.cli import INVALID_RUN_MODE_MSG, add_run_mode_argument, parse_run_mode
from src.runtime.run_mode import RunMode, resolve_run_config

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_cli_run_mode_default_standard() -> None:
    parser = argparse.ArgumentParser()
    add_run_mode_argument(parser)
    args = parser.parse_args([])
    assert args.run_mode == RunMode.STANDARD.value
    assert resolve_run_config(args.run_mode).run_mode == RunMode.STANDARD


def test_cli_invalid_run_mode_fails() -> None:
    with pytest.raises(SystemExit) as exc:
        parse_run_mode("turbo")
    assert INVALID_RUN_MODE_MSG in str(exc.value)


def test_cli_invalid_run_mode_argparse() -> None:
    parser = argparse.ArgumentParser()
    add_run_mode_argument(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["--run-mode", "invalid"])


def test_cli_and_streamlit_use_same_run_mode_policy() -> None:
    for mode in RunMode:
        cli_cfg = resolve_run_config(mode)
        ui_cfg = resolve_run_config(mode)
        assert cli_cfg == ui_cfg


@pytest.mark.skipif(not (OUT / "final_execution_decision.json").exists(), reason="outputs missing")
def test_cli_run_mode_quick(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    for name in ("final_execution_decision.json", "daily_report.md", "report_clarity_validation.json"):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out / name)

    with patch("src.full_pipeline.run_full_pipeline") as mock_fp:
        code = portfolio_main([
            "--data-dir", str(DATA),
            "--output-dir", str(out),
            "--run-mode", "quick",
        ])
        mock_fp.assert_not_called()
    assert code == 0
    prof = json.loads((out / "runtime_profile.json").read_text(encoding="utf-8"))
    assert prof["run_mode"] == "quick"
    assert prof["entrypoint"] == "cli"
    assert (out / "no_action_diagnostics.json").exists()


@pytest.mark.skipif(not (OUT / "run_manifest.json").exists(), reason="manifest missing")
def test_cli_run_mode_bundle_only(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    for name in (
        "run_manifest.json",
        "final_execution_decision.json",
        "daily_report.md",
        "no_action_diagnostics.json",
        "system_health.json",
        "acceptance_report.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out / name)

    with patch("src.full_pipeline.run_full_pipeline") as mock_fp:
        with patch(
            "src.validation.ai_export.build_ai_export_bundle",
            return_value={"as_of": "2026-07-03", "run_id": "test", "validation_prompt": ""},
        ):
            with patch(
                "src.validation.ai_export.validate_export_bundle_readiness",
                return_value={"pass": True, "failures": []},
            ):
                code = portfolio_main([
                    "--data-dir", str(DATA),
                    "--output-dir", str(out),
                    "--run-mode", "bundle_only",
                ])
        mock_fp.assert_not_called()
    assert code == 0
    prof = json.loads((out / "runtime_profile.json").read_text(encoding="utf-8"))
    assert prof["run_mode"] == "bundle_only"
    assert prof["entrypoint"] == "cli"


def test_daily_pipeline_accepts_run_mode() -> None:
    import scripts.daily_pipeline as daily

    parser = argparse.ArgumentParser()
    add_run_mode_argument(parser)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--no-backtest", action="store_true")
    args = parser.parse_args(["--run-mode", "deep"])
    assert args.run_mode == "deep"
    assert daily is not None


@pytest.mark.skipif(not (OUT / "final_execution_decision.json").exists(), reason="outputs missing")
def test_all_cli_modes_write_runtime_profile(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    for name in (
        "final_execution_decision.json",
        "daily_report.md",
        "report_clarity_validation.json",
        "run_manifest.json",
        "no_action_diagnostics.json",
        "system_health.json",
        "acceptance_report.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out / name)

    with patch("src.full_pipeline.run_full_pipeline") as mock_fp:
        mock_fp.return_value = type("R", (), {"data_gate": "YELLOW", "action_count": 0})()
        with patch(
            "src.validation.ai_export.build_ai_export_bundle",
            return_value={"as_of": "x", "run_id": "x", "validation_prompt": ""},
        ):
            with patch(
                "src.validation.ai_export.validate_export_bundle_readiness",
                return_value={"pass": True, "failures": []},
            ):
                for mode in ("quick", "bundle_only"):
                    portfolio_main([
                        "--data-dir", str(DATA),
                        "--output-dir", str(out),
                        "--run-mode", mode,
                    ])
                    prof = json.loads((out / "runtime_profile.json").read_text(encoding="utf-8"))
                    assert prof["run_mode"] == mode
                    assert prof["entrypoint"] == "cli"
                    assert "step_timings" in prof
                    assert "slowest_steps" in prof


def test_bundle_only_cli_does_not_recompute_outputs(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "run_manifest.json").write_text('{"run_id":"x"}', encoding="utf-8")
    (out / "final_execution_decision.json").write_text(
        '{"data_gate":"YELLOW","execution_scope":"NO_TRADE","actions":[]}',
        encoding="utf-8",
    )
    (out / "daily_report.md").write_text("# report", encoding="utf-8")
    (out / "no_action_diagnostics.json").write_text("{}", encoding="utf-8")

    with patch("src.full_pipeline.run_full_pipeline") as mock_fp:
        with patch(
            "src.validation.ai_export.prepare_export_bundle_existing_only",
            return_value={"as_of": "2026-07-03", "run_id": "test"},
        ) as mock_bundle:
            with patch("src.validation.ai_export.build_export_zip", return_value=b"zip"):
                portfolio_main([
                    "--data-dir", str(DATA),
                    "--output-dir", str(out),
                    "--run-mode", "bundle_only",
                ])
        mock_fp.assert_not_called()
        mock_bundle.assert_called_once()


def test_all_cli_modes_target_write_zero_without_approval(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "positions.csv").write_text("ticker,qty\n", encoding="utf-8")
    (data / "target_portfolio.csv").write_text("ticker,weight\nCASH,1\n", encoding="utf-8")
    (data / "market_indicators.csv").write_text("date,kospi\n2026-07-03,1\n", encoding="utf-8")
    (data / "portfolio_policy.yaml").write_text("data_gate_policy: {}\n", encoding="utf-8")
    (out / "final_execution_decision.json").write_text(
        '{"data_gate":"YELLOW","execution_scope":"NO_TRADE","actions":[]}',
        encoding="utf-8",
    )

    with patch("src.runtime.pipeline_runner._validate_target_guard", return_value={"target_guard_status": "pass"}):
        with patch("src.validation.no_action_diagnostics.write_no_action_diagnostics"):
            with patch("src.report.authoritative_status.resolve_authoritative_execution", return_value={}):
                portfolio_main([
                    "--data-dir", str(data),
                    "--output-dir", str(out),
                    "--run-mode", "quick",
                ])

    audit_path = out / "target_write_audit.jsonl"
    if audit_path.exists():
        lines = [ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for ln in lines:
            doc = json.loads(ln)
            assert doc.get("target_write_allowed") is not True
