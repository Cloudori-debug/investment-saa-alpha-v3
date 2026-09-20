"""OpenDART CECS fact pack — JSON APIs, no HTML viewers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_system.ui.services.cecs_opendart_pack import (
    _TickerFacts,
    collect_cecs_opendart_pack,
    execution_hint,
    flags_from_facts,
    last_four_completed_quarters,
    pension_hint,
    purpose_hint,
)
from alpha_system.ui.services.weekly_qual_report import load_cde_copy_prompt
from src.data_refresh.dart_client import DartCredentialsError


def test_last_four_completed_quarters() -> None:
    assert last_four_completed_quarters(date(2026, 8, 30)) == [
        (2025, 3),
        (2025, 4),
        (2026, 1),
        (2026, 2),
    ]


def test_execution_pension_purpose_hints() -> None:
    assert "3/4" in execution_hint(3)
    assert "75" in execution_hint(3)
    assert "_____" in pension_hint([])
    assert "보합" in pension_hint(
        [
            {"stkrt": "5.20"},
            {"stkrt": "5.15"},
        ]
    )
    assert "순증" in pension_hint(
        [
            {"stkrt": "5.40"},
            {"stkrt": "5.00"},
        ]
    )
    assert "30" in purpose_hint("일반", "경영권 영향")
    assert "100" in purpose_hint("약식", "단순투자")
    assert "_____" in purpose_hint("약식", "지분변동")
    assert "_____" in purpose_hint(
        "일반", "단순투자", as_of_year=2026, filing_year=2023
    )


def test_collect_pack_from_injected_json(tmp_path: Path) -> None:
    def fake_get(path: str, params: dict) -> dict:
        del params
        if path == "list.json":
            return {
                "list": [
                    {
                        "report_nm": "현금배당결정",
                        "rcept_dt": "20260515",
                        "rcept_no": "20260515000001",
                    }
                ]
            }
        if path == "majorstock.json":
            return {
                "list": [
                    {
                        "rcept_dt": "20260625",
                        "repror": "국민연금공단",
                        "stkrt": "5.20",
                        "stkrt_irds": "0.20",
                        "report_tp": "일반",
                        "report_resn": "단순투자",
                        "rcept_no": "20260625000001",
                    },
                    {
                        "rcept_dt": "20260330",
                        "repror": "국민연금공단",
                        "stkrt": "5.00",
                        "stkrt_irds": "0.00",
                        "report_tp": "일반",
                        "report_resn": "단순투자",
                        "rcept_no": "20260330000001",
                    },
                ]
            }
        return {"list": []}

    pack = collect_cecs_opendart_pack(
        tmp_path,
        ["005930"],
        as_of=date(2026, 8, 30),
        dart_get_fn=fake_get,
        corp_map={"005930": "00126380"},
    )
    assert pack.ok_count == 1
    assert pack.missing_key is False
    md = "\n".join(pack.markdown_by_ticker["005930"])
    assert "OpenDART" in md
    assert "현금배당결정" in md
    assert "최대주주+특수관계인" in md
    assert "국민연금" in md
    assert "단순투자" in md
    assert "dsaf001" in md
    assert "열지 마세요" in md


def test_missing_key_does_not_scrape(monkeypatch, tmp_path: Path) -> None:
    def boom(data_dir=None):
        raise DartCredentialsError("no key")

    monkeypatch.setattr(
        "src.data_refresh.dart_client.get_dart_api_key", boom
    )
    pack = collect_cecs_opendart_pack(
        tmp_path, ["005930"], as_of=date(2026, 8, 30)
    )
    assert pack.missing_key is True
    assert pack.ok_count == 0
    text = "\n".join(pack.markdown_by_ticker["005930"])
    assert "키 없음" in text
    assert "봇" in text


def test_flags_control_purpose_and_pension_exit() -> None:
    facts = _TickerFacts(
        ticker="005930",
        latest_major={
            "report_tp": "일반",
            "report_resn": "경영권 영향",
            "rcept_no": "20260625000001",
        },
        nps_rows=[
            {"stkrt": "4.80"},
            {"stkrt": "5.20"},
        ],
    )
    flags = flags_from_facts(facts)
    kinds = {f.kind for f in flags}
    assert kinds == {"control_purpose", "pension_exit"}
    assert all(f.source_url.startswith("https://opendart.fss.or.kr/") for f in flags)


def test_flags_no_gate_on_passive_hold() -> None:
    facts = _TickerFacts(
        ticker="005930",
        latest_major={"report_tp": "일반", "report_resn": "단순투자"},
        nps_rows=[{"stkrt": "5.20"}, {"stkrt": "5.00"}],
    )
    assert flags_from_facts(facts) == []


def test_prompt_c_forbids_html_viewers() -> None:
    root = Path(__file__).resolve().parents[1]
    prompt = load_cde_copy_prompt(root, which="C")
    assert "제안 종목" in prompt or "CECS" in prompt
    assert "dsaf001" in prompt or "viewer.do" in prompt
    assert "KIND" in prompt


def test_proposal_watch_skips_payout_and_does_not_fire(tmp_path: Path) -> None:
    from alpha_system.journal import clear_entries, list_entries
    from alpha_system.ui.services.cecs_opendart_pack import (
        load_opendart_watch,
        refresh_opendart_proposal_watch,
        watch_needs_refresh,
    )

    clear_entries()
    called: list[str] = []

    def fake_get(path: str, params: dict) -> dict:
        del params
        called.append(path)
        if path == "list.json":
            raise AssertionError("proposal watch must not call list.json")
        if path == "majorstock.json":
            return {
                "list": [
                    {
                        "rcept_dt": "20260625",
                        "repror": "국민연금공단",
                        "stkrt": "4.80",
                        "stkrt_irds": "-0.40",
                        "report_tp": "일반",
                        "report_resn": "경영권 영향",
                        "rcept_no": "20260625000001",
                    },
                    {
                        "rcept_dt": "20260330",
                        "repror": "국민연금공단",
                        "stkrt": "5.20",
                        "stkrt_irds": "0.00",
                        "report_tp": "일반",
                        "report_resn": "경영권 영향",
                        "rcept_no": "20260330000001",
                    },
                ]
            }
        return {"list": []}

    snap = refresh_opendart_proposal_watch(
        tmp_path,
        ["005930", "000660"],
        as_of=date(2026, 8, 31),
        dart_get_fn=fake_get,
        corp_map={"005930": "00126380", "000660": "00164779"},
        journal_path=tmp_path / "j.jsonl",
    )
    assert "list.json" not in called
    assert snap.flags
    assert all("fired" not in f for f in snap.flags)
    loaded = load_opendart_watch(tmp_path)
    assert loaded is not None
    assert loaded.tickers == ["005930", "000660"]
    assert not watch_needs_refresh(loaded, ["005930", "000660"])
    assert watch_needs_refresh(loaded, ["005930"])
    assert list_entries(action_kind="OPENDART_WATCH")
    overlay = tmp_path / "data" / "qual_rank_overlay.json"
    assert not overlay.exists()
    target = tmp_path / "data" / "target_portfolio.csv"
    assert not target.exists()
    clear_entries()


def test_collect_payout_sr4_sets_quarters_and_buyback(tmp_path: Path) -> None:
    import pandas as pd

    from alpha_system.ui.services.cecs_opendart_pack import (
        apply_payout_sr4,
        collect_payout_sr4,
    )

    def fake_get(path: str, params: dict) -> dict:
        del params
        if path == "list.json":
            return {
                "list": [
                    {
                        "report_nm": "현금배당결정",
                        "rcept_dt": "20260515",
                        "rcept_no": "1",
                    },
                    {
                        "report_nm": "자기주식취득결정",
                        "rcept_dt": "20260310",
                        "rcept_no": "2",
                    },
                ]
            }
        return {"list": []}

    rows = collect_payout_sr4(
        tmp_path,
        ["006040"],
        as_of=date(2026, 8, 30),
        dart_get_fn=fake_get,
        cache_path=tmp_path / "sr4.json",
        corp_map={"006040": "00123456"},
    )
    assert rows["006040"]["quarters_hit"] == 2
    assert rows["006040"]["buyback_3y"] is True
    frame = pd.DataFrame(
        [{"ticker": "006040", "name": "동원산업", "gate_pass": True, "dividend_yield": 2.8}]
    )
    out = apply_payout_sr4(frame, rows)
    assert int(out.loc[0, "execution_quarters_hit"]) == 2
    assert bool(out.loc[0, "buyback_3y"]) is True

    again = collect_payout_sr4(
        tmp_path,
        ["006040"],
        as_of=date(2026, 8, 30),
        dart_get_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("cache miss")),
        cache_path=tmp_path / "sr4.json",
        corp_map={"006040": "00123456"},
    )
    assert again["006040"]["quarters_hit"] == 2


def test_payout_sr4_imports_dart_when_alpha_portfolio_src_is_first() -> None:
    """Quant snapshot puts alpha_portfolio on sys.path[0]; OpenDART lives in repo src."""
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    script = r"""
import sys
import tempfile
from datetime import date
from pathlib import Path
repo = Path(%r)
alpha = repo / "alpha_portfolio"
sys.path[:0] = [str(alpha), str(repo)]
import src  # noqa: F401 — alpha_portfolio src
from alpha_system.ui.services.cecs_opendart_pack import collect_payout_sr4
cache = Path(tempfile.mkdtemp()) / "sr4.json"
rows = collect_payout_sr4(
    repo,
    ["006040"],
    as_of=date(2026, 8, 30),
    dart_get_fn=lambda *_a, **_k: {"list": []},
    cache_path=cache,
    corp_map={"006040": "00123456"},
)
assert "006040" in rows
print("ok")
""" % (str(repo),)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ok" in proc.stdout


