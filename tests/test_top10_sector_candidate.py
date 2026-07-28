"""Top10 sector candidate generation tests."""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

from src.alpha.sector_mapping import compute_sector_coverage_for_tickers
from src.alpha.top10_sector_candidate import (
    build_manual_candidate_rows,
    extract_top10_unknown_rows,
    simulate_coverage_with_candidates,
    write_top10_sector_candidate_artifacts,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def test_candidate_does_not_modify_manual_mapping(tmp_path: Path) -> None:
    shutil.copy(DATA / "krx_sector_mapping_manual.csv", tmp_path / "krx_sector_mapping_manual.csv")
    manual_path = tmp_path / "krx_sector_mapping_manual.csv"
    before = manual_path.read_bytes()

    top10 = [
        {"ticker": "001450", "name": "현대해상", "total_score": 56.0, "grade": "B", "sector": "unknown"},
        {"ticker": "055550", "name": "신한지주", "total_score": 55.0, "grade": "B", "sector": "unknown"},
    ]
    out = tmp_path / "outputs"
    meta = write_top10_sector_candidate_artifacts(top10, tmp_path, out, as_of="2026-07-02")

    assert manual_path.read_bytes() == before
    assert meta["manual_mapping_hash_unchanged"] is True
    assert (tmp_path / "krx_sector_mapping_manual_candidate.csv").exists()
    assert not (tmp_path / "krx_sector_mapping_manual.csv").read_text(encoding="utf-8-sig").endswith("candidate")


def test_extract_unknown_excludes_manual_mapped(tmp_path: Path) -> None:
    shutil.copy(DATA / "krx_sector_mapping_manual.csv", tmp_path / "krx_sector_mapping_manual.csv")
    top10 = [
        {"ticker": "055550", "name": "신한지주", "total_score": 55.0, "grade": "B", "sector": "unknown"},
        {"ticker": "001450", "name": "현대해상", "total_score": 54.0, "grade": "B", "sector": "unknown"},
    ]
    unknown = extract_top10_unknown_rows(top10, tmp_path)
    tickers = {r["ticker"] for r in unknown}
    assert "055550" not in tickers
    assert "001450" in tickers


def test_simulated_coverage_improves_with_candidates(tmp_path: Path) -> None:
    shutil.copy(DATA / "krx_sector_mapping_manual.csv", tmp_path / "krx_sector_mapping_manual.csv")
    top10 = [
        {"ticker": "055550", "name": "신한지주", "total_score": 55.0, "grade": "B", "sector": ""},
        {"ticker": "001450", "name": "현대해상", "total_score": 54.0, "grade": "B", "sector": ""},
        {"ticker": "214320", "name": "이노션", "total_score": 53.0, "grade": "B", "sector": ""},
        {"ticker": "015760", "name": "한국전력", "total_score": 52.0, "grade": "B", "sector": ""},
        {"ticker": "023590", "name": "다우기술", "total_score": 51.0, "grade": "B", "sector": ""},
    ]
    before = compute_sector_coverage_for_tickers(top10, tmp_path)
    unknown = extract_top10_unknown_rows(top10, tmp_path)
    candidates = build_manual_candidate_rows(unknown, as_of="2026-07-02", data_dir=tmp_path)
    after = simulate_coverage_with_candidates(top10, tmp_path, candidates)
    assert after.get("coverage_pct", 0) >= before.get("coverage_pct", 0)


def test_candidate_source_is_manual_candidate(tmp_path: Path) -> None:
    rows = build_manual_candidate_rows(
        [{"ticker": "999999", "name": "테스트미지정", "total_score": 50, "grade": "C"}],
        as_of="2026-07-02",
        data_dir=tmp_path,
    )
    assert rows[0]["source"] == "manual_candidate"
    assert rows[0]["internal_sector"] == "review_needed"


def test_top10_unknown_fix_tickers_resolve_from_manual() -> None:
    from src.alpha.sector_mapping import load_krx_sector_mapping, resolve_sector

    mapping = load_krx_sector_mapping(DATA)
    for ticker, name in [
        ("015760", "한국전력"),
        ("023590", "다우기술"),
        ("088350", "한화생명"),
        ("025540", "한국단자"),
    ]:
        res = resolve_sector(ticker, name, "", mapping)
        assert res["resolved"] is True, ticker
        assert res["sector"] != "unknown", ticker

    top10 = [
        {"ticker": "001450", "name": "현대해상"},
        {"ticker": "214320", "name": "이노션"},
        {"ticker": "192080", "name": "더블유게임즈"},
        {"ticker": "024110", "name": "기업은행"},
        {"ticker": "005380", "name": "현대차"},
        {"ticker": "015760", "name": "한국전력"},
        {"ticker": "033780", "name": "KT&G"},
        {"ticker": "023590", "name": "다우기술"},
        {"ticker": "088350", "name": "한화생명"},
        {"ticker": "025540", "name": "한국단자"},
    ]
    cov = compute_sector_coverage_for_tickers(top10, DATA)
    assert cov["unknown_count"] == 0
    assert cov["coverage_pct"] >= 80.0

