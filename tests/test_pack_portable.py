"""Secret-free portable pack — no network."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = _ROOT / "scripts" / "pack_portable.py"
    spec = importlib.util.spec_from_file_location("pack_portable", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pack_skips_secrets_and_positions(tmp_path: Path) -> None:
    mod = _load()
    src = tmp_path / "src"
    (src / "data" / "local").mkdir(parents=True)
    (src / "alpha_system").mkdir()
    (src / "alpha_dashboard.py").write_text("print(1)\n", encoding="utf-8")
    (src / "data" / "local" / "user_secrets.json").write_text(
        '{"dart_api_key": "SECRET"}\n', encoding="utf-8"
    )
    (src / "data" / "positions.csv").write_text("ticker,qty\n005930,1\n", encoding="utf-8")
    (src / "data" / "universe.csv").write_text("ticker\n005930\n", encoding="utf-8")
    (src / ".env").write_text("DART_API_KEY=SECRET\n", encoding="utf-8")
    dest = tmp_path / "out"
    mod.copy_tree(src, dest)
    assert not (dest / "data" / "local" / "user_secrets.json").exists()
    assert not (dest / "data" / "positions.csv").exists()
    assert not (dest / ".env").exists()
    assert (dest / "data" / "universe.csv").is_file()
    mod.strip_secrets(dest)
    assert (dest / "alpha_dashboard.py").is_file()


def test_pack_skip_python_writes_install_bat(tmp_path: Path) -> None:
    mod = _load()
    src = tmp_path / "app"
    src.mkdir()
    (src / "alpha_dashboard.py").write_text("# x\n", encoding="utf-8")
    dest = tmp_path / "portable"
    mod.pack(src, dest, skip_python=True, zip_out=False)
    assert (dest / "install.bat").is_file()
    bat = (dest / "install.bat").read_text(encoding="ascii")
    assert "LOCALAPPDATA" in bat
    assert "Setup.exe" not in bat
    assert (dest / "PACKAGED.txt").is_file()
    assert "secrets=stripped" in (dest / "PACKAGED.txt").read_text(encoding="utf-8")
    assert "SECRET" not in (dest / "다른PC.txt").read_text(encoding="utf-8")
