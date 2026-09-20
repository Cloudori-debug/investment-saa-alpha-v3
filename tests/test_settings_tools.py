from __future__ import annotations

import inspect
from pathlib import Path

from alpha_system.ui.pages import settings


def test_settings_has_tools_tab() -> None:
    src = inspect.getsource(settings)
    assert '_TAB_DISPLAY = "화면"' in src
    assert "render_theme_picker" in src
    assert '_TAB_TOOLS = "도구"' in src
    assert "_render_tools" in src
    assert "장부 폴더 만들기" in src
    assert "saa-alpha-update.zip" in src


def test_settings_required_files_are_ledgers_not_regime() -> None:
    src = inspect.getsource(settings)
    assert '("필수", ("positions.csv", "target_portfolio.csv"))' in src
    required_block = src.split("자격·필수 파일", 1)[-1].split("갱신 경로", 1)[0]
    assert '"market_indicators.csv"' not in required_block


def test_root_keeps_launcher_bats_only() -> None:
    root = Path(__file__).resolve().parents[1]
    leftover = {
        "START_OPS_ASSISTANT.bat",
        "업데이트.bat",
        "장부_내보내기.bat",
        "장부_가져오기.bat",
        "PC이사.bat",
        "폴더를_investment로.bat",
    }
    present = {p.name for p in root.glob("*.bat")}
    assert "투자나침반.bat" in present
    assert "Launch_SAA.bat" in present
    assert not (leftover & present)
    assert (root / "scripts" / "export_ledger.py").is_file()
    assert (root / "scripts" / "폴더를_investment로.bat").is_file()
