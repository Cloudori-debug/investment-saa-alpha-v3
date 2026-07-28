"""CECS workbench guards, persistence, and checklist refresh."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_system.journal import clear_entries
from alpha_system.loader import load_config
from alpha_system.ui.services.cecs_workbench import (
    CecsProgress,
    build_relative_cutoff_ladder,
    confirm_score_cutoff,
    cutoff_actions_enabled,
    default_relative_cutoff_rank,
    generate_correlation_report,
)
from alpha_system.ui.services.go_live_gate import assess_checklist
from alpha_system.ui.services.t3_history_refresh import try_generate_t3_history

_ASOF = date(2026, 7, 17)


def _template(path: Path, *, final_n: int = 29) -> Path:
    rows = []
    for i in range(30):
        final = i < final_n
        rows.append(
            {
                "ticker": f"{i + 1:06d}",
                "name": f"N{i + 1}",
                "as_of": _ASOF.isoformat(),
                "sector": f"S{i % 6}",
                "is_held": "True" if i < 8 else "False",
                "rank": i + 1,
                "execution_continuity": "0.50" if final else "",
                "execution_rationale": "execution evidence" if final else "",
                "pension_flow_score": "0.50" if final else "",
                "pension_rationale": "pension evidence" if final else "",
                "investment_purpose_flag": "0.50" if final else "",
                "investment_purpose_rationale": "purpose evidence" if final else "",
                "policy_dependency_flag": "0.50",
                "policy_dependency_rationale": "",
                "cecs_computed": "42.50" if final else "",
                "scored_by": "tester" if final else "",
                "scored_at": _ASOF.isoformat() if final else "",
                "status": "final" if final else "draft",
                "notes": "",
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_cutoff_action_is_disabled_before_30() -> None:
    assert (
        cutoff_actions_enabled(
            CecsProgress(final=29, total=30, draft_tickers=("000030",)),
            factor_exists=True,
        )
        is False
    )
    assert (
        cutoff_actions_enabled(
            CecsProgress(final=30, total=30, draft_tickers=()),
            factor_exists=True,
        )
        is True
    )


def test_cecs_final_checklist_is_non_blocking_ops_a(tmp_path: Path) -> None:
    """Ops A: incomplete CECS does not fail go-live checklist."""
    clear_entries()
    root = tmp_path
    data = root / "data"
    data.mkdir()
    _template(data / "cecs_manual_scoring_template.csv", final_n=29)
    (data / "kospi_market_pbr_history.csv").write_text(
        "month_end,market_pbr\n2026-06-30,0.9\n",
        encoding="utf-8",
    )
    cfg = load_config().model_copy(
        update={
            "scoring": load_config().scoring.model_copy(
                update={"score_cutoff": 50.0}
            )
        }
    )
    status = assess_checklist(cfg, root=root, go_live_date=None)
    assert next(i for i in status.items if i.key == "cecs_final").ok is True
    assert all(i.key != "cecs_final" or i.ok for i in status.blocking) or not any(
        i.key == "cecs_final" for i in status.blocking
    )
    clear_entries()


def test_relative_cutoff_ladder_derives_absolute_from_rank_count() -> None:
    scored = [
        {"ticker": "000001", "name": "A", "total_score": 90},
        {"ticker": "000002", "name": "B", "total_score": 80},
        {"ticker": "000003", "name": "C", "total_score": 79},
        {"ticker": "000004", "name": "D", "total_score": 50},
        {"ticker": "000005", "name": "E", "total_score": 40},
        {"ticker": "000006", "name": "F", "total_score": 30},
        {"ticker": "000007", "name": "G", "total_score": 20},
    ]
    ladder = build_relative_cutoff_ladder(scored, min_rank=3)
    by_rank = {option.rank_n: option for option in ladder}

    assert by_rank[3].cutoff == 79
    assert by_rank[3].eligible_count == 3
    assert by_rank[3].margin_below == 29
    assert by_rank[3].is_natural_break is True
    assert default_relative_cutoff_rank(ladder) == 3


def test_cutoff_requires_two_confirmations_without_cecs_gate(
    tmp_path: Path,
) -> None:
    """Ops A: cutoff confirm no longer waits for CECS 30/30."""
    root = Path(__file__).resolve().parents[1]
    config = tmp_path / "alpha_system.yaml"
    shutil.copy2(root / "alpha_system" / "config" / "alpha_system.yaml", config)
    cecs = _template(tmp_path / "cecs.csv", final_n=0)
    original = config.read_bytes()

    with pytest.raises(ValueError, match="2단계"):
        confirm_score_cutoff(
            config_path=config,
            cecs_path=cecs,
            cutoff=55.0,
            confirm_understood=True,
            confirm_final=False,
            as_of=_ASOF,
        )
    assert config.read_bytes() == original

    backup = confirm_score_cutoff(
        config_path=config,
        cecs_path=cecs,
        cutoff=55.0,
        confirm_understood=True,
        confirm_final=True,
        as_of=_ASOF,
        journal_path=tmp_path / "journal.jsonl",
        eligible_count=8,
        rank_n=8,
        method="absolute_cutoff_then_count",
        target_names=7,
    )
    saved = load_config(config)
    assert saved.scoring.score_cutoff == 55.0
    assert saved.sizing.target_names == 7
    assert backup.exists()


def test_correlation_report_requires_and_uses_final_30(tmp_path: Path) -> None:
    cecs = _template(tmp_path / "cecs.csv", final_n=30)
    factors = pd.DataFrame(
        [
            {
                "ticker": f"{i + 1:06d}",
                "sector": f"S{i % 6}",
                "score_q": i * 2 + 10,
                "score_v": 90 - i,
                "score_sr": (i * 7) % 100,
                "score_r": (i * 11) % 100,
            }
            for i in range(30)
        ]
    )
    factor_path = tmp_path / "alpha_scores.csv"
    factors.to_csv(factor_path, index=False)
    output = tmp_path / "correlation.md"

    report, written = generate_correlation_report(
        cecs_path=cecs,
        factor_path=factor_path,
        output_path=output,
        as_of=_ASOF,
    )
    assert report.status == "OK"
    assert report.n_names == 30
    assert written == output
    assert output.exists()


def test_t3_auto_history_attempt_writes_only_real_fetch_result(tmp_path: Path) -> None:
    dates = pd.date_range("2024-01-31", periods=30, freq="ME")
    raw = pd.DataFrame({"PBR": [0.8 + i * 0.01 for i in range(30)]}, index=dates)

    result = try_generate_t3_history(
        tmp_path,
        today=_ASOF,
        fetcher=lambda _start, _end, _ticker: raw,
    )
    assert result.ok is True
    assert result.rows == 30
    saved = pd.read_csv(tmp_path / "data" / "kospi_market_pbr_history.csv")
    assert list(saved.columns) == ["month_end", "market_pbr"]
