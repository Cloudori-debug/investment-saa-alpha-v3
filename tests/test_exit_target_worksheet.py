"""kr_alpha exit target worksheet — read-only observe, blank target columns."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from src.alpha.exit_target_worksheet import (
    SUGGEST_DEFERRED,
    WORKSHEET_COLUMNS,
    build_exit_target_worksheet,
    suggest_exit_targets,
    write_exit_target_worksheet,
)

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = Path(__file__).resolve().parents[1] / "outputs"


def test_suggest_reproduces_spec_table() -> None:
    """EXIT_TARGET_SUGGESTION_RULE_SPEC §1 verification (role+ROE 2-factor)."""
    # KT — VAL only, ×1.2
    kt = suggest_exit_targets("quality_dividend", 9.72, 0.72)
    assert kt["fund_included"] is False
    assert kt["suggested_roe_min"] == ""
    assert kt["suggested_pbr_max"] == 0.86

    # 코웨이 — VAL only (ROE≥13)
    cw = suggest_exit_targets("quality_defensive", 16.9, 1.87)
    assert cw["fund_included"] is False
    assert cw["suggested_roe_min"] == ""
    assert cw["suggested_pbr_max"] == 2.24

    # DB손보 — VAL only
    db = suggest_exit_targets("shareholder_return", 16.5, 0.92)
    assert db["fund_included"] is False
    assert db["suggested_pbr_max"] == 1.20

    # 동원 — FUND+VAL
    dw = suggest_exit_targets("dividend_value", 11.0, 0.41)
    assert dw["fund_included"] is True
    assert dw["suggested_roe_min"] == 13.5
    assert dw["suggested_pbr_max"] == 0.53

    # 오리온 — FUND include (ROE<13)
    orion = suggest_exit_targets("quality_defensive", 10.05, 1.31)
    assert orion["fund_included"] is True
    assert orion["suggested_roe_min"] == 12.6  # round(10.05+2.5, 1)
    assert orion["suggested_pbr_max"] == 1.57

    # SNT — FUND include
    snt = suggest_exit_targets("shareholder_return", 9.65, 0.54)
    assert snt["fund_included"] is True
    assert snt["suggested_roe_min"] == 12.2  # round(9.65+2.5, 1)
    assert snt["suggested_pbr_max"] == 0.70

    # 현대GF — value_rerating always FUND
    hg = suggest_exit_targets("value_rerating", 10.3, 0.54)
    assert hg["fund_included"] is True
    assert hg["suggested_roe_min"] == 12.8
    assert hg["suggested_pbr_max"] == 0.86

    # SK하이닉스 — out of multiplier table → deferred
    sk = suggest_exit_targets("defensive_consumer", 36.12, 12.35)
    assert sk["suggested_roe_min"] == SUGGEST_DEFERRED
    assert sk["suggested_pbr_max"] == SUGGEST_DEFERRED
    assert sk["fund_included"] is False


def test_suggest_unknown_role_no_fallback() -> None:
    out = suggest_exit_targets("mystery_role", 10.0, 1.0)
    assert out["suggested_roe_min"] == SUGGEST_DEFERRED
    assert out["suggested_pbr_max"] == SUGGEST_DEFERRED


def test_worksheet_includes_suggestions_and_blank_targets(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    shutil.copy(DATA / "target_portfolio.csv", data / "target_portfolio.csv")
    shutil.copy(DATA / "fundamentals.csv", data / "fundamentals.csv")
    shutil.copy(DATA / "kr_alpha_exit_targets.yaml", data / "kr_alpha_exit_targets.yaml")
    if (DATA / "positions.csv").exists():
        shutil.copy(DATA / "positions.csv", data / "positions.csv")
    if (DATA / "hakedaka_fundamentals.csv").exists():
        shutil.copy(DATA / "hakedaka_fundamentals.csv", data / "hakedaka_fundamentals.csv")
    if (OUT / "alpha_scored_universe.csv").exists():
        shutil.copy(OUT / "alpha_scored_universe.csv", out / "alpha_scored_universe.csv")
    pd.DataFrame(
        columns=["as_of", "ticker", "corp_code", "event_date", "event_types", "report_title", "rcept_no"]
    ).to_csv(out / "hakedaka_dart_events.csv", index=False)

    yaml_before = (data / "kr_alpha_exit_targets.yaml").read_text(encoding="utf-8")
    path = write_exit_target_worksheet(data, out)
    assert path.exists()
    yaml_after = (data / "kr_alpha_exit_targets.yaml").read_text(encoding="utf-8")
    assert yaml_before == yaml_after

    df = pd.read_csv(path, dtype=str).fillna("")
    assert list(df.columns) == WORKSHEET_COLUMNS
    assert "suggested_roe_min" in df.columns and "suggested_pbr_max" in df.columns
    assert WORKSHEET_COLUMNS[:3] == ["ticker", "name", "목표상태"]
    assert len(df) >= 7
    for t in ["030200", "021240", "005830", "000660", "006040", "271560", "005440"]:
        assert t in set(df["ticker"].astype(str).str.zfill(6))

    for col in ("target_roe_min", "target_pbr_max", "target_payout_min", "target_buyback_done"):
        assert (df[col].astype(str).str.strip() == "").all()

    sk = df[df["ticker"].astype(str).str.zfill(6) == "000660"].iloc[0]
    assert sk["suggested_pbr_max"] == SUGGEST_DEFERRED
    assert sk["suggested_roe_min"] == SUGGEST_DEFERRED

    md = (out / "kr_alpha_exit_target_worksheet.md").read_text(encoding="utf-8")
    assert "재현 정책" in md or "suggested" in md.lower()
    assert "자동 복사" in md or "자동" in md


def test_build_does_not_invent_targets() -> None:
    df = build_exit_target_worksheet(DATA, OUT)
    if df.empty:
        return
    for col in ("target_roe_min", "target_pbr_max", "target_payout_min", "target_buyback_done"):
        assert df[col].fillna("").astype(str).str.strip().eq("").all()
