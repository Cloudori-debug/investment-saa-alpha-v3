"""Background dashboard jobs — status file + cancel, no pause."""

from __future__ import annotations

from pathlib import Path

from alpha_system.journal import clear_entries
from alpha_system.ui.services.background_job import (
    KIND_QUANT,
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_RUNNING,
    JobStatus,
    job_is_busy,
    load_job,
    reap_job,
    request_cancel,
    save_job,
    start_dashboard_job,
)


def test_reap_marks_dead_pid_failed(tmp_path: Path, monkeypatch) -> None:
    clear_entries()
    job = JobStatus(
        kind=KIND_QUANT,
        label="정량 전체 갱신",
        state=STATE_RUNNING,
        pid=999999,
        started_at="2026-08-28T12:00:00+00:00",
        phase="수집",
    )
    save_job(tmp_path, job)
    monkeypatch.setattr(
        "alpha_system.ui.services.background_job.pid_alive",
        lambda pid: False,
    )
    out = reap_job(tmp_path)
    assert out is not None
    assert out.state == STATE_FAILED
    assert out.ok is False
    assert job_is_busy(tmp_path) is False


def test_reap_honours_cancel_flag(tmp_path: Path, monkeypatch) -> None:
    clear_entries()
    job = JobStatus(
        kind=KIND_QUANT,
        label="정량 전체 갱신",
        state=STATE_RUNNING,
        pid=999999,
        cancel_requested=True,
        started_at="2026-08-28T12:00:00+00:00",
    )
    save_job(tmp_path, job)
    monkeypatch.setattr(
        "alpha_system.ui.services.background_job.pid_alive",
        lambda pid: False,
    )
    out = reap_job(tmp_path)
    assert out is not None
    assert out.state == STATE_CANCELLED


def test_start_rejects_second_job(tmp_path: Path, monkeypatch) -> None:
    clear_entries()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_dashboard_job.py").write_text("#", encoding="utf-8")
    save_job(
        tmp_path,
        JobStatus(
            kind=KIND_QUANT,
            label="정량 전체 갱신",
            state=STATE_RUNNING,
            pid=4242,
            started_at="2026-08-28T12:00:00+00:00",
        ),
    )
    monkeypatch.setattr(
        "alpha_system.ui.services.background_job.pid_alive",
        lambda pid: True,
    )
    err = start_dashboard_job(tmp_path, "quant")
    assert err is not None
    assert "이미 실행 중" in err


def test_start_records_pid(tmp_path: Path, monkeypatch) -> None:
    clear_entries()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_dashboard_job.py").write_text("#", encoding="utf-8")
    monkeypatch.setattr(
        "alpha_system.ui.services.proposal_freeze.is_freeze_active",
        lambda root: False,
    )

    class _Proc:
        pid = 4242

    monkeypatch.setattr(
        "alpha_system.ui.services.background_job.subprocess.Popen",
        lambda *args, **kwargs: _Proc(),
    )
    err = start_dashboard_job(tmp_path, "quant")
    assert err is None
    job = load_job(tmp_path)
    assert job is not None
    assert job.pid == 4242
    assert job.state == STATE_RUNNING
    assert job.kind == KIND_QUANT


def test_request_cancel_sets_flag(tmp_path: Path, monkeypatch) -> None:
    clear_entries()
    save_job(
        tmp_path,
        JobStatus(
            kind=KIND_QUANT,
            label="정량 전체 갱신",
            state=STATE_RUNNING,
            pid=4242,
            started_at="2026-08-28T12:00:00+00:00",
        ),
    )
    killed: list[int] = []
    monkeypatch.setattr(
        "alpha_system.ui.services.background_job._kill_pid",
        lambda pid: killed.append(pid),
    )
    err = request_cancel(tmp_path)
    assert err is None
    job = load_job(tmp_path)
    assert job is not None
    assert job.cancel_requested is True
    assert killed == [4242]
