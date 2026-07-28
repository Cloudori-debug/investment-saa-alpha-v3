"""Ops Assistant portable pack — backup/restore for format & other Windows PCs.

Never writes target_portfolio.csv except when restoring a user-made backup zip.
Secrets stay under data/local/ and are optional in the pack (user must opt in).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Relative to repo root. Order is stable for manifests.
OPS_PACK_VERSION = "1.0"
PRODUCT_NAME = "SAA 알파 운용 비서"
PRODUCT_TAGLINE = "규칙 있는 개인 운용 비서 · 자동매매 아님"

# Always include when present (ops state / approvals).
CORE_RELATIVE_PATHS: tuple[str, ...] = (
    "data/target_portfolio.csv",
    "data/kr_alpha_exit_targets.yaml",
    "data/weekly_qual_suggestions.json",
    "data/monthly_cecs_suggestions.json",
    "data/cecs_manual_scoring_template.csv",
    "data/cecs_manual_scoring_candidates.csv",
    "data/positions.csv",
    "data/alpha_dashboard_runtime.json",
    "data/short_bond_regime_guide.yaml",
    "data/portfolio_policy.yaml",
    "data/compass_rules.yaml",
    "data/saa_profiles.yaml",
    "data/trigger_rules.yaml",
)

# Optional market caches — restore speeds first run; can re-fetch.
OPTIONAL_DATA_GLOBS: tuple[str, ...] = (
    "data/prices.csv",
    "data/fundamentals.csv",
    "data/market_indicators.csv",
    "data/macro_tier2.csv",
    "data/kospi_market_pbr_history.csv",
    "alpha_portfolio/data/output/alpha_scores.csv",
)

SECRETS_RELATIVE = "data/local/user_secrets.json"
SETUP_MARKER_RELATIVE = "data/local/ops_assistant_setup.json"


@dataclass(frozen=True)
class PackFile:
    relative: str
    exists: bool
    size_bytes: int


@dataclass(frozen=True)
class PackResult:
    path: Path
    included: tuple[str, ...]
    missing: tuple[str, ...]
    include_secrets: bool
    include_optional_data: bool


def product_identity() -> dict[str, str]:
    return {
        "name": PRODUCT_NAME,
        "tagline": PRODUCT_TAGLINE,
        "pack_version": OPS_PACK_VERSION,
    }


def list_pack_candidates(
    root: Path,
    *,
    include_optional_data: bool = True,
    include_secrets: bool = False,
) -> list[PackFile]:
    root = Path(root)
    rels: list[str] = list(CORE_RELATIVE_PATHS)
    if include_optional_data:
        rels.extend(OPTIONAL_DATA_GLOBS)
    if include_secrets:
        rels.append(SECRETS_RELATIVE)
    out: list[PackFile] = []
    seen: set[str] = set()
    for rel in rels:
        if rel in seen:
            continue
        seen.add(rel)
        path = root / rel
        exists = path.is_file()
        size = int(path.stat().st_size) if exists else 0
        out.append(PackFile(relative=rel, exists=exists, size_bytes=size))
    return out


def create_ops_backup_zip(
    root: Path,
    *,
    dest_dir: Path | None = None,
    include_optional_data: bool = True,
    include_secrets: bool = False,
    generated_at: datetime | None = None,
) -> PackResult:
    """Write a zip the operator can copy to USB / cloud before format."""
    root = Path(root)
    generated_at = generated_at or datetime.now()
    dest_dir = Path(dest_dir) if dest_dir else (root / "data" / "local" / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%d_%H%M%S")
    out_path = dest_dir / f"saa_ops_assistant_backup_{stamp}.zip"

    candidates = list_pack_candidates(
        root,
        include_optional_data=include_optional_data,
        include_secrets=include_secrets,
    )
    included: list[str] = []
    missing: list[str] = []
    for item in candidates:
        if item.exists:
            included.append(item.relative)
        else:
            missing.append(item.relative)

    manifest: dict[str, Any] = {
        "product": PRODUCT_NAME,
        "pack_version": OPS_PACK_VERSION,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "include_secrets": include_secrets,
        "include_optional_data": include_optional_data,
        "included": included,
        "missing": missing,
        "notes": [
            "자동매매 아님. 복원 후에도 DART 키·정량 갱신·주간 승인은 사람 몫.",
            "secrets를 넣었다면 USB를 암호화하고 공유하지 마세요.",
        ],
    }

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "OPS_ASSISTANT_MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        readme = (
            f"{PRODUCT_NAME}\n"
            f"{PRODUCT_TAGLINE}\n\n"
            "복원: 설정 › 이식·백업 탭에서 zip 업로드, 또는\n"
            "  python scripts/restore_ops_backup.py path/to/backup.zip\n"
        )
        zf.writestr("README_RESTORE.txt", readme)
        for rel in included:
            zf.write(root / rel, arcname=rel)

    return PackResult(
        path=out_path,
        included=tuple(included),
        missing=tuple(missing),
        include_secrets=include_secrets,
        include_optional_data=include_optional_data,
    )


def create_ops_backup_folder(
    root: Path,
    *,
    dest_dir: Path | None = None,
    include_optional_data: bool = False,
    include_secrets: bool = False,
    generated_at: datetime | None = None,
) -> PackResult:
    """Export ledger as a portable folder (USB-friendly) + zip twin inside it."""
    import shutil

    root = Path(root)
    generated_at = generated_at or datetime.now()
    stamp = generated_at.strftime("%Y%m%d_%H%M%S")
    base = Path(dest_dir) if dest_dir else (root / "dist" / "CARRY" / "02_SAA-Alpha-Backup")
    folder = base if base.name.startswith("02_") or base.name == "SAA-Alpha-Backup" else (
        base / f"SAA-Alpha-Backup_{stamp}"
    )
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

    zip_result = create_ops_backup_zip(
        root,
        dest_dir=folder,
        include_optional_data=include_optional_data,
        include_secrets=include_secrets,
        generated_at=generated_at,
    )

    # Also unpack core files as a folder tree for drag-drop inspection
    for rel in zip_result.included:
        src = root / rel
        if not src.is_file():
            continue
        dest = folder / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    readme = folder / "README_BACKUP.txt"
    readme.write_text(
        "\n".join(
            [
                f"{PRODUCT_NAME}",
                f"{PRODUCT_TAGLINE}",
                "",
                "This folder = LEDGER backup only (holdings / targets / approvals).",
                "Keep separate from the program (Setup / App folder).",
                "",
                "Restore:",
                "  Run 장부_가져오기.bat and select this folder (or the zip inside).",
                "",
                f"created: {generated_at.isoformat(timespec='seconds')}",
                f"files: {len(zip_result.included)}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return PackResult(
        path=folder,
        included=zip_result.included,
        missing=zip_result.missing,
        include_secrets=include_secrets,
        include_optional_data=include_optional_data,
    )


def restore_ops_backup_zip(
    root: Path,
    zip_path: Path,
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Restore files from a pack zip into root. Does not run scoring."""
    root = Path(root)
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise FileNotFoundError(f"백업 zip 없음: {zip_path}")

    restored: list[str] = []
    skipped: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        for name in sorted(names):
            if name.endswith("/") or name in {
                "OPS_ASSISTANT_MANIFEST.json",
                "README_RESTORE.txt",
            }:
                continue
            if not (
                name.startswith("data/")
                or name.startswith("alpha_portfolio/data/")
            ):
                skipped.append(name)
                continue
            dest = root / name
            if dest.exists() and not overwrite:
                skipped.append(name)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            restored.append(name)

    mark_setup_done(root, source="restore_ops_backup")
    return {"restored": restored, "skipped": skipped, "zip": str(zip_path)}


def restore_ops_backup_folder(
    root: Path,
    folder: Path,
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Restore from an exported backup folder (or find zip inside it)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"백업 폴더 없음: {folder}")

    zips = sorted(folder.glob("saa_ops_assistant_backup_*.zip"), reverse=True)
    if zips:
        return restore_ops_backup_zip(root, zips[0], overwrite=overwrite)

    restored: list[str] = []
    skipped: list[str] = []
    data_src = folder / "data"
    if not data_src.is_dir():
        raise FileNotFoundError(f"백업 zip/data 없음: {folder}")
    for path in data_src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(folder).as_posix()
        dest = root / rel
        if dest.exists() and not overwrite:
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
        restored.append(rel)
    mark_setup_done(root, source="restore_ops_backup_folder")
    return {"restored": restored, "skipped": skipped, "folder": str(folder)}


def restore_ops_backup_any(
    root: Path,
    path: Path,
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Restore from zip file or backup folder."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        return restore_ops_backup_zip(root, path, overwrite=overwrite)
    if path.is_dir():
        return restore_ops_backup_folder(root, path, overwrite=overwrite)
    raise FileNotFoundError(f"백업 경로를 찾을 수 없음: {path}")


def setup_status(root: Path) -> dict[str, Any]:
    """First-run checklist for the ops assistant product surface."""
    from src.settings.user_secrets import credential_status

    root = Path(root)
    data = root / "data"
    creds = credential_status(data)
    marker = root / SETUP_MARKER_RELATIVE
    core = list_pack_candidates(root, include_optional_data=False, include_secrets=False)
    core_missing = [c.relative for c in core if not c.exists]
    return {
        "product": PRODUCT_NAME,
        "setup_done": marker.is_file(),
        "dart_ok": bool(creds.get("dart")),
        "krx_ok": bool(creds.get("krx")),
        "core_missing": core_missing,
        "target_exists": (data / "target_portfolio.csv").is_file(),
        "exit_targets_exists": (data / "kr_alpha_exit_targets.yaml").is_file(),
    }


def mark_setup_done(root: Path, *, source: str = "ui") -> Path:
    path = Path(root) / SETUP_MARKER_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "product": PRODUCT_NAME,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "pack_version": OPS_PACK_VERSION,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def needs_first_run_banner(root: Path) -> bool:
    status = setup_status(root)
    if status["setup_done"]:
        return False
    return not status["dart_ok"] or not status["target_exists"]


__all__ = [
    "OPS_PACK_VERSION",
    "PRODUCT_NAME",
    "PRODUCT_TAGLINE",
    "CORE_RELATIVE_PATHS",
    "PackFile",
    "PackResult",
    "product_identity",
    "list_pack_candidates",
    "create_ops_backup_zip",
    "create_ops_backup_folder",
    "restore_ops_backup_zip",
    "restore_ops_backup_folder",
    "restore_ops_backup_any",
    "setup_status",
    "mark_setup_done",
    "needs_first_run_banner",
]
