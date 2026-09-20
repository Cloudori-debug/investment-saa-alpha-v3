"""Ops assistant portable pack — backup/restore round-trip."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.ops_assistant_pack import (
    CORE_RELATIVE_PATHS,
    PRODUCT_NAME,
    create_ops_backup_zip,
    mark_setup_done,
    needs_first_run_banner,
    restore_ops_backup_zip,
    setup_status,
)


def test_core_pack_includes_move_critical_files() -> None:
    assert "data/positions.csv" in CORE_RELATIVE_PATHS
    assert "data/kr_alpha_exit_targets.yaml" in CORE_RELATIVE_PATHS
    assert "data/public_brake_ledger.json" in CORE_RELATIVE_PATHS
    assert "alpha_system/config/dashboard.yaml" in CORE_RELATIVE_PATHS
    assert "alpha_system/config/alpha_system.yaml" in CORE_RELATIVE_PATHS


def test_create_and_restore_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "app"
    data = root / "data"
    data.mkdir(parents=True)
    cfg = root / "alpha_system" / "config"
    cfg.mkdir(parents=True)
    (data / "target_portfolio.csv").write_text("ticker,weight\n005930,0.1\n", encoding="utf-8")
    (data / "kr_alpha_exit_targets.yaml").write_text(
        "tickers:\n  '005930':\n    valuation:\n      pbr_max: 1.2\n",
        encoding="utf-8",
    )
    (data / "positions.csv").write_text("ticker,shares\n005930,10\n", encoding="utf-8")
    (data / "public_brake_ledger.json").write_text("[]\n", encoding="utf-8")
    (cfg / "dashboard.yaml").write_text("ui: portable\n", encoding="utf-8")

    result = create_ops_backup_zip(
        root,
        dest_dir=tmp_path / "out",
        include_optional_data=False,
        include_secrets=False,
    )
    assert result.path.is_file()
    assert "data/target_portfolio.csv" in result.included
    assert "data/public_brake_ledger.json" in result.included
    assert "alpha_system/config/dashboard.yaml" in result.included

    other = tmp_path / "other"
    other.mkdir()
    (other / "data").mkdir()
    restored = restore_ops_backup_zip(other, result.path)
    assert "data/target_portfolio.csv" in restored["restored"]
    assert "alpha_system/config/dashboard.yaml" in restored["restored"]
    assert (other / "data" / "target_portfolio.csv").read_text(encoding="utf-8").startswith(
        "ticker"
    )
    assert (other / "alpha_system" / "config" / "dashboard.yaml").read_text(
        encoding="utf-8"
    ).startswith("ui:")
    assert (other / "data" / "local" / "ops_assistant_setup.json").is_file()


def test_setup_banner_logic(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    assert needs_first_run_banner(root) is True
    mark_setup_done(root, source="test")
    assert needs_first_run_banner(root) is False
    status = setup_status(root)
    assert status["product"] == PRODUCT_NAME
    assert status["setup_done"] is True


def test_launcher_vbs_uses_ipv4_loopback_with_http_timeout() -> None:
    root = Path(__file__).resolve().parents[1]
    vbs = (root / "Start-Ops-Assistant.vbs").read_text(encoding="utf-8")
    bat = (root / "투자나침반.bat").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8501" in vbs
    assert "PortListening" in vbs
    assert "netstat" in vbs
    assert "localhost:8501" not in vbs
    assert "start \"\" wscript" in bat
