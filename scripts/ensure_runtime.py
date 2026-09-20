"""Create or repair a local interpreter so the app runs after a folder copy.

Prefers bundled embeddable Python (runtime/python) over .venv.
Does not write target_portfolio.csv. Safe to call on every UI launch.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def venv_python(root: Path) -> Path:
    return root / ".venv" / "Scripts" / "python.exe"


def embed_python(root: Path) -> Path:
    return root / "runtime" / "python" / "python.exe"


def venv_works(py: Path) -> bool:
    if not py.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(py), "-c", "import streamlit, alpha_system"],
            cwd=str(py.resolve().parents[2]),
            capture_output=True,
            text=True,
            timeout=40,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _base_python() -> list[str]:
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "python.exe" and ".venv" in {p.name.lower() for p in exe.parents}:
        for cmd in (("py", "-3.11"), ("py", "-3"), ("python",)):
            try:
                proc = subprocess.run(
                    [*cmd, "-c", "import sys; print(sys.executable)"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if proc.returncode == 0:
                found = proc.stdout.strip()
                if found and Path(found).is_file() and ".venv" not in found.replace("\\", "/"):
                    return [found]
        return [sys.executable]
    return [sys.executable]


def ensure_runtime(root: Path, *, recreate: bool = False) -> Path:
    root = Path(root).resolve()
    bundled = embed_python(root)
    if not recreate and venv_works(bundled):
        return bundled

    py = venv_python(root)
    if not recreate and venv_works(py):
        return py

    if py.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        broken = root / f".venv.broken_{stamp}"
        if broken.exists():
            shutil.rmtree(broken, ignore_errors=True)
        py.parent.parent.rename(broken)

    venv_dir = root / ".venv"
    base = _base_python()
    print(f"[ensure] creating venv with {base[0]}")
    subprocess.run([*base, "-m", "venv", str(venv_dir)], check=True, cwd=str(root))
    py = venv_python(root)
    if not py.is_file():
        raise RuntimeError("venv python missing after create")

    sitecust = root / "scripts" / "sitecustomize.venv.py"
    dest = venv_dir / "Lib" / "site-packages" / "sitecustomize.py"
    if sitecust.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sitecust, dest)

    print("[ensure] pip install -e .[ui,data] (first time may take a few minutes)")
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=True, cwd=str(root))
    subprocess.run([str(py), "-m", "pip", "install", "-e", ".[ui,data]"], check=True, cwd=str(root))
    if not venv_works(py):
        raise RuntimeError("venv created but streamlit/alpha_system still missing")
    return py


def main() -> int:
    p = argparse.ArgumentParser(description="Ensure local runtime for SAA Alpha")
    p.add_argument("--root", type=Path, default=_ROOT)
    p.add_argument("--recreate", action="store_true")
    args = p.parse_args()
    try:
        py = ensure_runtime(args.root, recreate=bool(args.recreate))
    except Exception as exc:
        print(f"[ensure] FAIL {exc}", file=sys.stderr)
        return 1
    print(f"[ensure] OK {py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
