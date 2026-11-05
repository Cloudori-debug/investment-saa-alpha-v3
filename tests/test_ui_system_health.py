"""대시보드 시스템 점검표 (UI · Soft 신뢰)."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.system_health import collect_system_health


ROOT = Path(__file__).resolve().parents[1]


def test_collect_returns_checks() -> None:
    health = collect_system_health(ROOT)
    assert health.trust in {"trust", "caution", "blocked"}
    assert health.headline
    keys = {c.key for c in health.checks}
    assert "krx_creds" in keys
    assert "quant_kospi" in keys
    assert "market_indicators" in keys
    assert "pension" in keys


def test_ops_journey_wires_health() -> None:
    chrome = (
        ROOT / "alpha_system" / "ui" / "services" / "ops_journey_chrome.py"
    ).read_text(encoding="utf-8")
    assert "render_system_health_strip" in chrome
    settings = (ROOT / "alpha_system" / "ui" / "pages" / "settings.py").read_text(
        encoding="utf-8"
    )
    assert "render_system_health_panel" in settings


def test_blocked_when_pension_error(tmp_path: Path) -> None:
    (tmp_path / "data" / "local").mkdir(parents=True)
    (tmp_path / "data" / "local" / "pension_briefing_last.json").write_text(
        '{"status":"error","message":"KRX 로그인 실패","finished_at":"2026-11-06T08:00:00"}',
        encoding="utf-8",
    )
    health = collect_system_health(tmp_path)
    assert health.fail_n >= 1
    assert health.trust == "blocked"
    assert any(c.key == "pension" and c.status == "fail" for c in health.checks)
