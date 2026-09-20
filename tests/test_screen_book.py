"""Independent KOSPI / KOSDAQ screen books."""

from __future__ import annotations

from pathlib import Path

from alpha_system.loader import load_config
from alpha_system.screen_book import (
    KOSDAQ_TARGET_NAMES,
    apply_book_config,
    ensure_book_dirs,
    is_kosdaq,
    normalize_market,
    operational_data_dir,
    provenance_rel,
    quality_fundamentals_csv,
    resolve_quality_fundamentals_csv,
    save_kosdaq_policy,
    target_names_band,
    watch_max,
)


def test_normalize_market() -> None:
    assert normalize_market("코스닥") == "KOSDAQ"
    assert normalize_market("kospi") == "KOSPI"
    assert not is_kosdaq("KOSPI")


def test_kosdaq_paths_do_not_share_kospi_ledger(tmp_path: Path) -> None:
    assert operational_data_dir(tmp_path, "KOSPI") == tmp_path / "data"
    assert operational_data_dir(tmp_path, "KOSDAQ") == tmp_path / "data" / "books" / "kosdaq"
    assert provenance_rel("KOSDAQ") != provenance_rel("KOSPI")
    assert quality_fundamentals_csv(tmp_path, "KOSPI") == (
        tmp_path / "alpha_portfolio" / "data" / "raw" / "fundamentals.csv"
    )
    assert resolve_quality_fundamentals_csv(tmp_path / "data") == quality_fundamentals_csv(
        tmp_path, "KOSPI"
    )
    assert resolve_quality_fundamentals_csv(
        tmp_path / "data" / "books" / "kosdaq"
    ) == quality_fundamentals_csv(tmp_path, "KOSDAQ")


def test_ensure_kosdaq_book_creates_empty_ledger(tmp_path: Path) -> None:
    data = ensure_book_dirs(tmp_path, "KOSDAQ")
    assert (data / "positions.csv").is_file()
    text = (data / "positions.csv").read_text(encoding="utf-8")
    assert "ticker" in text
    assert "005930" not in text


def test_kosdaq_config_overlay_is_three_names(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "alpha_system" / "config" / "alpha_system.yaml"
    cfg = load_config(src)
    save_kosdaq_policy(tmp_path, cutoff=55.0, target_names=3)
    out = apply_book_config(cfg, "KOSDAQ", root=tmp_path)
    assert out.universe.include_markets == ["KOSDAQ"]
    assert out.sizing.target_names == KOSDAQ_TARGET_NAMES
    assert out.sizing.max_names_per_sector == 1
    assert out.sizing.cyclical_theme_max == 1
    assert out.scoring.score_cutoff == 55.0
    kospi = apply_book_config(cfg, "KOSPI", root=tmp_path)
    assert kospi.universe.include_markets == ["KOSPI"]
    assert kospi.sizing.target_names == cfg.sizing.target_names


def test_kosdaq_cutoff_not_inherited_from_kospi(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "alpha_system" / "config" / "alpha_system.yaml"
    cfg = load_config(src)
    assert cfg.scoring.score_cutoff is not None
    out = apply_book_config(cfg, "KOSDAQ", root=tmp_path)
    assert out.scoring.score_cutoff is None
    assert out.sizing.target_names == KOSDAQ_TARGET_NAMES


def test_watch_and_name_bands() -> None:
    assert watch_max("KOSDAQ") == 10
    assert target_names_band("KOSDAQ") == (3, 3, 3)
    assert target_names_band("KOSPI")[0] == 5


def test_watch_metrics_read_book_data_dir_not_kospi(tmp_path: Path) -> None:
    import pandas as pd

    from alpha_system.ui.services.rank_watchboard import load_watch_metrics

    kospi = tmp_path / "data"
    kosdaq = tmp_path / "data" / "books" / "kosdaq"
    kospi.mkdir(parents=True)
    kosdaq.mkdir(parents=True)
    pd.DataFrame(
        [{"ticker": "005930", "date": "2026-09-01", "close": 70000}]
    ).to_csv(kospi / "prices.csv", index=False)
    pd.DataFrame(
        [{"ticker": "247540", "date": "2026-09-01", "close": 120000}]
    ).to_csv(kosdaq / "prices.csv", index=False)
    mixed = load_watch_metrics(tmp_path)
    book = load_watch_metrics(tmp_path, data_dir=kosdaq)
    assert mixed["005930"]["price"] == 70000
    assert "247540" not in mixed
    assert book["247540"]["price"] == 120000
    assert "005930" not in book
