"""Weekly integrated qualitative report + domain gates."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from alpha_system.journal import clear_entries, list_entries
from alpha_system.ui.services.cecs_workbench import import_ai_suggestions, reopen_final_for_rescoring
from alpha_system.ui.services.weekly_domain_gates import approve_domain, mark_sources_reviewed
from alpha_system.ui.services.weekly_qual_report import (
    WeeklySubject,
    load_cde_copy_prompt,
    parse_weekly_qual_markdown,
    persist_targets_supplement,
    persist_weekly_suggestions,
    waiting_target_subjects,
    write_targets_supplement_report,
    write_weekly_qual_report,
)


def test_load_cde_copy_prompt_b_from_docs() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    prompt = load_cde_copy_prompt(root, which="B")
    assert "E_TARGET_VALUATION" in prompt or "목표가" in prompt
    assert "### TARGET" in prompt
    assert "target_portfolio" in prompt
    prompt_a = load_cde_copy_prompt(root, which="A")
    assert "C_T2_EVENTS" in prompt_a
    prompt_c = load_cde_copy_prompt(root, which="C")
    assert "A_CECS_SUMMARY" in prompt_c or "CECS" in prompt_c
    # Missing docs → fallback still usable
    assert "완성 Markdown" in load_cde_copy_prompt(Path("/nonexistent"), which="B")
    assert "CECS" in load_cde_copy_prompt(Path("/nonexistent"), which="C")


def test_weekly_request_has_sections_a_to_e(tmp_path: Path) -> None:
    clear_entries()
    report = write_weekly_qual_report(
        summary_subjects=[
            WeeklySubject("005830", "DB손해보험", "insurance"),
            WeeklySubject("021240", "코웨이", "consumer"),
        ],
        deep_subjects=[WeeklySubject("005830", "DB손해보험", "insurance")],
        t2_event_ids=["commercial_code_enforcement_decrees"],
        docs_dir=tmp_path / "docs",
        as_of=date(2026, 7, 17),
        generated_at=datetime(2026, 7, 17, 16, 0, 0),
        journal_path=tmp_path / "journal.jsonl",
    )
    md = report.markdown
    for section in (
        "A_CECS_SUMMARY",
        "B_FINAL6_DEEP",
        "C_T2_EVENTS",
        "D_THESIS",
        "E_TARGET_VALUATION",
    ):
        assert f"## {section}" in md
    assert "## [005830] DB손해보험" in md
    assert "### DEEP [005830]" in md
    assert "### EVENT [commercial_code_enforcement_decrees]" in md
    assert "### THESIS" in md
    assert "### TARGET [005830]" in md
    assert "숫자 칸 형식" in md
    assert "65 (AI 초안)" in md  # as forbidden example in the rules
    assert "숫자만" in md
    assert "48000" in md  # target_price example
    assert "0.75" in md  # pbr_max example
    assert "CECS 채점표" in md or "CECS 3축 채점표" in md
    assert "T2 확정 기준" in md
    assert "실측 범위" in md
    assert "system:weekly_neutral_hold" in md
    assert "EXIT_TARGET_ANCHOR" in md or "실측 앵커" in md
    assert "### pension" in md
    # pension/purpose prefilled; execution still blank
    assert "- 점수 제안(0-100): 50" in md
    assert "C_T2_EVENTS` → `D_THESIS` → `E_TARGET_VALUATION`" in md
    assert list_entries(action_kind="WEEKLY_QUAL_REPORT_GENERATED")
    clear_entries()


def test_monthly_cecs_report_execution_only(tmp_path: Path) -> None:
    clear_entries()
    from alpha_system.ui.services.weekly_qual_report import write_monthly_cecs_report

    report = write_monthly_cecs_report(
        summary_subjects=[
            WeeklySubject("005830", "DB손해보험", "insurance"),
            WeeklySubject("021240", "코웨이", "consumer"),
        ],
        docs_dir=tmp_path / "docs",
        as_of=date(2026, 8, 3),
        generated_at=datetime(2026, 8, 3, 12, 0, 0),
        journal_path=tmp_path / "journal.jsonl",
    )
    md = report.markdown
    assert report.path.name.startswith("monthly_cecs_report_")
    assert "## A_CECS_SUMMARY" in md
    assert "## C_T2_EVENTS" not in md
    assert "## E_TARGET_VALUATION" not in md
    assert "system:monthly_neutral_hold" in md
    assert "순위" in md and ("미반영" in md or "무관" in md)
    import re

    assert len(re.findall(r"^## \[\d{6}\]", md, re.M)) == 2
    assert "system:monthly_neutral_hold" in md
    assert md.count("- 점수 제안(0-100): 50") == 4  # pension+purpose × 2
    assert list_entries(action_kind="MONTHLY_CECS_REPORT_GENERATED")
    clear_entries()


def test_load_cde_prompts_mention_anchor_and_cecs_ledger() -> None:
    root = Path(__file__).resolve().parents[1]
    prompt_a = load_cde_copy_prompt(root, which="A")
    prompt_b = load_cde_copy_prompt(root, which="B")
    prompt_c = load_cde_copy_prompt(root, which="C")
    assert "실측" in prompt_a or "앵커" in prompt_a or "BPS" in prompt_a
    assert "실측" in prompt_b or "앵커" in prompt_b or "BPS" in prompt_b
    assert "execution" in prompt_c.lower() or "execution만" in prompt_c
    assert "Ops A" in prompt_c or "순위" in prompt_c


def test_weekly_be_requires_deep_subjects(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="proposal_book|B/E"):
        write_weekly_qual_report(
            summary_subjects=[WeeklySubject("005830", "DB손해보험", "insurance")],
            deep_subjects=[],
            t2_event_ids=["commercial_code_enforcement_decrees"],
            docs_dir=tmp_path / "docs",
            as_of=date(2026, 7, 18),
        )


def test_apply_targets_fails_closed_when_deep_tickers_empty(tmp_path: Path) -> None:
    clear_entries()
    root = tmp_path
    (root / "data").mkdir()
    (root / "data" / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\n005830,kr_alpha,10\n", encoding="utf-8"
    )
    suggestions = {
        "report_id": "WQR-empty-deep",
        "deep_tickers": [],
        "targets": [
            {
                "ticker": "005830",
                "pbr_max": 1.0,
                "fundamental_reason": "x",
                "rationale": "y",
                "sources": ["https://example.com"],
            }
        ],
        "source_reviewed": {"targets": ["005830"]},
        "approved": {k: False for k in ("cecs", "t2", "thesis", "targets")},
        "domain_status": {"targets": "ai_suggested"},
    }
    import json

    (root / "data" / "weekly_qual_suggestions.json").write_text(
        json.dumps(suggestions, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="deep_tickers"):
        approve_domain(
            root=root,
            domain="targets",
            approved_by="operator",
            as_of=date(2026, 7, 18),
            reviewed_keys=["005830"],
            journal_path=tmp_path / "j.jsonl",
            exit_targets_path=root / "data" / "kr_alpha_exit_targets.yaml",
            confirm_steps=2,
        )
    clear_entries()


def test_weekly_report_marks_approved_as_target_ref(tmp_path: Path) -> None:
    """E section: YAML 승인 종목은 TARGET_REF, 대기만 TARGET 공란."""
    root = tmp_path
    (root / "data").mkdir()
    yaml_path = root / "data" / "kr_alpha_exit_targets.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "tickers": {
                    "005830": {
                        "valuation": {"pbr_max": 0.9},
                        "target_price": 120000,
                        "approved_as_of": "2026-07-01",
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    from alpha_system.ui.services.weekly_qual_report import load_exit_target_entries

    report = write_weekly_qual_report(
        summary_subjects=[WeeklySubject("005830", "DB손보", "insurance")],
        deep_subjects=[
            WeeklySubject("005830", "DB손보", "insurance"),
            WeeklySubject("021240", "코웨이", "consumer"),
        ],
        t2_event_ids=["commercial_code_enforcement_decrees"],
        docs_dir=tmp_path / "docs",
        as_of=date(2026, 7, 18),
        generated_at=datetime(2026, 7, 18, 9, 0, 0),
        existing_exit=load_exit_target_entries(root),
    )
    e = report.markdown.split("## E_TARGET_VALUATION", 1)[1]
    assert "### TARGET_REF [005830]" in e
    assert "### TARGET [021240]" in e
    assert "### TARGET [005830]" not in e
    assert "pbr_max: _____" not in e.split("### TARGET_REF [005830]", 1)[1].split("###", 1)[0]


def test_parse_ignores_target_ref_blocks() -> None:
    md = """## E_TARGET_VALUATION

### TARGET_REF [005830] DB손보
- pbr_max(승인): 0.9
- target_price(승인): 120000
- 펀더멘털 사유: should-not-parse
- 근거: should-not-parse
- 출처:
  - https://example.com/ref

### TARGET [021240] 코웨이
- pbr_max: 2.1
- target_price: 140000
- 펀더멘털 사유: 렌탈
- 근거: 피어
- 출처:
  - https://example.com/coway
"""
    parsed = parse_weekly_qual_markdown(md)
    assert [t.ticker for t in parsed.targets] == ["021240"]


def test_apply_targets_protects_existing_yaml(tmp_path: Path) -> None:
    """승인 시 이미 있는 pbr_max/target_price는 덮어쓰지 않음."""
    clear_entries()
    root = tmp_path
    (root / "data").mkdir()
    (root / "data" / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\n005830,kr_alpha,10\n021240,kr_alpha,10\n",
        encoding="utf-8",
    )
    yaml_path = root / "data" / "kr_alpha_exit_targets.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "tickers": {
                    "005830": {
                        "valuation": {"pbr_max": 0.9},
                        "target_price": 120000,
                        "approved_as_of": "2026-07-01",
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    import json

    suggestions = {
        "report_id": "WQR-protect",
        "deep_tickers": ["005830", "021240"],
        "targets": [
            {
                "ticker": "005830",
                "pbr_max": 9.9,
                "target_price": 1,
                "fundamental_reason": "bad overwrite",
                "rationale": "should be protected",
                "sources": ["https://example.com/a"],
            },
            {
                "ticker": "021240",
                "pbr_max": 2.1,
                "target_price": 140000,
                "fundamental_reason": "new",
                "rationale": "ok",
                "sources": ["https://example.com/b"],
            },
        ],
        "source_reviewed": {"targets": ["005830", "021240"]},
        "approved": {k: False for k in ("cecs", "t2", "thesis", "targets")},
        "domain_status": {"targets": "ai_suggested"},
    }
    (root / "data" / "weekly_qual_suggestions.json").write_text(
        json.dumps(suggestions, ensure_ascii=False), encoding="utf-8"
    )
    result = approve_domain(
        root=root,
        domain="targets",
        approved_by="operator",
        as_of=date(2026, 7, 18),
        reviewed_keys=["005830", "021240"],
        journal_path=tmp_path / "j.jsonl",
        exit_targets_path=yaml_path,
        confirm_steps=2,
    )
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert data["tickers"]["005830"]["valuation"]["pbr_max"] == 0.9
    assert data["tickers"]["005830"]["target_price"] == 120000
    assert data["tickers"]["021240"]["valuation"]["pbr_max"] == 2.1
    assert "005830" in (result["applied"].get("protected") or [])
    assert "021240" in (result["applied"].get("tickers") or [])
    clear_entries()


def test_persist_deep_tickers_ignores_targets_union(tmp_path: Path) -> None:
    from alpha_system.ui.services.weekly_qual_report import (
        parse_weekly_qual_markdown,
        persist_weekly_suggestions,
    )

    root = tmp_path
    (root / "data").mkdir()
    parsed = parse_weekly_qual_markdown(_filled_weekly_md())
    out = persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="x.md",
        as_of=date(2026, 7, 18),
        locked_deep_tickers=["005830"],
    )
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["deep_tickers"] == ["005830"]
    assert "999999" not in data["deep_tickers"]


def test_persist_drops_targets_outside_locked_final(tmp_path: Path) -> None:
    """Upload may contain old-final TARGET blocks; import must not keep them."""
    root = tmp_path
    (root / "data").mkdir()
    md = _filled_weekly_md() + """
### TARGET [316140] 광주신발
- pbr_max: 0.86
- target_price: 43000
- 펀더멘털 사유: 옛 final
- 근거: 이전 주
- 출처:
  - https://example.com/old
"""
    parsed = parse_weekly_qual_markdown(md)
    assert any(str(t.ticker).zfill(6) == "316140" for t in parsed.targets)
    out = persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="stale.md",
        as_of=date(2026, 7, 25),
        locked_deep_tickers=["005830"],
    )
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    kept = {str(t.get("ticker")).zfill(6) for t in data["targets"]}
    assert "005830" in kept
    assert "316140" not in kept
    assert any("316140" in f for f in (data.get("domain_failures") or {}).get("targets") or [])


def test_targets_supplement_drops_prior_out_of_final(tmp_path: Path) -> None:
    """E-only merge must not preserve last week's out-of-final targets."""
    import json

    root = tmp_path
    (root / "data").mkdir()
    prior = {
        "report_id": "WQR-prior",
        "domain_status": {
            "cecs": "empty",
            "t2": "empty",
            "thesis": "empty",
            "targets": "ai_suggested",
        },
        "targets": [
            {
                "ticker": "316140",
                "pbr_max": 0.86,
                "target_price": 43000,
                "fundamental_reason": "old",
                "rationale": "old",
                "sources": ["https://example.com/old"],
            },
            {
                "ticker": "005830",
                "pbr_max": 1.0,
                "target_price": 100000,
                "fundamental_reason": "keep",
                "rationale": "in final",
                "sources": ["https://example.com/db"],
            },
        ],
        "approved": {k: False for k in ("cecs", "t2", "thesis", "targets")},
        "deep_tickers": ["005830", "021240"],
    }
    (root / "data" / "weekly_qual_suggestions.json").write_text(
        json.dumps(prior, ensure_ascii=False), encoding="utf-8"
    )
    filled = """## E_TARGET_VALUATION

### TARGET [021240] 코웨이
- pbr_max: 2.1
- target_price: 140000
- 펀더멘털 사유: 렌탈
- 근거: 피어
- 출처:
  - https://example.com/coway
"""
    parsed = parse_weekly_qual_markdown(filled)
    out = persist_targets_supplement(
        root=root,
        parsed=parsed,
        report_name="supp.md",
        as_of=date(2026, 7, 25),
        proposal_tickers=["005830", "021240"],
        waiting_tickers=["021240"],
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    kept = {str(t.get("ticker")).zfill(6) for t in payload["targets"]}
    # 대기(021240)만 큐에 남김 — 이미 승인된 005830을 재승인 큐에 두면 YAML 덮어쓰기 위험
    assert kept == {"021240"}
    assert "316140" not in kept
    assert "005830" not in kept


def test_apply_targets_rejects_ticker_not_in_final_snapshot(tmp_path: Path) -> None:
    clear_entries()
    root = tmp_path
    (root / "data").mkdir()
    target_csv = root / "data" / "target_portfolio.csv"
    target_csv.write_text("ticker,asset_group,target_weight\n005830,kr_alpha,10\n", encoding="utf-8")
    suggestions = {
        "report_id": "WQR-test",
        "deep_tickers": ["005830"],
        "targets": [
            {
                "ticker": "999999",
                "pbr_max": 1.0,
                "fundamental_reason": "stale",
                "rationale": "not in final",
                "sources": ["https://example.com"],
            }
        ],
        "source_reviewed": {"targets": ["999999"]},
        "approved": {k: False for k in ("cecs", "t2", "thesis", "targets")},
        "domain_status": {"targets": "ai_suggested"},
    }
    import json

    (root / "data" / "weekly_qual_suggestions.json").write_text(
        json.dumps(suggestions, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="최종 선정"):
        approve_domain(
            root=root,
            domain="targets",
            approved_by="operator",
            as_of=date(2026, 7, 18),
            reviewed_keys=["999999"],
            journal_path=tmp_path / "j.jsonl",
            exit_targets_path=root / "data" / "kr_alpha_exit_targets.yaml",
            confirm_steps=2,
        )
    clear_entries()


def test_apply_targets_rejects_sell_side_sot(tmp_path: Path) -> None:
    """QUAL_PUBLIC_OVERLAY: broker/consensus SoT must not write exit YAML."""
    clear_entries()
    root = tmp_path
    (root / "data").mkdir()
    (root / "data" / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\n005830,kr_alpha,10\n", encoding="utf-8"
    )
    suggestions = {
        "report_id": "WQR-sell-side",
        "deep_tickers": ["005830"],
        "targets": [
            {
                "ticker": "005830",
                "pbr_max": 0.8,
                "target_price": 120000,
                "fundamental_reason": "KB증권 목표가 상향",
                "rationale": "목표가 컨센서스 약 12만원",
                "sources": ["https://example.com/broker"],
            }
        ],
        "source_reviewed": {"targets": ["005830"]},
        "approved": {k: False for k in ("cecs", "t2", "thesis", "targets")},
        "domain_status": {"targets": "ai_suggested"},
    }
    import json

    (root / "data" / "weekly_qual_suggestions.json").write_text(
        json.dumps(suggestions, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="증권사·컨센서스"):
        approve_domain(
            root=root,
            domain="targets",
            approved_by="operator",
            as_of=date(2026, 7, 18),
            reviewed_keys=["005830"],
            journal_path=tmp_path / "j.jsonl",
            exit_targets_path=root / "data" / "kr_alpha_exit_targets.yaml",
            confirm_steps=2,
        )
    assert not (root / "data" / "kr_alpha_exit_targets.yaml").exists()
    clear_entries()


def test_domain_approve_is_isolated_and_target_portfolio_unchanged(tmp_path: Path) -> None:
    clear_entries()
    root = tmp_path
    (root / "data").mkdir()
    target_csv = root / "data" / "target_portfolio.csv"
    target_csv.write_text("ticker,asset_group,target_weight\n005830,kr_alpha,10\n", encoding="utf-8")
    before = hashlib.sha256(target_csv.read_bytes()).hexdigest()

    cecs = root / "data" / "cecs_manual_scoring_template.csv"
    pd.DataFrame(
        [
            {
                "ticker": "005830",
                "name": "DB손해보험",
                "as_of": "2026-07-17",
                "sector": "insurance",
                "execution_continuity": "",
                "execution_rationale": "",
                "pension_flow_score": "",
                "pension_rationale": "",
                "investment_purpose_flag": "",
                "investment_purpose_rationale": "",
                "policy_dependency_flag": "0.50",
                "cecs_computed": "",
                "status": "final",
            }
        ]
    ).to_csv(cecs, index=False)

    filled = _filled_weekly_md()
    parsed = parse_weekly_qual_markdown(filled)
    assert parsed.domain_status["cecs"] == "ai_suggested"
    assert parsed.domain_status["t2"] == "ai_suggested"
    assert parsed.domain_status["thesis"] == "ai_suggested"
    assert parsed.domain_status["targets"] == "ai_suggested"

    from alpha_system.ui.services.weekly_qual_report import (
        SUGGESTIONS_LANE_MONTHLY,
        SUGGESTIONS_LANE_WEEKLY,
        persist_weekly_suggestions,
    )

    persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="weekly_filled.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_WEEKLY,
    )
    persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="monthly_filled.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_MONTHLY,
    )

    with pytest.raises(ValueError, match="출처 미확인"):
        approve_domain(
            root=root,
            domain="t2",
            approved_by="op",
            as_of=date(2026, 7, 17),
            reviewed_keys=[],
            confirm_steps=2,
            journal_path=root / "journal.jsonl",
            runtime_path=root / "data" / "alpha_dashboard_runtime.json",
        )

    mark_sources_reviewed(root=root, domain="t2", keys=["commercial_code_enforcement_decrees"])
    approve_domain(
        root=root,
        domain="t2",
        approved_by="op",
        as_of=date(2026, 7, 17),
        reviewed_keys=["commercial_code_enforcement_decrees"],
        confirm_steps=2,
        journal_path=root / "journal.jsonl",
        runtime_path=root / "data" / "alpha_dashboard_runtime.json",
    )

    payload = __import__("json").loads(
        (root / "data" / "weekly_qual_suggestions.json").read_text(encoding="utf-8")
    )
    assert payload["approved"]["t2"] is True
    assert payload["approved"]["cecs"] is False
    assert payload["approved"]["thesis"] is False
    assert payload["approved"]["targets"] is False

    # Upload alone did not demote final. Explicit domain approval performs an
    # audited re-open + immediate re-finalization in one operator action.
    assert pd.read_csv(cecs, dtype=str).iloc[0]["status"] == "final"
    mark_sources_reviewed(root=root, domain="cecs", keys=["005830"])
    approve_domain(
        root=root,
        domain="cecs",
        approved_by="op",
        as_of=date(2026, 7, 17),
        reviewed_keys=["005830"],
        journal_path=root / "journal.jsonl",
        cecs_path=cecs,
    )
    assert pd.read_csv(cecs, dtype=str).iloc[0]["status"] == "final"

    mark_sources_reviewed(root=root, domain="targets", keys=["005830"])
    approve_domain(
        root=root,
        domain="targets",
        approved_by="op",
        as_of=date(2026, 7, 17),
        reviewed_keys=["005830"],
        journal_path=root / "journal.jsonl",
        exit_targets_path=root / "data" / "kr_alpha_exit_targets.yaml",
    )
    yaml_data = yaml.safe_load(
        (root / "data" / "kr_alpha_exit_targets.yaml").read_text(encoding="utf-8")
    )
    assert yaml_data["tickers"]["005830"]["valuation"]["pbr_max"] == 1.2
    assert hashlib.sha256(target_csv.read_bytes()).hexdigest() == before

    kinds = {e.action_kind for e in list_entries()}
    assert "T2_EVENT_RECORD" in kinds
    assert "TARGET_VALUATION_MODIFY" in kinds
    assert "WEEKLY_DOMAIN_APPROVED" in kinds
    clear_entries()


def test_reupload_preserves_only_identical_approved_domains(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    filled = _filled_weekly_md()
    parsed = parse_weekly_qual_markdown(filled)
    from alpha_system.ui.services.weekly_qual_report import (
        SUGGESTIONS_LANE_MONTHLY,
        SUGGESTIONS_LANE_WEEKLY,
    )

    weekly_path = persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="weekly_filled.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_WEEKLY,
    )
    monthly_path = persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="monthly_filled.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_MONTHLY,
    )
    json_mod = __import__("json")
    weekly = json_mod.loads(weekly_path.read_text(encoding="utf-8"))
    weekly["approved"]["t2"] = True
    weekly["domain_status"]["t2"] = "approved"
    weekly["source_reviewed"]["t2"] = ["commercial_code_enforcement_decrees"]
    weekly["approved_meta"] = {"t2": {"approved_by": "op"}}
    weekly_path.write_text(
        json_mod.dumps(weekly, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monthly = json_mod.loads(monthly_path.read_text(encoding="utf-8"))
    monthly["approved"]["cecs"] = True
    monthly["domain_status"]["cecs"] = "approved"
    monthly["source_reviewed"]["cecs"] = ["005830"]
    monthly["approved_meta"] = {"cecs": {"approved_by": "op"}}
    monthly_path.write_text(
        json_mod.dumps(monthly, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Identical re-upload keeps approvals in each lane.
    persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="weekly_filled_v2.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_WEEKLY,
    )
    persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="monthly_filled_v2.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_MONTHLY,
    )
    assert json_mod.loads(weekly_path.read_text(encoding="utf-8"))["approved"]["t2"] is True
    assert json_mod.loads(monthly_path.read_text(encoding="utf-8"))["approved"]["cecs"] is True

    # Changing CECS invalidates monthly CECS approval; weekly T2 stays approved.
    changed = parse_weekly_qual_markdown(
        filled.replace(
            "- 점수 제안(0-100): 80",
            "- 점수 제안(0-100): 81",
            1,
        )
    )
    persist_weekly_suggestions(
        root=root,
        parsed=changed,
        report_name="weekly_filled_v3.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_WEEKLY,
    )
    persist_weekly_suggestions(
        root=root,
        parsed=changed,
        report_name="monthly_filled_v3.md",
        as_of=date(2026, 7, 17),
        journal_path=root / "journal.jsonl",
        lane=SUGGESTIONS_LANE_MONTHLY,
    )
    assert json_mod.loads(weekly_path.read_text(encoding="utf-8"))["approved"]["t2"] is True
    assert json_mod.loads(monthly_path.read_text(encoding="utf-8"))["approved"]["cecs"] is False


def test_cecs_final_guard_blocks_import_without_reopen(tmp_path: Path) -> None:
    clear_entries()
    path = tmp_path / "cecs.csv"
    pd.DataFrame(
        [
            {
                "ticker": "005830",
                "name": "DB손해보험",
                "execution_continuity": "0.80",
                "pension_flow_score": "0.50",
                "investment_purpose_flag": "1.00",
                "policy_dependency_flag": "0.50",
                "cecs_computed": "70",
                "status": "final",
                "execution_rationale": "old",
                "pension_rationale": "old",
                "investment_purpose_rationale": "old",
            }
        ]
    ).to_csv(path, index=False)

    from alpha_system.ui.services.cecs_ai_research import parse_cecs_ai_research_markdown

    parsed = parse_cecs_ai_research_markdown(
        """## [005830] DB손해보험

### execution
- 점수 제안(0-100): 90
- 근거: new
- 출처: [1차 출처: DART](https://dart.fss.or.kr/e1)

### pension
- 점수 제안(0-100): 50
- 근거: new
- 출처: [1차 출처: DART](https://dart.fss.or.kr/p1)

### purpose
- 점수 제안(0-100): 100
- 근거: new
- 출처: [1차 출처: DART](https://dart.fss.or.kr/u1)
"""
    )
    result = import_ai_suggestions(
        path=path,
        suggestions=parsed.suggestions,
        report_name="x.md",
        as_of=date(2026, 7, 17),
        journal_path=tmp_path / "j.jsonl",
    )
    assert result.imported_tickers == ()
    assert any("final" in f for f in result.failures)
    assert pd.read_csv(path, dtype=str).iloc[0]["status"] == "final"

    reopen_final_for_rescoring(
        path=path,
        tickers=["005830"],
        reopened_by="op",
        as_of=date(2026, 7, 17),
        reason="주간 리포트 재채점",
        journal_path=tmp_path / "j.jsonl",
    )
    assert pd.read_csv(path, dtype=str).iloc[0]["status"] == "draft"
    result2 = import_ai_suggestions(
        path=path,
        suggestions=parsed.suggestions,
        report_name="x.md",
        as_of=date(2026, 7, 17),
        journal_path=tmp_path / "j.jsonl",
    )
    assert result2.imported_tickers == ("005830",)
    assert pd.read_csv(path, dtype=str).iloc[0]["status"] == "ai_suggested"
    clear_entries()


def _filled_weekly_md() -> str:
    return """# 주간 통합 정성 AI 요청서

- report_id: `WQR-TEST`
- as_of: `2026-07-17`
- input_snapshot_hash: `abc`

## A_CECS_SUMMARY

## [005830] DB손해보험

### execution
- 점수 제안(0-100): 80
- 근거: ok
- 출처: [1차 출처: DART](https://dart.fss.or.kr/e1)

### pension
- 점수 제안(0-100): 50
- 근거: ok
- 출처: [1차 출처: DART](https://dart.fss.or.kr/p1)

### purpose
- 점수 제안(0-100): 100
- 근거: ok
- 출처: [1차 출처: DART](https://dart.fss.or.kr/u1)

## B_FINAL6_DEEP

### DEEP [005830] DB손해보험
- 공시/지배구조: ok
- 자사주·배당·환원: ok
- 연기금·수급: ok
- 투자목적: ok
- 리스크: ok
- 출처:
  - [1차 출처: DART](https://dart.fss.or.kr/d1)

## C_T2_EVENTS

### EVENT [commercial_code_enforcement_decrees]
- fired: true
- 근거: 시행령 확정 공고
- 출처:
  - https://www.law.go.kr/example

## D_THESIS

### THESIS
- damage: false
- 근거: 훼손 징후 없음
- 출처:
  - https://example.com/thesis

## E_TARGET_VALUATION

### TARGET [005830] DB손해보험
- pbr_max: 1.2
- target_price: _____
- 펀더멘털 사유: ROE 안정·배당 지속
- 근거: 피어 밴드 상단
- 출처:
  - https://example.com/val
"""


def test_targets_supplement_e_only_and_merge(tmp_path: Path) -> None:
    clear_entries()
    root = tmp_path
    (root / "data").mkdir()
    (root / "data" / "kr_alpha_exit_targets.yaml").write_text(
        "tickers:\n  '005830':\n    valuation:\n      pbr_max: 1.0\n",
        encoding="utf-8",
    )
    # Pre-existing CECS suggestion envelope must survive supplement merge.
    import json

    prior = {
        "report_id": "WQR-prior",
        "domain_status": {
            "cecs": "ai_suggested",
            "t2": "empty",
            "thesis": "empty",
            "targets": "empty",
        },
        "cecs": [{"ticker": "005830", "name": "DB"}],
        "targets": [],
        "approved": {k: False for k in ("cecs", "t2", "thesis", "targets")},
        "deep_tickers": ["005830", "021240"],
    }
    (root / "data" / "weekly_qual_suggestions.json").write_text(
        json.dumps(prior, ensure_ascii=False), encoding="utf-8"
    )

    from alpha_system.ui.services.weekly_qual_report import (
        persist_targets_supplement,
        waiting_target_subjects,
        write_targets_supplement_report,
    )

    rows = [
        WeeklySubject("005830", "DB손해보험", "insurance"),
        WeeklySubject("021240", "코웨이", "consumer"),
    ]
    waiting = waiting_target_subjects(rows, root=root)
    assert [s.ticker for s in waiting] == ["021240"]

    report = write_targets_supplement_report(
        waiting_subjects=waiting,
        proposal_tickers=["005830", "021240"],
        docs_dir=root / "docs",
        as_of=date(2026, 7, 18),
        generated_at=datetime(2026, 7, 18, 10, 0, 0),
        journal_path=root / "journal.jsonl",
    )
    assert "E_TARGET_VALUATION" in report.markdown
    assert "A_CECS_SUMMARY" not in report.markdown
    assert "021240" in report.markdown
    assert "005830" not in report.markdown.split("## E_TARGET_VALUATION", 1)[1]
    assert list_entries(action_kind="WEEKLY_TARGETS_SUPPLEMENT_GENERATED")

    filled = """# supplement
- report_id: `WQR-E-test`

## E_TARGET_VALUATION

### TARGET [021240] 코웨이
- pbr_max: 2.1
- target_price: 140000
- 펀더멘털 사유: 렌탈 계정 순증
- 근거: 피어 대비
- 출처:
  - https://example.com/coway
"""
    parsed = parse_weekly_qual_markdown(filled)
    assert parsed.targets and parsed.targets[0].ticker == "021240"
    out = persist_targets_supplement(
        root=root,
        parsed=parsed,
        report_name="supp.md",
        as_of=date(2026, 7, 18),
        proposal_tickers=["005830", "021240"],
        waiting_tickers=["021240"],
        journal_path=root / "journal.jsonl",
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "targets_supplement"
    assert payload["domain_status"]["cecs"] == "empty"
    assert payload["cecs"] == []
    assert payload["domain_status"]["targets"] == "ai_suggested"
    assert {t["ticker"] for t in payload["targets"]} == {"021240"}
    assert set(payload["deep_tickers"]) == {"005830", "021240"}
    monthly = json.loads(
        (root / "data" / "monthly_cecs_suggestions.json").read_text(encoding="utf-8")
    )
    assert monthly["domain_status"]["cecs"] == "ai_suggested"
    assert monthly["cecs"][0]["ticker"] == "005830"
    assert list_entries(action_kind="WEEKLY_TARGETS_SUPPLEMENT_IMPORT")
    clear_entries()


def test_monthly_upload_does_not_wipe_weekly_cde(tmp_path: Path) -> None:
    """Monthly CECS persist must leave weekly C/D/E file intact."""
    import json

    from alpha_system.ui.services.weekly_qual_report import (
        SUGGESTIONS_LANE_MONTHLY,
        SUGGESTIONS_LANE_WEEKLY,
        load_merged_qual_status,
        persist_weekly_suggestions,
    )

    root = tmp_path
    (root / "data").mkdir()
    weekly_parsed = parse_weekly_qual_markdown(_filled_weekly_md())
    weekly_path = persist_weekly_suggestions(
        root=root,
        parsed=weekly_parsed,
        report_name="weekly.md",
        as_of=date(2026, 7, 18),
        locked_deep_tickers=["005830"],
        lane=SUGGESTIONS_LANE_WEEKLY,
    )
    weekly_before = json.loads(weekly_path.read_text(encoding="utf-8"))
    assert weekly_before["domain_status"]["t2"] == "ai_suggested"
    assert weekly_before["cecs"] == []

    monthly_md = """# monthly
- report_id: `WQR-M`
- as_of: `2026-07-18`
- input_snapshot_hash: `m1`

## A_CECS_SUMMARY

## [005830] DB손해보험

### execution
- 점수 제안(0-100): 70
- 근거: monthly
- 출처: [1차 출처: DART](https://dart.fss.or.kr/m1)

### pension
- 점수 제안(0-100): 60
- 근거: monthly
- 출처: [1차 출처: DART](https://dart.fss.or.kr/m2)

### purpose
- 점수 제안(0-100): 80
- 근거: monthly
- 출처: [1차 출처: DART](https://dart.fss.or.kr/m3)
"""
    monthly_parsed = parse_weekly_qual_markdown(monthly_md)
    monthly_path = persist_weekly_suggestions(
        root=root,
        parsed=monthly_parsed,
        report_name="monthly.md",
        as_of=date(2026, 7, 18),
        lane=SUGGESTIONS_LANE_MONTHLY,
    )
    assert monthly_path.name == "monthly_cecs_suggestions.json"
    weekly_after = json.loads(weekly_path.read_text(encoding="utf-8"))
    assert weekly_after["domain_status"]["t2"] == "ai_suggested"
    assert weekly_after["t2"]
    assert weekly_after["thesis"] is not None
    assert weekly_after["targets"]
    monthly = json.loads(monthly_path.read_text(encoding="utf-8"))
    assert monthly["domain_status"]["cecs"] == "ai_suggested"
    assert monthly["cecs"]
    assert monthly["t2"] == []
    merged = load_merged_qual_status(root)
    assert merged["domain_status"]["t2"] == "ai_suggested"
    assert merged["domain_status"]["cecs"] == "ai_suggested"
    clear_entries()


def test_targets_supplement_rejects_outside_waiting(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data").mkdir()
    filled = """## E_TARGET_VALUATION

### TARGET [000660] SK하이닉스
- pbr_max: 1.5
- target_price: 200000
- 펀더멘털 사유: x
- 근거: y
- 출처:
  - https://example.com/h
"""
    parsed = parse_weekly_qual_markdown(filled)
    with pytest.raises(ValueError, match="최종 선정 밖|대기 목록"):
        persist_targets_supplement(
            root=root,
            parsed=parsed,
            report_name="bad.md",
            as_of=date(2026, 7, 18),
            proposal_tickers=["021240"],
            waiting_tickers=["021240"],
        )


def test_empty_targets_auto_not_applicable_gate(tmp_path: Path) -> None:
    """When all proposal exits already exist, weekly targets gate auto-satisfies."""
    clear_entries()
    root = tmp_path
    (root / "data").mkdir()
    (root / "data" / "kr_alpha_exit_targets.yaml").write_text(
        "tickers:\n  '005830':\n    valuation:\n      pbr_max: 1.0\n    target_price: 210000\n",
        encoding="utf-8",
    )
    md = """# weekly
- report_id: `WQR-empty-e`
- as_of: `2026-07-31`
- input_snapshot_hash: `abc`

## C_T2_EVENTS
### EVENT [commercial_code_enforcement_decrees]
- fired: false
- 근거: as_of 기준 관보 미확인
- 출처:
  - 확인 불가

## D_THESIS
### THESIS
- damage: false
- 근거: 제도 후퇴 없음
- 출처:
  - 확인 불가

## E_TARGET_VALUATION
### 대기 (채움 대상)
(대기 종목 없음)
"""
    parsed = parse_weekly_qual_markdown(md)
    assert parsed.domain_status["targets"] == "empty"
    out = persist_weekly_suggestions(
        root=root,
        parsed=parsed,
        report_name="empty_e.md",
        as_of=date(2026, 7, 31),
        locked_deep_tickers=["005830"],
        lane="weekly",
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["domain_status"]["targets"] == "not_applicable"
    assert data["approved"]["targets"] is True
    assert (data.get("approved_meta") or {}).get("targets", {}).get("applied", {}).get(
        "skipped"
    ) is True
