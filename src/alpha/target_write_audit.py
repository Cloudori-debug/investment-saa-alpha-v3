"""Single entry point for operational target_portfolio.csv writes with audit trail."""
from __future__ import annotations

import contextvars
import inspect
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.alpha.target_portfolio_guard import (
    TargetPortfolioWriteBlockedError,
    _content_hash,
    _load_guard,
    _normalize_ticker,
    _read_csv_rows,
    _save_guard,
    assert_approval_bridge_may_include_tickers,
    clear_blocked_reintroduction,
    count_material_weight_changes,
    evaluate_target_guard,
    find_blocked_reintroduction_violations,
    operational_target_path,
    record_blocked_reintroduction,
    user_target_portfolio_path,
    UNINTENDED_REMOVAL_REASON_MARKER,
)
from src.models import TargetRow

ALLOWED_WRITE_SOURCES: frozenset[str] = frozenset({
    "approval_bridge",
    "restore_from_user_target",
    "manual_admin_override",
})

FORBIDDEN_WRITE_SOURCES: frozenset[str] = frozenset({
    "compass_proposal",
    "generated_targets",
    "report_export",
    "gap_calculation",
    "screener_output",
    "opportunity_engine",
    "hakedaka",
    "daily_report_generation",
    "bundle_export",
    "ui_save_without_approval",
    "write_target_portfolio_approved",
    "unknown",
})

_operational_write_authorized: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_operational_write_authorized", default=False
)


def is_operational_target_file(path: Path) -> bool:
    name = path.name.lower()
    return name == "target_portfolio.csv" and "user_target" not in name


def authorize_operational_write() -> contextvars.Token:
    return _operational_write_authorized.set(True)


def reset_operational_write(token: contextvars.Token) -> None:
    _operational_write_authorized.reset(token)


def operational_write_is_authorized() -> bool:
    return _operational_write_authorized.get()


def target_write_audit_path(output_dir: Path) -> Path:
    return output_dir / "target_write_audit.jsonl"


def proposal_output_dir(output_dir: Path) -> Path:
    return output_dir / "proposals"


def _resolve_writer_module(explicit: str | None) -> str:
    if explicit:
        return explicit
    frame = inspect.stack()[2]
    return f"{frame.filename}:{frame.function}"


def _is_write_allowed(*, source: str, approved_by_user: bool) -> tuple[bool, str]:
    if source in FORBIDDEN_WRITE_SOURCES:
        return False, f"forbidden source: {source}"
    if source not in ALLOWED_WRITE_SOURCES:
        return False, f"unlisted source: {source}"
    if source in {"approval_bridge", "manual_admin_override"} and not approved_by_user:
        return False, f"{source} requires approved_by_user=True"
    return True, ""


@dataclass
class TargetWriteResult:
    success: bool
    blocked: bool
    path: Path | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    guard_after: dict[str, Any] | None = None


def _append_audit_logs(
    output_dir: Path,
    audit: dict[str, Any],
) -> None:
    from src.decision_logger import append_decision_log

    output_dir.mkdir(parents=True, exist_ok=True)
    append_decision_log(output_dir / "decision_log.jsonl", audit)
    audit_path = target_write_audit_path(output_dir)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit, ensure_ascii=False) + "\n")


def apply_blocked_target_write_lock(output_dir: Path, audit: dict[str, Any]) -> None:
    """Lock final_execution_decision when unauthorized target write was attempted."""
    from src.validation.bundle_consistency import apply_target_guard_conflict_lock

    final_path = output_dir / "final_execution_decision.json"
    if not final_path.exists():
        return
    try:
        final_doc = json.loads(final_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    conflict = {
        "conflict_detected": True,
        "guard_fail": True,
        "health_severity": "FAIL",
        "acceptance_severity": "FAIL",
        "final_severity": "FAIL",
    }
    locked = apply_target_guard_conflict_lock(final_doc, conflict)
    locked["target_write_blocked"] = True
    locked["last_blocked_target_write"] = {
        "source": audit.get("target_write_source"),
        "reason": audit.get("target_write_reason"),
        "writer_module": audit.get("writer_module"),
    }
    perms = dict(locked.get("execution_permissions") or {})
    perms["target_write_blocked"] = True
    perms["main_block_reason"] = "unauthorized_target_write_blocked"
    locked["execution_permissions"] = perms
    final_path.write_text(
        json.dumps(locked, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_operational_target(
    data_dir: Path,
    rows: list[TargetRow] | list[dict[str, Any]],
    *,
    source: str,
    reason: str,
    approved_by_user: bool = False,
    writer_module: str = "",
    output_dir: Path | None = None,
    run_id: str | None = None,
    proposal_source_id: str | None = None,
    restore_occurred: bool = False,
    backup: bool = True,
    exclude_tickers: frozenset[str] | None = None,
    sync_user_target: bool = False,
    override_previous_removal: frozenset[str] | None = None,
) -> TargetWriteResult:
    """Single audited entry point for data/target_portfolio.csv writes."""
    from src.data_loader import write_target_portfolio

    out_dir = output_dir or (data_dir.parent / "outputs")
    op_path = operational_target_path(data_dir)
    before_rows = _read_csv_rows(op_path) if op_path.exists() else []
    before_tickers = {
        _normalize_ticker(r.get("ticker", ""))
        for r in before_rows
        if _normalize_ticker(r.get("ticker", ""))
    }
    hash_before = _content_hash(before_rows) if before_rows else ""
    user_hash = (
        _content_hash(_read_csv_rows(user_target_portfolio_path(data_dir)))
        if user_target_portfolio_path(data_dir).exists()
        else ""
    )
    allowed, deny_reason = _is_write_allowed(source=source, approved_by_user=approved_by_user)
    module_name = _resolve_writer_module(writer_module or None)

    from src.validation.bundle_consistency import resolve_pipeline_run_id

    resolved_run_id = run_id or resolve_pipeline_run_id(out_dir)
    if not resolved_run_id and allowed:
        resolved_run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    base_audit: dict[str, Any] = {
        "event": "target_write_audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": resolved_run_id,
        "target_write_source": source,
        "target_write_reason": reason if allowed else deny_reason or reason,
        "target_write_allowed": allowed,
        "writer_module": module_name,
        "approved_by_user": approved_by_user,
        "proposal_source_id": proposal_source_id,
        "target_path": str(op_path),
        "target_hash_before": hash_before,
        "target_hash_after": hash_before,
        "user_target_hash": user_hash,
        "restore_occurred": restore_occurred,
        "no_trade_locked": False,
    }

    if not allowed:
        guard_after = evaluate_target_guard(data_dir, out_dir)
        audit = {
            **base_audit,
            "changed_rows_after_write": guard_after.get("changed_rows", 0),
            "proposal_leak_after_write": guard_after.get("system_proposal_leak_count", 0),
            "material_after_write": guard_after.get("unknown_material_count", 0),
            "guard_result_after_write": guard_after.get("severity", "FAIL"),
            "execution_scope_after_write": "NO_TRADE",
            "no_trade_locked": True,
        }
        _append_audit_logs(out_dir, audit)
        apply_blocked_target_write_lock(out_dir, audit)
        return TargetWriteResult(success=False, blocked=True, audit=audit, guard_after=guard_after)

    typed = [r if isinstance(r, TargetRow) else TargetRow.model_validate(r) for r in rows]
    if exclude_tickers:
        exclude = {str(t).zfill(6) if str(t).isdigit() and len(str(t)) < 6 else str(t) for t in exclude_tickers}
        typed = [r for r in typed if r.ticker not in exclude and r.ticker.zfill(6) not in exclude]
    if not typed:
        raise ValueError("write_operational_target: no rows after filter")

    # Material delta vs pre-write operational file (same basis as _content_hash).
    write_material_change_count = count_material_weight_changes(before_rows, typed)

    if source == "approval_bridge":
        try:
            assert_approval_bridge_may_include_tickers(
                data_dir,
                typed,
                override_previous_removal=override_previous_removal,
            )
        except TargetPortfolioWriteBlockedError as exc:
            guard_after = evaluate_target_guard(data_dir, out_dir)
            audit = {
                **base_audit,
                "target_write_allowed": False,
                "target_write_reason": str(exc),
                "blocked_reintroduction_tickers": find_blocked_reintroduction_violations(
                    data_dir,
                    typed,
                    override_previous_removal=override_previous_removal,
                ),
                "changed_rows_after_write": guard_after.get("changed_rows", 0),
                "proposal_leak_after_write": guard_after.get("system_proposal_leak_count", 0),
                "material_after_write": guard_after.get("unknown_material_count", 0),
                "guard_result_after_write": guard_after.get("severity", "PASS"),
                "execution_scope_after_write": "—",
            }
            _append_audit_logs(out_dir, audit)
            return TargetWriteResult(success=False, blocked=True, audit=audit, guard_after=guard_after)

    if backup and op_path.exists():
        backup_dir = data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = "pre_restore" if source == "restore_from_user_target" else "pre_write"
        shutil.copy2(op_path, backup_dir / f"target_portfolio.{ts}.{suffix}.bak.csv")

    token = authorize_operational_write()
    try:
        write_target_portfolio(typed, op_path)
    finally:
        reset_operational_write(token)

    hash_after = _content_hash(_read_csv_rows(op_path))

    guard = _load_guard(data_dir)
    guard["operational_target_hash"] = hash_after
    guard["last_target_write_source"] = source
    guard["last_target_write_allowed"] = True
    guard["last_target_write_at"] = datetime.now(timezone.utc).isoformat()
    if source == "restore_from_user_target":
        guard["last_restore_at"] = guard["last_target_write_at"]
        guard["restore_reason"] = reason or "restore_from_user_target"
        guard["restored_from"] = user_target_portfolio_path(data_dir).name
        guard.pop("approval_flag", None)
    elif source in {"approval_bridge", "manual_admin_override"}:
        guard["last_approved_write_at"] = guard["last_target_write_at"]
        guard["approved_by"] = module_name
        guard["approval_reason"] = reason
        guard["approval_flag"] = True
    _save_guard(data_dir, guard)

    after_tickers = {_normalize_ticker(r.ticker) for r in typed}
    if (
        source == "manual_admin_override"
        and UNINTENDED_REMOVAL_REASON_MARKER in reason.lower()
    ):
        for ticker in sorted(before_tickers - after_tickers):
            record_blocked_reintroduction(
                data_dir,
                ticker,
                reason=reason,
                source=source,
            )

    if source == "approval_bridge" and override_previous_removal:
        for ticker in override_previous_removal:
            clear_blocked_reintroduction(data_dir, ticker)

    guard = _load_guard(data_dir)

    if sync_user_target or source in {"approval_bridge", "manual_admin_override"}:
        user_path = user_target_portfolio_path(data_dir)
        shutil.copy2(op_path, user_path)
        guard["user_target_hash"] = _content_hash(_read_csv_rows(user_path))
        _save_guard(data_dir, guard)
        user_hash = guard["user_target_hash"]

    guard_after = evaluate_target_guard(data_dir, out_dir)

    # changed_rows_after_write == user↔op guard diff after sync (usually 0).
    # Prefer write_material_change_count for "how many weights this write changed".
    user_op_guard_diff_rows = int(guard_after.get("changed_rows", 0) or 0)

    execution_scope = "NO_TRADE" if guard_after.get("severity") == "FAIL" else "—"
    audit = {
        **base_audit,
        "target_hash_after": hash_after,
        "user_target_hash": user_hash,
        "write_material_change_count": write_material_change_count,
        "changed_rows_after_write": user_op_guard_diff_rows,  # legacy alias: user_op_guard_diff_rows
        "user_op_guard_diff_rows": user_op_guard_diff_rows,
        "proposal_leak_after_write": guard_after.get("system_proposal_leak_count", 0),
        "material_after_write": guard_after.get("unknown_material_count", 0),
        "guard_result_after_write": guard_after.get("severity", "PASS"),
        "execution_scope_after_write": execution_scope,
        "no_trade_locked": guard_after.get("severity") == "FAIL",
    }
    _append_audit_logs(out_dir, audit)

    final_path = out_dir / "final_execution_decision.json"
    if hash_before != hash_after and final_path.exists():
        from src.validation.bundle_consistency import refresh_bundle_after_target_write

        try:
            refresh_bundle_after_target_write(
                data_dir,
                out_dir,
                run_id=resolved_run_id,
                write_audit=audit,
            )
        except Exception as exc:
            from src.validation.bundle_consistency import apply_snapshot_stale_lock, mark_snapshot_stale, write_bundle_consistency_validation

            mark_snapshot_stale(
                out_dir,
                reason=f"bundle refresh failed after target write: {exc}",
                write_audit=audit,
                run_id=resolved_run_id,
            )
            try:
                final_doc = json.loads(final_path.read_text(encoding="utf-8"))
                locked = apply_snapshot_stale_lock(final_doc, {"issues": [str(exc)]})
                final_path.write_text(
                    json.dumps(locked, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except (json.JSONDecodeError, OSError):
                pass
            write_bundle_consistency_validation(out_dir, {
                "pass": False,
                "snapshot_stale": True,
                "issues": [f"bundle refresh failed: {exc}"],
            })

    return TargetWriteResult(
        success=True,
        blocked=False,
        path=op_path,
        audit=audit,
        guard_after=guard_after,
    )


def get_last_target_write_audit(output_dir: Path) -> dict[str, Any]:
    """Most recent target_write_audit event."""
    path = target_write_audit_path(output_dir)
    if not path.exists():
        log_path = output_dir / "decision_log.jsonl"
        if not log_path.exists():
            return {}
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "target_write_audit":
                if ev.get("target_write_allowed") and not ev.get("run_id"):
                    from src.validation.bundle_consistency import resolve_pipeline_run_id

                    rid = resolve_pipeline_run_id(output_dir)
                    if rid:
                        ev = {**ev, "run_id": rid, "run_id_source": "inferred_from_manifest"}
                return ev
        return {}
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("target_write_allowed") and not ev.get("run_id"):
            from src.validation.bundle_consistency import resolve_pipeline_run_id

            rid = resolve_pipeline_run_id(output_dir)
            if rid:
                ev = {**ev, "run_id": rid, "run_id_source": "inferred_from_manifest"}
        return ev
    return {}


def detect_blocked_target_write_in_run(output_dir: Path, run_id: str | None) -> bool:
    """True if this run attempted a blocked operational target write."""
    if not run_id:
        return False
    log_path = output_dir / "decision_log.jsonl"
    if not log_path.exists():
        return False
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") != "target_write_audit":
            continue
        if ev.get("run_id") != run_id:
            continue
        if ev.get("target_write_allowed") is False:
            return True
    return False


def assert_operational_write_allowed(path: Path) -> None:
    if is_operational_target_file(path) and not operational_write_is_authorized():
        raise TargetPortfolioWriteBlockedError(
            "Direct write to operational target_portfolio.csv blocked. "
            "Use write_operational_target() with an allowed source."
        )
