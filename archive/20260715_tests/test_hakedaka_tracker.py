from pathlib import Path

import yaml

from src.value_list.seed_stocks import GROUP_LABELS, STOCKS


def test_thesis_score_range():
    from src.value_list.scorer import compute_thesis_score

    top = compute_thesis_score(STOCKS[18])  # 모토닉
    low = compute_thesis_score(STOCKS[2])   # 하림지주
    assert top > low
    assert 0 <= top <= 100


def test_run_tracker(tmp_path):
    from src.value_list.pipeline import run_hakedaka_tracker

    data = Path(__file__).resolve().parents[1] / "data"
    out = tmp_path / "outputs"
    rows = run_hakedaka_tracker(data, out)
    assert len(rows) == 50
    assert (out / "hakedaka_scores.csv").exists()
    assert (out / "hakedaka_report.md").exists()
    assert rows[0].rank == 1
