"""Proposal-screen target confirm — exit YAML only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from alpha_system.journal import clear_entries, list_entries
from alpha_system.ui.services.weekly_domain_gates import approve_proposal_target


def test_approve_proposal_target_writes_yaml_not_target_csv(tmp_path: Path) -> None:
    clear_entries()
    root = tmp_path
    data = root / "data"
    data.mkdir()
    target_csv = data / "target_portfolio.csv"
    target_csv.write_text(
        "ticker,asset_group,target_weight\n005930,kr_alpha,10\n",
        encoding="utf-8",
    )
    before = target_csv.read_text(encoding="utf-8")
    out = approve_proposal_target(
        root=root,
        ticker="005930",
        pbr_max=1.25,
        target_price=72000,
        fundamental_reason="정당P/B 초안",
        rationale="r=9% g=4%",
        sources=("https://example.com/pb",),
        as_of=date(2026, 8, 31),
        proposal_tickers=["005930", "000660"],
        journal_path=root / "journal.jsonl",
    )
    assert out["target_portfolio_written"] is False
    assert target_csv.read_text(encoding="utf-8") == before
    yaml_path = data / "kr_alpha_exit_targets.yaml"
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    entry = raw["tickers"]["005930"]
    assert entry["target_price"] == 72000
    assert entry["valuation"]["pbr_max"] == 1.25
    assert entry["source"] == "proposal_screen_approved"
    kinds = {e.action_kind for e in list_entries()}
    assert "TARGET_VALUATION_MODIFY" in kinds
    clear_entries()


def test_approve_proposal_target_rejects_outside_book(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    try:
        approve_proposal_target(
            root=root,
            ticker="005930",
            pbr_max=1.0,
            target_price=None,
            fundamental_reason="x",
            rationale="x",
            as_of=date(2026, 8, 31),
            proposal_tickers=["000660"],
        )
    except ValueError as exc:
        assert "제안 북" in str(exc)
    else:
        raise AssertionError("expected reject")


def test_proposal_page_owns_targets_weekly_does_not() -> None:
    import inspect

    from alpha_system.ui.pages import events, portfolio
    from alpha_system.ui.services.proposal_freeze import REQUIRED_GATE_DOMAINS

    from alpha_system.ui.services.weekly_qual_report import WEEKLY_DOMAIN_KEYS

    assert WEEKLY_DOMAIN_KEYS == ("t2", "thesis")
    assert REQUIRED_GATE_DOMAINS == ("t2", "thesis")
    assert "_render_proposal_target_board" in inspect.getsource(portfolio)
    src = inspect.getsource(portfolio)
    assert "auto_apply_proposal_quant_targets" in src
    assert "숫자 수정 확정" not in src
    assert "#### 목표가 확정" not in src
    src = inspect.getsource(portfolio)
    assert "_render_proposal_opendart_gates" in src
    assert "refresh_opendart_proposal_watch" in src
    assert "apply_opendart_flag_gates" in src
    assert "제외 확정" not in src
    assert "편입 게이트 초안" not in src
    assert "OpenDART 초안 불러오기" not in src
    weekly = inspect.getsource(events._render_weekly_qual)
    assert "persist_killswitch_draft" not in weekly
    assert "t2_event_ids()" in weekly
    assert "write_targets_supplement_report" not in inspect.getsource(events)


def test_auto_apply_quant_targets_writes_yaml_not_target_csv(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from alpha_system.ui.services.weekly_domain_gates import (
        AUTO_TARGET_SOURCE,
        auto_apply_proposal_quant_targets,
    )

    clear_entries()
    data = tmp_path / "data"
    data.mkdir()
    target_csv = data / "target_portfolio.csv"
    target_csv.write_text(
        "ticker,asset_group,target_weight\n005930,kr_alpha,10\n",
        encoding="utf-8",
    )
    before = target_csv.read_text(encoding="utf-8")
    rows = [
        SimpleNamespace(
            ticker="005930",
            name="삼성전자",
            extra={
                "quant_pbr_justified": 1.7,
                "quant_price_justified": 72000,
                "quant_pbr_draft": 1.9,
                "quant_price_mid": 80000,
            },
        ),
        SimpleNamespace(
            ticker="000660",
            name="SK하이닉스",
            extra={},
        ),
        SimpleNamespace(
            ticker="035420",
            name="NAVER",
            extra={"quant_pbr_justified": 2.1, "quant_price_justified": 180000},
        ),
    ]
    yaml_path = data / "kr_alpha_exit_targets.yaml"
    yaml_path.write_text(
        "tickers:\n  '035420':\n    approved_by: operator\n    target_price: 1\n"
        "    valuation:\n      pbr_max: 1.0\n",
        encoding="utf-8",
    )
    out = auto_apply_proposal_quant_targets(
        root=tmp_path,
        rows=rows,
        as_of=date(2026, 8, 31),
        journal_path=tmp_path / "j.jsonl",
    )
    assert out["target_portfolio_written"] is False
    assert target_csv.read_text(encoding="utf-8") == before
    assert "005930" in out["applied"]
    assert "000660" in out["skipped"]
    assert "035420" in out["applied"]
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    samsung = raw["tickers"]["005930"]
    assert samsung["source"] == AUTO_TARGET_SOURCE
    assert samsung["valuation"]["pbr_max"] == 1.9
    assert samsung["target_price"] == 80000
    assert raw["tickers"]["035420"]["target_price"] == 180000
    assert raw["tickers"]["035420"]["source"] == AUTO_TARGET_SOURCE
    again = auto_apply_proposal_quant_targets(
        root=tmp_path,
        rows=rows[:1],
        as_of=date(2026, 8, 31),
        journal_path=tmp_path / "j.jsonl",
    )
    assert again["applied"] == []
    assert "005930" in again["unchanged"]
    clear_entries()
