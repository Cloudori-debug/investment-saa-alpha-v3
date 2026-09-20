"""Local venv repair helper — no network, no recreate on the live tree."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = _ROOT / "scripts" / "ensure_runtime.py"
    spec = importlib.util.spec_from_file_location("ensure_runtime", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_venv_works_false_when_missing(tmp_path: Path) -> None:
    mod = _load()
    assert mod.venv_works(tmp_path / ".venv" / "Scripts" / "python.exe") is False


def test_venv_python_path(tmp_path: Path) -> None:
    mod = _load()
    assert mod.venv_python(tmp_path) == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert mod.embed_python(tmp_path) == tmp_path / "runtime" / "python" / "python.exe"
