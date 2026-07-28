"""Policy-B screen dry report: objective ranking, no operational writes."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from alpha_system.loader import load_config
from alpha_system.report.screen_dry import build_screen_dry
from scripts.run_kr_alpha_screen_dry import main


def _scores() -> pd.DataFrame:
    rows = []
    for i, score in enumerate((90, 80, 70, 60, 55, 50, 40, 30), start=1):
        rows.append(
            {
                "ticker": f"{i:06d}",
                "name": f"N{i}",
                "gate_pass": True,
                "gate_fail_reason": "",
                "score_q": score,
                "score_v": score,
                "score_sr": score,
                "score_r": score,
                "composite_raw": score,
                # Must be ignored by policy B:
                "incumbent_bonus": 1000 if i == 8 else 0,
                "is_held": i in {1, 8},
            }
        )
    return pd.DataFrame(rows)


def _cecs(*, status: str = "final") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": f"{i:06d}",
                "name": f"N{i}",
                "status": status,
                "cecs_computed": score,
            }
            for i, score in enumerate((90, 80, 70, 60, 55, 50, 40, 30), start=1)
        ]
    )


def _positions(held: set[int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": f"{i:06d}",
                "name": f"N{i}",
                "asset_group": "kr_alpha",
            }
            for i in held
        ]
    )


def test_policy_b_held_flag_does_not_change_selected_six() -> None:
    cfg = load_config()
    common = {
        "cfg": cfg,
        "scores_df": _scores(),
        "cecs_df": _cecs(),
        "as_of": date(2026, 7, 17),
        "assumed_cutoff": 45.0,
    }
    a = build_screen_dry(positions_df=_positions({1, 8}), **common)
    b = build_screen_dry(positions_df=_positions({2, 3, 4}), **common)

    selected_a = set(a.rows.loc[a.rows["selected"], "ticker"])
    selected_b = set(b.rows.loc[b.rows["selected"], "ticker"])
    assert selected_a == selected_b == {f"{i:06d}" for i in range(1, 7)}
    assert "000008" not in selected_a


def test_below_cutoff_holding_is_reported_as_dropped() -> None:
    result = build_screen_dry(
        cfg=load_config(),
        scores_df=_scores(),
        cecs_df=_cecs(),
        positions_df=_positions({8}),
        as_of=date(2026, 7, 17),
        assumed_cutoff=45.0,
    )
    row = result.rows[result.rows["ticker"] == "000008"].iloc[0]
    assert bool(row["is_held"]) is True
    assert bool(row["selected"]) is False
    assert "탈락 보유" in row["reason"]


def test_final_zero_does_not_block_dry_selection() -> None:
    """Ops A: draft CECS does not block screen dry (rank is quant-only)."""
    result = build_screen_dry(
        cfg=load_config(),
        scores_df=_scores(),
        cecs_df=_cecs(status="draft"),
        positions_df=_positions(set()),
        as_of=date(2026, 7, 17),
        assumed_cutoff=45.0,
    )
    assert result.blocked_reason != "CECS final 0건 — 선정 리포트 차단"
    assert result.selected_count >= 1 or result.blocked_reason in {
        "계산 가능한 후보 없음",
        "eligibility 통과 후보 없음",
        None,
    }


def test_cli_writes_reports_but_preserves_target(tmp_path: Path) -> None:
    scores = tmp_path / "scores.csv"
    cecs = tmp_path / "cecs.csv"
    positions = tmp_path / "positions.csv"
    target = tmp_path / "target_portfolio.csv"
    out_csv = tmp_path / "dry.csv"
    out_md = tmp_path / "dry.md"

    _scores().to_csv(scores, index=False)
    _cecs().to_csv(cecs, index=False)
    _positions({1, 8}).to_csv(positions, index=False)
    target.write_bytes(b"ticker,target_weight\nOLD,1.0\n")
    before = target.read_bytes()

    code = main(
        [
            "--scores",
            str(scores),
            "--cecs",
            str(cecs),
            "--positions",
            str(positions),
            "--target",
            str(target),
            "--output-csv",
            str(out_csv),
            "--output-md",
            str(out_md),
            "--as-of",
            "2026-07-17",
            "--assumed-cutoff",
            "45",
        ]
    )

    assert code == 0
    assert target.read_bytes() == before
    assert out_csv.exists()
    text = out_md.read_text(encoding="utf-8")
    assert "selection_policy: **B**" in text
    assert "is_held 가산·강제 포함 없음" in text
    assert "operational target write: **없음**" in text
