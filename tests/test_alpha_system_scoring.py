"""§7.2 scoring (5-factor) + §7.1 T4 + CECS-T2 remap tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from alpha_system.entry import TrancheState, TriggerSnapshot, evaluate_entry
from alpha_system.journal import clear_entries
from alpha_system.loader import load_config
from alpha_system.schema import ConfigTodoError, TrancheId
from alpha_system.scoring import (
    CatalystInputs,
    FIVE_FACTORS,
    analyze_factor_correlation,
    calculate_cecs,
    evaluate_rescore_triggers,
    require_eligibility_decided,
    score_name,
    t2_candidate_signals,
    write_correlation_report,
    write_overlap_report,
)


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture(autouse=True)
def _clear_journal():
    clear_entries()
    yield
    clear_entries()


def test_hard_rule_block_paths_present() -> None:
    text = Path("tests/test_alpha_system_entry.py").read_text(encoding="utf-8")
    assert "test_hard_rule_reverse_blocks_unmet_trigger" in text
    assert "test_hard_rule_sunset_expires_unexecuted" in text
    assert "test_hard_rule_thesis_damage_freezes" in text


def test_t2_candidate_sources_mapped_from_cecs(cfg) -> None:
    sources = cfg.tranches["T2"].event_candidate_sources
    assert "disclosure_status" in sources
    assert "independent_catalyst_flag" in sources


def test_t4_pending_before_month_12(cfg) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
        ),
    )
    t4 = next(s for s in ev.statuses if s.tranche_id == TrancheId.T4)
    assert t4.state == TrancheState.PENDING
    assert "12m" in t4.detail


def test_t4_initial_only_when_t2_t3_unmet(cfg) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2027, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
        ),
    )
    t4 = next(s for s in ev.statuses if s.tranche_id == TrancheId.T4)
    assert t4.state == TrancheState.READY

    ev2 = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2027, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
            events_fired=frozenset({"ifrs18_domestic_adoption_schedule_confirmed"}),
        ),
    )
    t4b = next(s for s in ev2.statuses if s.tranche_id == TrancheId.T4)
    assert t4b.state == TrancheState.PENDING
    assert "already met" in t4b.detail.lower()
    assert t4b.trigger_met is False


def test_cecs_ignores_disclosure_and_independent() -> None:
    base = CatalystInputs(
        "A",
        execution_continuity=1.0,
        pension_flow_score=1.0,
        investment_purpose_flag=1.0,
        disclosure_status=0.0,
        independent_catalyst_flag=0.0,
        policy_dependency_flag=0.0,
    )
    boosted = CatalystInputs(
        "B",
        execution_continuity=1.0,
        pension_flow_score=1.0,
        investment_purpose_flag=1.0,
        disclosure_status=1.0,
        independent_catalyst_flag=1.0,
        policy_dependency_flag=0.0,
    )
    assert calculate_cecs(base) == calculate_cecs(boosted)
    assert t2_candidate_signals(boosted)["disclosure_status"] == 1.0


def test_cecs_port_matches_spec_penalty() -> None:
    high = CatalystInputs("A", execution_continuity=1.0, policy_dependency_flag=0.0)
    low = CatalystInputs("B", execution_continuity=1.0, policy_dependency_flag=1.0)
    assert calculate_cecs(high) > calculate_cecs(low)


def test_eligibility_cutoff_todo_does_not_invent(cfg) -> None:
    cfg = cfg.model_copy(
        update={"scoring": cfg.scoring.model_copy(update={"score_cutoff": None})}
    )
    s = score_name(
        ticker="0001",
        score_q=80,
        score_v=70,
        score_sr=60,
        score_r=50,
        cecs=70,
        system_cfg=cfg,
    )
    assert s.eligibility is None
    assert "TODO" in s.eligibility_reason
    with pytest.raises(ConfigTodoError):
        require_eligibility_decided(s)


def test_cecs_missing_does_not_invent_neutral(cfg) -> None:
    """No cecs value and no sub-scores → eligibility undecided, never a silent 0.5."""
    s = score_name(
        ticker="0001",
        score_q=80,
        score_v=70,
        score_sr=60,
        score_r=50,
        system_cfg=cfg,
    )
    assert s.eligibility is None
    assert "CECS" in s.eligibility_reason
    assert s.factors["cecs"] != s.factors["cecs"]  # NaN, not 50
    with pytest.raises(ConfigTodoError):
        require_eligibility_decided(s)


def test_cecs_frame_uses_real_subs_only(cfg) -> None:
    from alpha_system.scoring import score_frame

    df = pd.DataFrame(
        [
            {  # has real subs → scored
                "ticker": "0001",
                "score_q": 80,
                "execution_continuity": 0.9,
                "pension_flow_score": 0.8,
                "investment_purpose_flag": 0.7,
            },
            {  # no cecs, no subs → undecided, not fabricated
                "ticker": "0002",
                "score_q": 80,
            },
        ]
    )
    scored = {s.ticker: s for s in score_frame(df, cfg)}
    assert scored["0001"].factors["cecs"] == scored["0001"].factors["cecs"]  # not NaN
    assert scored["0002"].eligibility is None
    assert scored["0002"].factors["cecs"] != scored["0002"].factors["cecs"]  # NaN


def test_eligibility_absolute_cutoff_when_set(tmp_path: Path, cfg) -> None:
    raw = cfg.model_dump(mode="json")
    raw["scoring"]["score_cutoff"] = 60.0
    path = tmp_path / "cut.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    loaded = load_config(path)
    ok = score_name(
        ticker="0001", factor_score_total=80, cecs=80, system_cfg=loaded
    )
    bad = score_name(
        ticker="0002", factor_score_total=10, cecs=10, system_cfg=loaded
    )
    assert ok.eligibility is True
    assert bad.eligibility is False
    assert bad.weight_input == 0.0


def test_ops_a_cecs_weight_zero_ignores_cecs_in_total(cfg) -> None:
    """Ops A: identical factors → identical total_score regardless of CECS."""
    high = score_name(
        ticker="0001", factor_score_total=70.0, cecs=100.0, system_cfg=cfg
    )
    low = score_name(
        ticker="0002", factor_score_total=70.0, cecs=0.0, system_cfg=cfg
    )
    assert high.total_score == low.total_score == 70.0


def test_correlation_skipped_without_data() -> None:
    report = analyze_factor_correlation(None, as_of=date(2026, 7, 16))
    assert report.status == "SKIPPED"
    assert report.high_pairs == []


def test_correlation_ok_with_five_factors() -> None:
    rows = []
    for i in range(25):
        rows.append(
            {
                "ticker": f"{i:04d}",
                "sector": "전기·전자" if i < 21 else "보험",
                "score_q": 50 + i,
                "score_v": 50 + i * 0.9,
                "score_sr": 100 - i,
                "score_r": 40,
                "cecs": 55,
            }
        )
    report = analyze_factor_correlation(pd.DataFrame(rows), as_of=date(2026, 7, 16))
    assert report.status == "OK"
    assert list(FIVE_FACTORS) == [
        "score_q",
        "score_v",
        "score_sr",
        "score_r",
        "cecs",
    ]
    assert any(p.factor_a == "score_q" and p.factor_b == "score_v" for p in report.high_pairs)
    fb = [r for r in report.sector_fallback_rows if r.sector_peer_fallback]
    assert len(fb) == 4  # insurance sector has 4 names in snapshot
    assert all(r.sector == "보험" for r in fb)


def test_rescore_hook_when_trigger_fired(cfg) -> None:
    d = evaluate_rescore_triggers(
        cfg, as_of=date(2026, 7, 16), fired_events=["dividend_articles_amendment"]
    )
    assert d.should_rescore is True
    assert "dividend_articles_amendment" in d.matched_triggers


def test_write_reports(tmp_path: Path) -> None:
    overlap = write_overlap_report(tmp_path / "overlap.md")
    text = overlap.read_text(encoding="utf-8")
    assert "적용 상태" in text
    report = analyze_factor_correlation(None, as_of=date(2026, 7, 16))
    corr_path = write_correlation_report(report, tmp_path / "corr.md")
    assert "5팩터" in corr_path.read_text(encoding="utf-8")
