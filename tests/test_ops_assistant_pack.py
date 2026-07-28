"""Ops assistant portable pack — backup/restore round-trip."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.ops_assistant_pack import (
    PRODUCT_NAME,
    create_ops_backup_zip,
    mark_setup_done,
    needs_first_run_banner,
    restore_ops_backup_zip,
    setup_status,
)


def test_create_and_restore_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "app"
    data = root / "data"
    data.mkdir(parents=True)
    (data / "target_portfolio.csv").write_text("ticker,weight\n005930,0.1\n", encoding="utf-8")
    (data / "kr_alpha_exit_targets.yaml").write_text(
        "tickers:\n  '005930':\n    valuation:\n      pbr_max: 1.2\n",
        encoding="utf-8",
    )
    (data / "positions.csv").write_text("ticker,shares\n005930,10\n", encoding="utf-8")

    result = create_ops_backup_zip(
        root,
        dest_dir=tmp_path / "out",
        include_optional_data=False,
        include_secrets=False,
    )
    assert result.path.is_file()
    assert "data/target_portfolio.csv" in result.included

    other = tmp_path / "other"
    other.mkdir()
    (other / "data").mkdir()
    restored = restore_ops_backup_zip(other, result.path)
    assert "data/target_portfolio.csv" in restored["restored"]
    assert (other / "data" / "target_portfolio.csv").read_text(encoding="utf-8").startswith(
        "ticker"
    )
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
