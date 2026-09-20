"""Dashboard long jobs as a subprocess so the UI can navigate while they run.

Pause/resume is not supported: PyKRX·DART and src.main have no cooperative
checkpoints. Cancel kills the process tree; restart from the same button.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from typing import Any, Mapping, Optional


JOB_REL = Path("data") / "local" / "alpha_job.json"

KIND_QUANT = "quant"
KIND_COMPASS = "compass"

_LABELS = {
    KIND_QUANT: "정량 갱신",
    KIND_COMPASS: "나침반·레짐 분석",
}
_TYPICAL_SEC = {
    KIND_QUANT: 900,
    KIND_COMPASS: 900,
}

STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


@dataclass
class JobStatus:
    kind: str
    label: str
    state: str
    pid: int = 0
    started_at: str = ""
    updated_at: str = ""
    ended_at: str = ""
    phase: str = ""
    message: str = ""
    typical_sec: int = 600
    ok: Optional[bool] = None
    cancel_requested: bool = False
    journaled: bool = False
    collect_scope: str = "liquid"
    run_mode: str = "standard"
    market: str = "KOSPI"
    detail: dict[str, Any] | None = None

    @property
    def busy(self) -> bool:
        return self.state == STATE_RUNNING


def job_path(root: Path) -> Path:
    return Path(root) / JOB_REL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def elapsed_sec(job: JobStatus) -> int:
    start = _parse_iso(job.started_at)
    if start is None:
        return 0
    end = _parse_iso(job.ended_at) or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds()))


def progress_fraction(job: JobStatus) -> float:
    if job.state != STATE_RUNNING:
        return 1.0 if job.ok else 0.0
    typical = max(30, int(job.typical_sec or 600))
    return min(0.95, elapsed_sec(job) / typical)


def ended_age_sec(job: JobStatus) -> int:
    end = _parse_iso(job.ended_at)
    if end is None:
        return 0
    now = datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((now - end).total_seconds()))


def pid_alive(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    pid = int(pid)
    if sys.platform == "win32":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def load_job(root: Path) -> Optional[JobStatus]:
    path = job_path(root)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    known = {f.name for f in JobStatus.__dataclass_fields__.values()}
    payload = {k: v for k, v in raw.items() if k in known}
    try:
        return JobStatus(**payload)
    except TypeError:
        return None


def save_job(root: Path, job: JobStatus) -> None:
    path = job_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    job.updated_at = _now_iso()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(asdict(job), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def job_is_busy(root: Path) -> bool:
    job = reap_job(root)
    return bool(job and job.busy)


def reap_job(root: Path) -> Optional[JobStatus]:
    """If the worker died without writing a terminal state, close the record."""
    job = load_job(root)
    if job is None or not job.busy:
        return job
    if pid_alive(job.pid):
        return job
    job.ended_at = job.ended_at or _now_iso()
    if job.cancel_requested:
        job.state = STATE_CANCELLED
        job.ok = False
        job.message = job.message or "중단됨"
        job.phase = "중단"
    else:
        job.state = STATE_FAILED
        job.ok = False
        job.message = job.message or "프로세스가 예기치 않게 종료되었습니다."
        job.phase = "실패"
    save_job(root, job)
    _journal_if_needed(root, job)
    return job


def _journal_if_needed(root: Path, job: JobStatus) -> None:
    if job.journaled or job.state == STATE_RUNNING:
        return
    try:
        from alpha_system.journal.recorder import configure_journal_path
        from alpha_system.ui.services.auto_journal import journal_data_refresh

        configure_journal_path(Path(root) / "data" / "alpha_system_journal.jsonl")
        as_of = datetime.now(timezone.utc).date()
        journal_data_refresh(
            as_of=as_of,
            ok=bool(job.ok),
            message=job.message or job.label,
            detail={
                "kind": job.kind,
                "state": job.state,
                "phase": job.phase,
                "detail": job.detail or {},
            },
        )
        job.journaled = True
        save_job(root, job)
    except Exception:
        pass


def start_dashboard_job(
    root: Path,
    kind: str,
    *,
    collect_scope: str = "liquid",
    run_mode: str = "standard",
    market: str = "KOSPI",
) -> Optional[str]:
    """Launch worker. Returns an error string, or None if started."""
    kind = (kind or "").strip().lower()
    if kind not in {KIND_QUANT, KIND_COMPASS}:
        return "알 수 없는 작업입니다."
    if kind == KIND_QUANT:
        from alpha_system.ui.services.proposal_freeze import (
            block_message,
            is_freeze_active,
        )

        if is_freeze_active(root):
            return block_message(root=root)

    current = reap_job(root)
    if current is not None and current.busy:
        return f"이미 실행 중: {current.label}"

    script = Path(root) / "scripts" / "run_dashboard_job.py"
    if not script.exists():
        return "scripts/run_dashboard_job.py 가 없습니다."

    from alpha_system.screen_book import market_label, normalize_market

    book = normalize_market(market)
    label = _LABELS[kind]
    if kind == KIND_QUANT:
        label = f"{market_label(book)} 정량 갱신"

    job = JobStatus(
        kind=kind,
        label=label,
        state=STATE_RUNNING,
        started_at=_now_iso(),
        phase="시작",
        typical_sec=_TYPICAL_SEC[kind],
        collect_scope=collect_scope,
        run_mode=run_mode,
        market=book,
    )
    save_job(root, job)

    env = os.environ.copy()
    py_path = os.pathsep.join(
        [str(root), str(Path(root) / "src"), env.get("PYTHONPATH", "")]
    )
    env["PYTHONPATH"] = py_path
    env["PYTHONUNBUFFERED"] = "1"
    env["ALPHA_JOB_ROOT"] = str(root)

    cmd = [
        sys.executable,
        str(script),
        "--root",
        str(root),
        "--kind",
        kind,
        "--collect-scope",
        collect_scope,
        "--run-mode",
        run_mode,
        "--market",
        book,
    ]
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except OSError as exc:
        job.state = STATE_FAILED
        job.ok = False
        job.message = f"실행 실패: {exc}"
        job.ended_at = _now_iso()
        save_job(root, job)
        return job.message

    job.pid = int(proc.pid)
    save_job(root, job)
    return None


def request_cancel(root: Path) -> Optional[str]:
    job = load_job(root)
    if job is None or not job.busy:
        return "실행 중인 작업이 없습니다."
    job.cancel_requested = True
    job.phase = "중단 요청"
    save_job(root, job)
    _kill_pid(job.pid)
    return None


def _kill_pid(pid: int) -> None:
    pid = int(pid or 0)
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def apply_worker_result(
    root: Path,
    *,
    ok: bool,
    message: str,
    phase: str,
    detail: Mapping[str, Any] | None = None,
) -> None:
    job = load_job(root) or JobStatus(
        kind=KIND_QUANT,
        label=_LABELS[KIND_QUANT],
        state=STATE_RUNNING,
    )
    job.ok = bool(ok)
    job.message = message
    job.phase = phase
    job.detail = dict(detail or {})
    job.ended_at = _now_iso()
    if job.cancel_requested and not ok:
        job.state = STATE_CANCELLED
    else:
        job.state = STATE_DONE if ok else STATE_FAILED
    save_job(root, job)
    _journal_if_needed(root, job)


def update_phase(root: Path, phase: str) -> None:
    job = load_job(root)
    if job is None:
        return
    job.phase = phase
    save_job(root, job)
