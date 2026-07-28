"""Guard user-confirmed target_portfolio.csv from unapproved system proposal leaks."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

GuardReason = Literal[
    "formatting_only",
    "approved_change",
    "bootstrap_initialization",
    "ticker_resolution_change",
    "system_proposal_leak",
    "unknown",
    "unknown_material",
]
GuardSeverity = Literal["PASS", "WARN", "FAIL"]

REASON_VALUES: frozenset[str] = frozenset({
    "formatting_only",
    "approved_change",
    "bootstrap_initialization",
    "ticker_resolution_change",
    "system_proposal_leak",
    "unknown",
    "unknown_material",
})

SEVERITY_BY_REASON: dict[str, GuardSeverity] = {
    "formatting_only": "PASS",
    "approved_change": "PASS",
    "bootstrap_initialization": "WARN",
    "ticker_resolution_change": "WARN",
    "unknown": "WARN",
    "unknown_material": "FAIL",
    "system_proposal_leak": "FAIL",
}

FAIL_REASONS: frozenset[str] = frozenset({"system_proposal_leak", "unknown_material"})
WARN_REASONS: frozenset[str] = frozenset({
    "bootstrap_initialization",
    "ticker_resolution_change",
    "unknown",
})

WEIGHT_EPS = 0.01
FORMAT_WEIGHT_EPS = 0.001
PROPOSAL_MATCH_EPS = 0.05

RECOVERY_GUIDE_KO = (
    "승인되지 않은 target 변경이 감지되었습니다. user_target_portfolio.csv 또는 "
    "마지막 승인 baseline으로 target_portfolio.csv를 복구하거나, 사용자가 명시 승인한 경우에만 "
    "--approve-target으로 baseline을 갱신하십시오."
)


class TargetPortfolioWriteBlockedError(RuntimeError):
    """Raised when writing target_portfolio.csv without explicit approval."""


def operational_target_path(data_dir: Path) -> Path:
    return data_dir / "target_portfolio.csv"


def user_target_portfolio_path(data_dir: Path) -> Path:
    return data_dir / "user_target_portfolio.csv"


def guard_state_path(data_dir: Path) -> Path:
    return data_dir / "target_portfolio_write_guard.json"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _float_weight(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker or "").strip()
    if t.isdigit() and len(t) < 6:
        return t.zfill(6)
    return t


def _row_weight(row: dict[str, str] | None) -> float:
    if not row:
        return 0.0
    return _float_weight(row.get("target_weight"))


def _content_hash(rows: list[dict[str, str]]) -> str:
    """Ticker + target_weight canonical hash (formatting-insensitive)."""
    canonical = sorted(
        {
            (
                _normalize_ticker(r.get("ticker", "")),
                round(_row_weight(r), 4),
            )
            for r in rows
            if _normalize_ticker(r.get("ticker", ""))
        }
    )
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def count_material_weight_changes(
    before_rows: list[dict[str, str]] | list[Any],
    after_rows: list[dict[str, str]] | list[Any],
) -> int:
    """Count tickers whose rounded target_weight differs (same basis as _content_hash)."""

    def _map(rows: list[Any]) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in rows:
            if hasattr(r, "ticker"):
                tk = _normalize_ticker(getattr(r, "ticker", ""))
                w = round(float(getattr(r, "target_weight", 0) or 0), 4)
            else:
                tk = _normalize_ticker((r or {}).get("ticker", ""))
                w = round(_row_weight(r or {}), 4)
            if tk:
                out[tk] = w
        return out

    before = _map(before_rows)
    after = _map(after_rows)
    return sum(1 for t in set(before) | set(after) if before.get(t) != after.get(t))


def _load_guard(data_dir: Path) -> dict[str, Any]:
    path = guard_state_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_guard(data_dir: Path, guard: dict[str, Any]) -> None:
    guard_state_path(data_dir).write_text(
        json.dumps(guard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


UNINTENDED_REMOVAL_REASON_MARKER = "unintended"


def get_blocked_reintroductions(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Tickers manually removed as unintended — approval_bridge may not re-add without override."""
    return dict(_load_guard(data_dir).get("blocked_reintroductions") or {})


def record_blocked_reintroduction(
    data_dir: Path,
    ticker: str,
    *,
    reason: str,
    source: str,
) -> None:
    guard = _load_guard(data_dir)
    blocked = dict(guard.get("blocked_reintroductions") or {})
    norm = _normalize_ticker(ticker)
    blocked[norm] = {
        "ticker": norm,
        "reason": reason,
        "source": source,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    guard["blocked_reintroductions"] = blocked
    _save_guard(data_dir, guard)


def clear_blocked_reintroduction(data_dir: Path, ticker: str) -> None:
    guard = _load_guard(data_dir)
    blocked = dict(guard.get("blocked_reintroductions") or {})
    blocked.pop(_normalize_ticker(ticker), None)
    guard["blocked_reintroductions"] = blocked
    _save_guard(data_dir, guard)


def _row_ticker_and_weight(row: Any) -> tuple[str, float]:
    if hasattr(row, "ticker"):
        return _normalize_ticker(row.ticker), float(getattr(row, "target_weight", 0) or 0)
    if isinstance(row, dict):
        return _normalize_ticker(row.get("ticker", "")), _float_weight(row.get("target_weight"))
    return "", 0.0


def blocked_reintroduction_exclusion_warning(ticker: str, *, reason: str = "unintended removal") -> str:
    return (
        f"{ticker}: 수동 제거·재편입 금지 — proposal/draft에서 제외 "
        f"(override_previous_removal 필요 · {reason})"
    )


def filter_blocked_reintroduction_rows(
    data_dir: Path,
    rows: list[Any],
) -> tuple[list[Any], list[str]]:
    """Drop blocked tickers with positive weight before approval_bridge write."""
    blocked = get_blocked_reintroductions(data_dir)
    if not blocked:
        return rows, []
    kept: list[Any] = []
    warnings: list[str] = []
    for row in rows:
        ticker, weight = _row_ticker_and_weight(row)
        if ticker in blocked and weight > 0:
            reason = str(blocked[ticker].get("reason") or "unintended removal")
            warnings.append(blocked_reintroduction_exclusion_warning(ticker, reason=reason))
            continue
        kept.append(row)
    return kept, warnings


def find_blocked_reintroduction_violations(
    data_dir: Path,
    rows: list[Any],
    *,
    override_previous_removal: frozenset[str] | None = None,
) -> list[str]:
    blocked = get_blocked_reintroductions(data_dir)
    if not blocked:
        return []
    override = {_normalize_ticker(t) for t in (override_previous_removal or frozenset())}
    violations: list[str] = []
    for row in rows:
        ticker, weight = _row_ticker_and_weight(row)
        if not ticker or weight <= 0:
            continue
        if ticker in blocked and ticker not in override:
            violations.append(ticker)
    return violations


def assert_approval_bridge_may_include_tickers(
    data_dir: Path,
    rows: list[Any],
    *,
    override_previous_removal: frozenset[str] | None = None,
) -> None:
    violations = find_blocked_reintroduction_violations(
        data_dir,
        rows,
        override_previous_removal=override_previous_removal,
    )
    if not violations:
        return
    blocked = get_blocked_reintroductions(data_dir)
    details = [
        f"{ticker} ({blocked.get(ticker, {}).get('reason', 'unintended removal')})"
        for ticker in violations
    ]
    raise TargetPortfolioWriteBlockedError(
        "approval_bridge blocked: manually removed unintended ticker(s) cannot be re-added "
        f"without override_previous_removal — {', '.join(details)}"
    )

def _load_proposal_map(data_dir: Path, output_dir: Path | None) -> dict[str, dict[str, str]]:
    candidates: list[Path] = []
    if output_dir is not None:
        candidates.extend([
            output_dir / "proposals" / "target_portfolio_proposal.csv",
            output_dir / "target_portfolio_proposal.csv",
        ])
    candidates.extend([
        data_dir.parent / "outputs" / "proposals" / "target_portfolio_proposal.csv",
        data_dir.parent / "outputs" / "target_portfolio_proposal.csv",
        data_dir / "target_portfolio_proposal.csv",
    ])
    for path in candidates:
        if path.exists():
            return {
                _normalize_ticker(r.get("ticker", "")): r
                for r in _read_csv_rows(path)
                if _normalize_ticker(r.get("ticker", ""))
            }
    return {}


def _proposal_weight_match(
    operational_weight: float,
    proposal_row: dict[str, str] | None,
    *,
    eps: float = PROPOSAL_MATCH_EPS,
) -> bool:
    if not proposal_row:
        return False
    return abs(operational_weight - _row_weight(proposal_row)) <= eps


def _material_fields_differ(
    user_row: dict[str, str] | None,
    op_row: dict[str, str] | None,
) -> bool:
    if user_row is None or op_row is None:
        return True
    if abs(_row_weight(user_row) - _row_weight(op_row)) > FORMAT_WEIGHT_EPS:
        return True
    for field in ("name", "asset_group", "sector", "role"):
        u = str(user_row.get(field) or "").strip()
        o = str(op_row.get(field) or "").strip()
        if u and o and u != o:
            return True
    return False


def _is_formatting_only_row(
    user_row: dict[str, str] | None,
    op_row: dict[str, str] | None,
) -> bool:
    if user_row is None or op_row is None:
        return False
    return abs(_row_weight(user_row) - _row_weight(op_row)) <= FORMAT_WEIGHT_EPS


def _is_ticker_resolution_only(
    user_row: dict[str, str] | None,
    op_row: dict[str, str] | None,
) -> bool:
    if user_row is None or op_row is None:
        return False
    if abs(_row_weight(user_row) - _row_weight(op_row)) > FORMAT_WEIGHT_EPS:
        return False
    return _material_fields_differ(user_row, op_row)


def _is_system_proposal_leak(
    *,
    change_type: str,
    ticker: str,
    user_row: dict[str, str] | None,
    op_row: dict[str, str] | None,
    proposal_map: dict[str, dict[str, str]],
    approval_flag: bool,
) -> bool:
    if approval_flag:
        return False
    tk = _normalize_ticker(ticker)
    proposal = proposal_map.get(tk)
    op_weight = _row_weight(op_row)
    user_weight = _row_weight(user_row)

    if change_type == "added" and user_row is None and op_row is not None:
        if proposal is not None:
            return True
        if _proposal_weight_match(op_weight, proposal):
            return True
        return op_weight > 0

    if change_type == "removed" and op_row is None and user_row is not None:
        return proposal is not None and user_weight > 0

    if change_type == "weight_changed" and proposal is not None:
        if _proposal_weight_match(op_weight, proposal) and abs(user_weight - op_weight) > WEIGHT_EPS:
            return True
        if abs(op_weight - _row_weight(proposal)) <= PROPOSAL_MATCH_EPS and abs(user_weight - op_weight) > WEIGHT_EPS:
            return True

    if proposal is not None and op_row is not None and user_row is not None:
        if _proposal_weight_match(op_weight, proposal) and abs(user_weight - op_weight) > WEIGHT_EPS:
            return True

    return False


def classify_diff_reason(
    *,
    change_type: str,
    ticker: str,
    user_row: dict[str, str] | None,
    op_row: dict[str, str] | None,
    proposal_map: dict[str, dict[str, str]],
    approval_flag: bool,
    guard: dict[str, Any],
) -> GuardReason:
    if approval_flag:
        return "approved_change"

    if _is_ticker_resolution_only(user_row, op_row):
        return "ticker_resolution_change"

    if _is_formatting_only_row(user_row, op_row) and change_type in {"weight_changed", "unchanged"}:
        return "formatting_only"

    if _is_system_proposal_leak(
        change_type=change_type,
        ticker=ticker,
        user_row=user_row,
        op_row=op_row,
        proposal_map=proposal_map,
        approval_flag=approval_flag,
    ):
        return "system_proposal_leak"

    if guard.get("user_target_bootstrapped_at") and not guard.get("last_approved_write_at"):
        if change_type == "weight_changed":
            delta = abs(_row_weight(op_row) - _row_weight(user_row))
            if delta < 0.2:
                return "bootstrap_initialization"

    if change_type in {"added", "removed"}:
        return "unknown_material"

    delta = abs(_row_weight(op_row) - _row_weight(user_row))
    if delta >= WEIGHT_EPS:
        return "unknown_material"

    return "unknown"


def reason_to_severity(reason: str) -> GuardSeverity:
    return SEVERITY_BY_REASON.get(reason, "WARN")  # type: ignore[return-value]


def aggregate_guard_severity(reasons: list[str]) -> GuardSeverity:
    if any(r in FAIL_REASONS for r in reasons):
        return "FAIL"
    if any(r in WARN_REASONS for r in reasons):
        return "WARN"
    if reasons and all(r in {"formatting_only", "approved_change"} for r in reasons):
        return "PASS"
    if not reasons:
        return "PASS"
    return "WARN"


def bootstrap_user_target_if_missing(data_dir: Path) -> Path | None:
    """Copy operational target to user baseline when user file is absent."""
    user_path = user_target_portfolio_path(data_dir)
    if user_path.exists():
        return None
    op_path = operational_target_path(data_dir)
    if not op_path.exists():
        return None
    shutil.copy2(op_path, user_path)
    guard = _load_guard(data_dir)
    guard["user_target_bootstrapped_at"] = datetime.now(timezone.utc).isoformat()
    guard["operational_target_hash"] = _content_hash(_read_csv_rows(op_path))
    guard["user_target_hash"] = _content_hash(_read_csv_rows(user_path))
    _save_guard(data_dir, guard)
    return user_path


def write_target_portfolio_approved(
    data_dir: Path,
    rows: list[dict[str, Any]],
    *,
    approved_by: str,
    reason: str = "",
    source: str = "approval_bridge",
    output_dir: Path | None = None,
) -> Path:
    """Write data/target_portfolio.csv only with explicit approval."""
    from src.alpha.target_write_audit import write_operational_target
    from src.models import TargetRow

    typed = [TargetRow.model_validate(r) for r in rows]
    result = write_operational_target(
        data_dir,
        typed,
        source=source,
        reason=reason or f"approved_by={approved_by}",
        approved_by_user=True,
        writer_module=f"write_target_portfolio_approved:{approved_by}",
        output_dir=output_dir,
        sync_user_target=True,
    )
    if result.blocked or not result.path:
        raise TargetPortfolioWriteBlockedError(result.audit.get("target_write_reason", "blocked"))
    return result.path


def restore_target_from_user_baseline(
    data_dir: Path,
    *,
    exclude_tickers: frozenset[str] | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Restore operational target from user-confirmed baseline (not --approve-target)."""
    from src.alpha.target_write_audit import write_operational_target
    from src.models import TargetRow

    exclude = {_normalize_ticker(t) for t in (exclude_tickers or frozenset())}
    user_path = user_target_portfolio_path(data_dir)
    if not user_path.exists():
        raise FileNotFoundError(f"user target missing: {user_path}")

    user_rows = _read_csv_rows(user_path)
    restored_rows = [
        r for r in user_rows
        if _normalize_ticker(r.get("ticker", "")) not in exclude
    ]
    if not restored_rows:
        raise ValueError("restore would leave target_portfolio.csv empty")

    typed = [TargetRow.model_validate(r) for r in restored_rows]
    result = write_operational_target(
        data_dir,
        typed,
        source="restore_from_user_target",
        reason="restore_from_user_target",
        approved_by_user=False,
        writer_module="restore_target_from_user_baseline",
        output_dir=output_dir,
        restore_occurred=True,
    )
    if result.blocked or not result.path:
        raise TargetPortfolioWriteBlockedError(result.audit.get("target_write_reason", "blocked"))
    return result.path


def auto_restore_operational_target_if_needed(
    data_dir: Path,
    output_dir: Path | None = None,
    *,
    exclude_tickers: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Restore operational target from user baseline when guard FAIL. Returns restore metadata."""
    exclude = exclude_tickers or frozenset({"030190"})
    pre = evaluate_target_guard(data_dir, output_dir)
    user_path = user_target_portfolio_path(data_dir)
    if pre.get("severity") != "FAIL" or not user_path.exists():
        return {
            "restored": False,
            "pre_guard": pre,
            "post_guard": pre,
        }
    restore_target_from_user_baseline(data_dir, exclude_tickers=exclude, output_dir=output_dir)
    post = evaluate_target_guard(data_dir, output_dir)
    return {
        "restored": True,
        "restore_reason": "restore_from_user_target",
        "pre_guard": pre,
        "post_guard": post,
        "pre_severity": pre.get("severity"),
        "post_severity": post.get("severity"),
    }


def operational_tickers_not_in_user(data_dir: Path) -> list[str]:
    """Tickers in operational target but absent from user target."""
    user_path = user_target_portfolio_path(data_dir)
    if not user_path.exists():
        return []
    user_rows = _read_csv_rows(user_path)
    op_rows = _read_csv_rows(operational_target_path(data_dir))
    user_set = {_normalize_ticker(r.get("ticker", "")) for r in user_rows if _normalize_ticker(r.get("ticker", ""))}
    extras: list[str] = []
    for r in op_rows:
        tk = _normalize_ticker(r.get("ticker", ""))
        if tk and tk not in user_set:
            extras.append(tk)
    return sorted(extras)


def build_target_guard_diff_rows(
    data_dir: Path,
    output_dir: Path | None = None,
) -> list[dict[str, Any]]:
    user_path = user_target_portfolio_path(data_dir)
    op_path = operational_target_path(data_dir)
    if not user_path.exists():
        bootstrap_user_target_if_missing(data_dir)

    user_rows = _read_csv_rows(user_path if user_path.exists() else op_path)
    op_rows = _read_csv_rows(op_path)
    user_map = {_normalize_ticker(r.get("ticker", "")): r for r in user_rows if _normalize_ticker(r.get("ticker", ""))}
    op_map = {_normalize_ticker(r.get("ticker", "")): r for r in op_rows if _normalize_ticker(r.get("ticker", ""))}
    guard = _load_guard(data_dir)
    approval_flag = bool(guard.get("approval_flag")) or bool(guard.get("last_approved_write_at"))
    proposal_map = _load_proposal_map(data_dir, output_dir)

    diff_rows: list[dict[str, Any]] = []
    all_tickers = sorted(set(user_map) | set(op_map))
    for tk in all_tickers:
        user_row = user_map.get(tk)
        op_row = op_map.get(tk)
        if user_row and op_row and not _material_fields_differ(user_row, op_row):
            continue
        if user_row and op_row and _is_formatting_only_row(user_row, op_row):
            change_type = "weight_changed"
        elif user_row is None:
            change_type = "added"
        elif op_row is None:
            change_type = "removed"
        else:
            change_type = "weight_changed"

        reason = classify_diff_reason(
            change_type=change_type,
            ticker=tk,
            user_row=user_row,
            op_row=op_row,
            proposal_map=proposal_map,
            approval_flag=approval_flag,
            guard=guard,
        )
        diff_rows.append({
            "ticker": tk,
            "name": (op_row or user_row or {}).get("name", ""),
            "change_type": change_type,
            "previous_weight": _row_weight(user_row),
            "current_weight": _row_weight(op_row),
            "reason": reason,
            "severity": reason_to_severity(reason),
        })
    return diff_rows


def evaluate_target_guard(
    data_dir: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Full target guard evaluation with reason counts and aggregate severity."""
    guard = _load_guard(data_dir)
    op_path = operational_target_path(data_dir)
    user_path = user_target_portfolio_path(data_dir)
    op_rows = _read_csv_rows(op_path)
    user_rows = _read_csv_rows(user_path) if user_path.exists() else []
    current_hash = _content_hash(op_rows)
    user_hash = _content_hash(user_rows) if user_rows else ""
    previous_hash = str(guard.get("operational_target_hash") or guard.get("user_target_hash") or "")

    diff_rows = build_target_guard_diff_rows(data_dir, output_dir)
    reasons = [str(r.get("reason", "unknown")) for r in diff_rows]
    severity = aggregate_guard_severity(reasons)

    fail_reasons = [r for r in reasons if r in FAIL_REASONS]
    warn_reasons = [r for r in reasons if r in WARN_REASONS]
    system_proposal_leak_count = sum(1 for r in reasons if r == "system_proposal_leak")
    unknown_material_count = sum(1 for r in reasons if r == "unknown_material")

    approval_flag = bool(guard.get("approval_flag")) or bool(guard.get("last_approved_write_at"))
    hash_changed = bool(previous_hash) and previous_hash != current_hash

    if not diff_rows and not hash_changed:
        status = "pass"
        severity = "PASS"
    elif severity == "FAIL":
        status = "fail"
    elif severity == "WARN":
        status = "warn"
    else:
        status = "pass"

    if hash_changed and not approval_flag and severity == "PASS":
        if not diff_rows or any(str(r.get("reason")) != "formatting_only" for r in diff_rows):
            severity = "WARN"
            status = "warn"

    return {
        "status": status,
        "severity": severity,
        "target_portfolio_guard_status": status,
        "target_portfolio_guard_severity": severity,
        "previous_hash": previous_hash,
        "current_hash": current_hash,
        "user_target_hash": user_hash,
        "approval_flag": approval_flag,
        "changed_rows": len(diff_rows),
        "fail_reasons_count": len(fail_reasons),
        "warn_reasons_count": len(warn_reasons),
        "system_proposal_leak_count": system_proposal_leak_count,
        "unknown_material_count": unknown_material_count,
        "fail_reasons": sorted(set(fail_reasons)),
        "warn_reasons": sorted(set(warn_reasons)),
        "top10_changed_rows": diff_rows[:10],
        "recommended_action": (
            "restore approved target or approve target change"
            if severity in {"FAIL", "WARN"}
            else "none"
        ),
        "recovery_guide": RECOVERY_GUIDE_KO if system_proposal_leak_count > 0 else "",
        "hash_changed_without_approval": hash_changed and not approval_flag,
    }


def inspect_target_guard(data_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    return evaluate_target_guard(data_dir, output_dir)


def check_unapproved_target_overwrite(data_dir: Path, output_dir: Path | None = None) -> list[str]:
    """Return human-readable warnings/failures for health integration."""
    detail = evaluate_target_guard(data_dir, output_dir)
    messages: list[str] = []
    severity = detail.get("severity", "PASS")
    if detail.get("hash_changed_without_approval"):
        if severity == "FAIL":
            messages.append(
                "target_portfolio.csv changed without approval — "
                f"FAIL ({detail.get('system_proposal_leak_count', 0)} proposal leak, "
                f"{detail.get('unknown_material_count', 0)} material)"
            )
        else:
            messages.append("target_portfolio.csv changed without approval flag — treat as WARN")
    elif severity == "FAIL":
        messages.append(
            f"target_portfolio_guard FAIL — "
            f"proposal_leak={detail.get('system_proposal_leak_count', 0)} "
            f"material={detail.get('unknown_material_count', 0)}"
        )
    return messages


def write_target_guard_diff(data_dir: Path, output_dir: Path) -> Path:
    path = output_dir / "target_portfolio_guard_diff.csv"
    rows = build_target_guard_diff_rows(data_dir, output_dir)
    fieldnames = [
        "ticker", "name", "change_type", "previous_weight", "current_weight", "reason", "severity",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def apply_target_guard_to_permissions(
    trade_permission: str,
    position_action: str,
    *,
    guard_severity: str,
) -> tuple[str, str]:
    """FAIL 시 Buy/Add/Replace 차단, risk-reduce Trim만 허용."""
    if guard_severity != "FAIL":
        return trade_permission, position_action
    return "BLOCK_ALL", "RISK_REDUCE_ONLY"


def apply_target_guard_to_actions(
    actions: list,
    gap_rows: list,
    *,
    guard_severity: str,
) -> tuple[list, list]:
    """FAIL 시 Buy/Add/Rebalance/Replace 및 target 기반 Trim을 review-only로."""
    if guard_severity != "FAIL":
        return actions, []

    from src.execution_permissions import infer_trim_reason
    from src.execution_scope import _is_kr_alpha_risk_reduction_trim
    from src.models import TradeAction

    gap_map = {r.ticker: r for r in gap_rows}
    executable: list[TradeAction] = []
    extra_review: list[TradeAction] = []
    blocked_actions = frozenset({
        "Buy", "Buy-allowed", "Add", "Rebalance", "Replace",
    })

    for act in actions:
        if act.ticker == "PORTFOLIO":
            executable.append(act)
            continue

        row = gap_map.get(act.ticker)
        is_kr = row is not None and row.asset_group == "kr_alpha"
        action_name = str(act.action)

        if action_name in blocked_actions or (is_kr and action_name in {"Buy-allowed", "Wait"} and act.allowed_size_pct and act.allowed_size_pct > 0):
            extra_review.append(act)
            executable.append(
                TradeAction(
                    ticker=act.ticker,
                    name=act.name,
                    action="Review-only",
                    reason="target_portfolio_guard FAIL — 승인되지 않은 target 오염, 신규/교체/리밸런스 금지",
                    allowed_size_pct=0,
                    priority="Low",
                )
            )
            continue

        if action_name == "Trim":
            trim_reason = infer_trim_reason(action_name, act.reason or "")
            is_risk = trim_reason == "risk_reduce" or _is_kr_alpha_risk_reduction_trim(act, {"kr_alpha_risk_trim_under_etf_only": True})
            if is_risk:
                extra_review.append(act)
                executable.append(
                    TradeAction(
                        ticker=act.ticker,
                        name=act.name,
                        action="Trim",
                        reason=f"{act.reason} — target_guard FAIL, 리스크 축소 Trim만 사람 승인 시 허용",
                        allowed_size_pct=act.allowed_size_pct,
                        priority=act.priority,
                    )
                )
            else:
                extra_review.append(act)
                executable.append(
                    TradeAction(
                        ticker=act.ticker,
                        name=act.name,
                        action="Review-only",
                        reason="target_portfolio_guard FAIL — target 기반 Trim review-only",
                        allowed_size_pct=0,
                        priority="Low",
                    )
                )
            continue

        if action_name in {"Hold", "Park", "No trade", "Stop-buy", "Risk defense", "Review-only"}:
            executable.append(act)
        else:
            executable.append(act)

    return executable, extra_review
