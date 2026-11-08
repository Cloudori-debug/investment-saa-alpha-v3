"""데이터 갱신 막힘 화면 알림."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.data_fetch_alerts import (
    collect_data_fetch_alerts,
    record_fetch_issues,
    save_persisted_alerts,
)


ROOT = Path(__file__).resolve().parents[1]


def test_record_and_collect_krx(tmp_path: Path) -> None:
    from alpha_system.ui.services.data_fetch_alerts import action_for_issue

    (tmp_path / "data" / "local").mkdir(parents=True)
    record_fetch_issues(
        tmp_path,
        where="테스트",
        errors=["KRX 로그인 실패: 비밀번호 변경이 필요합니다."],
    )
    alerts = collect_data_fetch_alerts(tmp_path)
    hit = next(a for a in alerts if a.key == "krx_login")
    assert hit.severity == "error"
    assert hit.action_ko
    assert "설정" in hit.action_ko or "KRX" in hit.action_ko
    assert "설정" in action_for_issue("KRX 로그인 실패")


def test_ops_journey_wires_alerts() -> None:
    chrome = (
        ROOT / "alpha_system" / "ui" / "services" / "ops_journey_chrome.py"
    ).read_text(encoding="utf-8")
    assert "render_data_fetch_alerts" in chrome
    job = (
        ROOT / "scripts" / "run_dashboard_job.py"
    ).read_text(encoding="utf-8")
    assert "record_from_quant_detail" in job
    events = (
        ROOT / "alpha_system" / "ui" / "pages" / "events.py"
    ).read_text(encoding="utf-8")
    assert "render_inline_job_progress" in events
    refresh = (
        ROOT / "alpha_system" / "ui" / "services" / "refresh.py"
    ).read_text(encoding="utf-8")
    assert "_job_phase" in refresh


def test_save_roundtrip(tmp_path: Path) -> None:
    from alpha_system.ui.services.data_fetch_alerts import DataFetchAlert

    (tmp_path / "data" / "local").mkdir(parents=True)
    save_persisted_alerts(
        tmp_path,
        [
            DataFetchAlert(
                key="fred",
                severity="warning",
                title="FRED",
                detail="test",
                where="나침반",
            )
        ],
    )
    alerts = collect_data_fetch_alerts(tmp_path)
    assert any(a.key == "fred" for a in alerts)


def test_korea_10y_history_fallback_not_blocker(tmp_path: Path) -> None:
    from alpha_system.ui.services.data_fetch_alerts import record_fetch_issues

    (tmp_path / "data" / "local").mkdir(parents=True)
    record_fetch_issues(
        tmp_path,
        where="나침반·확인①",
        warnings=[
            "korea_10y — PyKRX 실패/범위외, history 유효값 사용",
            "as_of 2026-11-05→2026-11-06 (외부 시장지표)",
        ],
    )
    alerts = collect_data_fetch_alerts(tmp_path)
    assert not any(a.key == "fetch_other" for a in alerts)
    assert not any("korea_10y" in (a.detail or "") for a in alerts)
    assert not any(a.severity == "error" and "korea_10y" in a.detail for a in alerts)
