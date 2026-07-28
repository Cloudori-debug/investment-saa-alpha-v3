"""§7.4 journal / report."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alpha_system.entry import TriggerSnapshot, evaluate_entry
from alpha_system.journal import (
    JournalValidationError,
    append_record,
    clear_entries,
    list_discretionary_warnings,
    list_entries,
)
from alpha_system.loader import load_config
from alpha_system.report import (
    ExecutionFill,
    StatusReportInput,
    render_status_report,
    write_status_report,
)
from alpha_system.scoring import score_name


@pytest.fixture(autouse=True)
def _clear():
    clear_entries()
    yield
    clear_entries()


@pytest.fixture
def cfg():
    return load_config()


def test_append_only_and_rationale_field(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    r1 = append_record(
        action_kind="MARK_READY",
        as_of=date(2026, 7, 16),
        subject="T1",
        rationale="system start",
        trigger_snapshot={"system_started": True},
        score_snapshot={},
        journal_path=path,
    )
    r2 = append_record(
        action_kind="EXECUTE",
        as_of=date(2026, 7, 16),
        subject="T1",
        rationale="ops ack",
        journal_path=path,
    )
    assert r1.entry_id != r2.entry_id
    assert "rationale" in r1.to_dict()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    # no update/delete API — file only grows
    assert len(list_entries()) == 2


def test_warn_discretionary_requires_reason() -> None:
    with pytest.raises(JournalValidationError):
        append_record(
            action_kind="WARN_DISCRETIONARY",
            as_of=date(2026, 7, 16),
            subject="005930",
            discretionary_reason="  ",
        )
    append_record(
        action_kind="WARN_DISCRETIONARY",
        as_of=date(2026, 7, 16),
        subject="005930",
        discretionary_reason="liquidity event",
        rationale="cut overnight",
    )
    assert len(list_discretionary_warnings()) == 1


def test_status_report_includes_tranches_scores_discretionary(cfg, tmp_path: Path) -> None:
    append_record(
        action_kind="WARN_DISCRETIONARY",
        as_of=date(2026, 7, 16),
        subject="X",
        discretionary_reason="test deviation",
        rationale="unit",
    )
    entry = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True, go_live_date=date(2026, 7, 16)),
        journal=False,
    )
    scores = [
        score_name(
            ticker="0001",
            score_q=70,
            score_v=60,
            score_sr=50,
            score_r=40,
            cecs=55,
            system_cfg=cfg,
        )
    ]
    text = render_status_report(
        cfg,
        StatusReportInput(
            as_of=date(2026, 7, 16),
            entry=entry,
            scores=scores,
            fills=[
                ExecutionFill(
                    ticker="0001",
                    as_of=date(2026, 7, 16),
                    side="buy",
                    price=100.0,
                    weight=0.05,
                )
            ],
        ),
    )
    assert "트랜치 상태" in text
    assert "T1" in text
    assert "eligibility" in text
    assert "재량 이탈" in text
    assert "test deviation" in text
    assert "benchmark" in text
    assert "[TODO]" in text or "TODO" in text
    out = write_status_report(
        cfg,
        StatusReportInput(as_of=date(2026, 7, 16), entry=entry),
        tmp_path / "status.md",
    )
    assert out.exists()


def test_five_factor_doc_states_qv_layers() -> None:
    text = Path("docs/ALPHA_SYSTEM_FIVE_FACTOR_REWEIGHT.md").read_text(encoding="utf-8")
    assert "score_q" in text and "score_v" in text
    assert "누락 아님" in text or "누락" in text
    assert "0.70" in text and "factor_score_total" in text
