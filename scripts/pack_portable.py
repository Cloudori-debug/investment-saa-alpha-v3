"""Build a secret-free portable folder for another Windows PC.

Does not copy API keys, positions, or runtime go-live state.
Uses official embeddable CPython (signed python.exe) so the other PC
does not need a Python installer. Launchers are .bat/.vbs — no unsigned Setup.exe.

  python scripts/pack_portable.py
  python scripts/pack_portable.py --skip-python   # tree only (tests / dry run)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

EMBED_VERSION = "3.13.7"
EMBED_URL = (
    f"https://www.python.org/ftp/python/{EMBED_VERSION}/"
    f"python-{EMBED_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    ".cursor",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "archive",
    "outputs",
    "htmlcov",
    "agent-transcripts",
    "cache",
    "local",
    "backups",
    "quarantine",
}
SKIP_DIR_REL = {
    Path("docs") / "archive",
    Path("alpha_system") / "config" / "backups",
    Path("Claude outputs"),
}
SECRET_FILE_NAMES = {
    "user_secrets.json",
    ".env",
    "credentials.json",
    "secrets.yaml",
}
PERSONAL_REL = {
    Path("data") / "positions.csv",
    Path("data") / "alpha_dashboard_runtime.json",
    Path("data") / "books" / "kosdaq" / "positions.csv",
    Path("data") / "books" / "kosdaq" / "alpha_dashboard_runtime.json",
}
SKIP_FILE_SUFFIXES = {".pyc", ".pyo", ".pem", ".key"}
SKIP_FILE_NAMES = {".coverage"}


def _rel(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def should_skip_dir(path: Path, root: Path) -> bool:
    if path.name in SKIP_DIR_NAMES:
        return True
    rel = _rel(path, root)
    return rel in SKIP_DIR_REL or any(rel == p or p in rel.parents for p in SKIP_DIR_REL)


def should_skip_file(path: Path, root: Path) -> bool:
    name = path.name
    if name in SECRET_FILE_NAMES:
        return True
    if name.startswith(".env."):
        return True
    if name.lower() == "positions.csv":
        return True
    if path.suffix.lower() in SKIP_FILE_SUFFIXES:
        return True
    if name in SKIP_FILE_NAMES:
        return True
    rel = _rel(path, root)
    if rel in PERSONAL_REL:
        return True
    if "prices_history" in name and name.endswith(".csv"):
        return True
    return False


def copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(src):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not should_skip_dir(current / d, src)]
        rel_dir = _rel(current, src)
        target_dir = dest if rel_dir == Path(".") else dest / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            file_path = current / name
            if should_skip_file(file_path, src):
                continue
            shutil.copy2(file_path, target_dir / name)


def strip_secrets(dest: Path) -> list[str]:
    """Delete leftover secrets/personal files if any slipped through."""
    removed: list[str] = []
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name in {n.lower() for n in SECRET_FILE_NAMES} or name.startswith(".env."):
            path.unlink()
            removed.append(str(path.relative_to(dest)))
            continue
        rel = path.relative_to(dest)
        if name == "positions.csv" or rel in PERSONAL_REL:
            path.unlink()
            removed.append(str(rel))
    local = dest / "data" / "local"
    if local.exists():
        shutil.rmtree(local, ignore_errors=True)
        removed.append("data/local")
    (dest / "data" / "local" / "backups").mkdir(parents=True, exist_ok=True)
    return removed


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "SAA-alpha-pack/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def install_embed_python(dest: Path, *, cache_dir: Path) -> Path:
    py_dir = dest / "runtime" / "python"
    if py_dir.exists():
        shutil.rmtree(py_dir)
    py_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / f"python-{EMBED_VERSION}-embed-amd64.zip"
    if not zip_path.is_file():
        print(f"[pack] download {EMBED_URL}")
        _download(EMBED_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(py_dir)

    pth = next(py_dir.glob("python*._pth"), None)
    if pth is None:
        raise RuntimeError("embed python*._pth missing")
    zip_name = next((p.name for p in py_dir.glob("python*.zip")), "python313.zip")
    pth.write_text(
        f"{zip_name}\n.\nLib\\site-packages\n..\\..\nimport site\n",
        encoding="ascii",
    )

    site = py_dir / "Lib" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    get_pip = cache_dir / "get-pip.py"
    if not get_pip.is_file():
        print(f"[pack] download {GET_PIP_URL}")
        _download(GET_PIP_URL, get_pip)
    py = py_dir / "python.exe"
    subprocess.run([str(py), str(get_pip), "--no-warn-script-location"], check=True, cwd=str(py_dir))
    print("[pack] pip install ui+data deps into embed python")
    subprocess.run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-warn-script-location",
            "pandas==2.3.3",
            "pydantic==2.13.3",
            "pyyaml==6.0.3",
            "streamlit==1.56.0",
            "pykrx==1.2.7",
        ],
        check=True,
        cwd=str(dest),
    )
    sitecust = dest / "scripts" / "sitecustomize.venv.py"
    if sitecust.is_file():
        shutil.copy2(sitecust, site / "sitecustomize.py")
    return py


def write_markers(dest: Path, *, stripped: list[str]) -> None:
    (dest / "PACKAGED.txt").write_text(
        "Alpha Screener portable\n"
        "secrets=stripped\n"
        f"python=embed-{EMBED_VERSION}\n"
        "launcher=Launch_SAA.bat\n",
        encoding="ascii",
    )
    guide = dest / "다른PC.txt"
    guide.write_text(
        "알파 스크리너 — 다른 Windows PC\n"
        "\n"
        "1) 이 폴더 전체를 USB로 복사하거나 zip을 풉니다.\n"
        "   (인터넷에서 받은 zip이면 속성에서 '차단 해제'를 켜세요.)\n"
        "2) install.bat 을 실행하면 시작 메뉴 바로가기가 생깁니다.\n"
        "   바로 쓰려면 Launch_SAA.bat 만 눌러도 됩니다. Python 설치 불필요.\n"
        "3) 설정에서 DART·KRX 키를 이 PC에만 입력합니다. 패키지에 키는 없습니다.\n"
        "4) 확인 › ③ 가동에서 한 번 선언한 뒤, ①에서 정량을 돌립니다.\n"
        "\n"
        "미서명 Setup.exe는 쓰지 않습니다 (SmartScreen).\n"
        "제거된 민감/개인 파일:\n  "
        + ("\n  ".join(stripped) if stripped else "(없음)")
        + "\n",
        encoding="utf-8",
    )


def write_install_bat(dest: Path) -> None:
    text = r"""@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "DEST=%LOCALAPPDATA%\AlphaScreener"
echo [SAA] install to %DEST%
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%~dp0." "%DEST%" /E /XD runtime\python\__pycache__ /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 (
  echo [ERROR] copy failed
  pause
  exit /b 1
)
set "BAT=%DEST%\Launch_SAA.bat"
set "MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
if not exist "%MENU%" mkdir "%MENU%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=New-Object -ComObject WScript.Shell; $p=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Alpha Screener.lnk'; $c=$s.CreateShortcut($p); $c.TargetPath='cmd.exe'; $c.Arguments='/c ""' + $env:LOCALAPPDATA + '\AlphaScreener\Launch_SAA.bat""'; $c.WorkingDirectory=Join-Path $env:LOCALAPPDATA 'AlphaScreener'; $c.WindowStyle=7; $c.Save()"
echo [SAA] Start Menu: Alpha Screener
echo [SAA] Run Launch_SAA.bat in %DEST%
pause
"""
    (dest / "install.bat").write_text(text.replace("\n", "\r\n"), encoding="ascii")


def pack(
    root: Path,
    dest: Path,
    *,
    skip_python: bool = False,
    zip_out: bool = False,
) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    print(f"[pack] copy {root} -> {dest}")
    copy_tree(root, dest)
    stripped = strip_secrets(dest)
    write_install_bat(dest)
    if not skip_python:
        cache = root / "dist" / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        py = install_embed_python(dest, cache_dir=cache)
        print(f"[pack] python {py}")
    write_markers(dest, stripped=stripped)
    if zip_out:
        zip_path = dest.parent / f"{dest.name}.zip"
        if zip_path.exists():
            zip_path.unlink()
        print(f"[pack] zip {zip_path}")
        shutil.make_archive(str(zip_path.with_suffix("")), "zip", dest)
        return zip_path
    return dest


def main() -> int:
    p = argparse.ArgumentParser(description="Secret-free portable pack")
    p.add_argument("--root", type=Path, default=_ROOT)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--skip-python", action="store_true")
    p.add_argument("--zip", dest="make_zip", action="store_true")
    args = p.parse_args()
    root = args.root.resolve()
    dest = (args.out or (root / "dist" / "AlphaScreener-portable")).resolve()
    try:
        pack(root, dest, skip_python=bool(args.skip_python), zip_out=bool(args.make_zip))
    except Exception as exc:
        print(f"[pack] FAIL {exc}", file=sys.stderr)
        return 1
    print(f"[pack] OK {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
