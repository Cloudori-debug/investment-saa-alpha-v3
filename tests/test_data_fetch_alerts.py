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
    (tmp_path / "data" / "local").mkdir(parents=True)
    record_fetch_issues(
        tmp_path,
        where="테스트",
        errors=["KRX 로그인 실패: 비밀번호 변경이 필요합니다."],
    )
    alerts = collect_data_fetch_alerts(tmp_path)
    assert any(a.key == "krx_login" and a.severity == "error" for a in alerts)


def test_ops_journey_wires_alerts() -> None:
    chrome = (
        ROOT / "alpha_system" / "ui" / "services" / "ops_journey_chrome.py"
    ).read_text(encoding="utf-8")
    assert "render_data_fetch_alerts" in chrome
    job = (
        ROOT / "scripts" / "run_dashboard_job.py"
    ).read_text(encoding="utf-8")
    assert "record_from_quant_detail" in job


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
