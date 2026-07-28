"""Weekly-qual proposal freeze — pin proposal tickers; block quant refresh.

Default: disabled via data/proposal_freeze_policy.json (enabled: false).
When disabled, request generation does not lock quant refresh.

Does not write target_portfolio.csv. Ranking remains pure QVM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

FREEZE_FILENAME = "weekly_qual_proposal_freeze.json"
POLICY_FILENAME = "proposal_freeze_policy.json"
REQUIRED_GATE_DOMAINS = ("t2", "thesis", "targets")


@dataclass(frozen=True)
class ProposalFreeze:
    active: bool
    frozen_at: str | None = None
    as_of: str | None = None
    report_id: str | None = None
    quant_run_id: str | None = None
    scores_sha256: str | None = None
    proposal_tickers: tuple[str, ...] = ()
    proposal_names: dict[str, str] | None = None
    source: str = "weekly_qual_report_generated"

    @property
    def tickers(self) -> tuple[str, ...]:
        return tuple(str(t).zfill(6) for t in self.proposal_tickers)


def freeze_path(root: Path) -> Path:
    return Path(root) / "data" / FREEZE_FILENAME


def policy_path(root: Path) -> Path:
    return Path(root) / "data" / POLICY_FILENAME


def freeze_feature_enabled(root: Path) -> bool:
    """Policy SoT. Missing file => disabled (permanent unlock default)."""
    path = policy_path(root)
    if not path.exists():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(raw, dict):
        return False
    return bool(raw.get("enabled"))


def set_freeze_feature_enabled(
    root: Path,
    *,
    enabled: bool,
    note: str = "",
) -> Path:
    path = policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": bool(enabled),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": note
        or (
            "주간 요청서 생성 시 정량 재실행 차단"
            if enabled
            else "기본 해제 — 요청서 생성해도 정량 잠금 없음"
        ),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Clear any leftover active lock when turning the feature off.
    if not enabled:
        fr = load_freeze(root, apply_policy=False)
        if fr.active:
            release_freeze(root, reason="proposal_freeze_policy.enabled=false")
    return path


def ensure_default_policy(root: Path) -> Path:
    """Write disabled policy if missing (first-run permanent unlock)."""
    path = policy_path(root)
    if path.exists():
        return path
    return set_freeze_feature_enabled(root, enabled=False)


def load_freeze(root: Path, *, apply_policy: bool = True) -> ProposalFreeze:
    path = freeze_path(root)
    if not path.exists():
        return ProposalFreeze(active=False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ProposalFreeze(active=False)
    if not isinstance(raw, dict):
        return ProposalFreeze(active=False)
    tickers = raw.get("proposal_tickers") or []
    names = raw.get("proposal_names") or {}
    active = bool(raw.get("active"))
    if apply_policy and not freeze_feature_enabled(root):
        active = False
    return ProposalFreeze(
        active=active,
        frozen_at=str(raw.get("frozen_at") or "") or None,
        as_of=str(raw.get("as_of") or "") or None,
        report_id=str(raw.get("report_id") or "") or None,
        quant_run_id=str(raw.get("quant_run_id") or "") or None,
        scores_sha256=str(raw.get("scores_sha256") or "") or None,
        proposal_tickers=tuple(str(t).zfill(6) for t in tickers if str(t).strip()),
        proposal_names={
            str(k).zfill(6): str(v)
            for k, v in (names.items() if isinstance(names, dict) else [])
            if str(k).strip()
        },
        source=str(raw.get("source") or "weekly_qual_report_generated"),
    )


def is_freeze_active(root: Path, *, respect_policy: bool = True) -> bool:
    fr = load_freeze(root, apply_policy=respect_policy)
    return bool(fr.active and fr.tickers)


def block_message(freeze: ProposalFreeze | None = None, *, root: Path | None = None) -> str:
    fr = freeze if freeze is not None else (load_freeze(root) if root else ProposalFreeze(active=False))
    rid = fr.report_id or "—"
    as_of = fr.as_of or "—"
    return (
        f"주간 정성 창으로 정량 제안이 고정되어 있습니다 "
        f"(report {rid} · as_of {as_of}). "
        f"필수 게이트(T2·논지·목표가) 승인 후 자동 해제됩니다. "
        f"정량 재실행은 창이 열린 동안 차단됩니다."
    )


def activate_freeze(
    root: Path,
    *,
    report_id: str,
    as_of: date,
    proposal_tickers: Sequence[str],
    proposal_names: Mapping[str, str] | None = None,
    quant_run_id: str | None = None,
    scores_sha256: str | None = None,
    source: str = "weekly_qual_report_generated",
) -> ProposalFreeze:
    ensure_default_policy(root)
    tickers = tuple(str(t).zfill(6) for t in proposal_tickers if str(t).strip())
    if not tickers:
        raise ValueError("proposal_tickers가 비어 freeze를 걸 수 없습니다.")
    names = {
        str(k).zfill(6): str(v)
        for k, v in (proposal_names or {}).items()
        if str(k).strip()
    }
    enabled = freeze_feature_enabled(root)
    payload = {
        "active": bool(enabled),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of.isoformat(),
        "report_id": report_id,
        "quant_run_id": quant_run_id,
        "scores_sha256": scores_sha256,
        "proposal_tickers": list(tickers),
        "proposal_names": names,
        "source": source,
        "target_portfolio_written": False,
        "policy_enabled": enabled,
        "skipped_lock": (not enabled),
    }
    path = freeze_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return load_freeze(root)


def release_freeze(
    root: Path,
    *,
    reason: str,
    journal_path: Path | None = None,
    as_of: date | None = None,
) -> ProposalFreeze:
    prev = load_freeze(root, apply_policy=False)
    if not prev.active and not freeze_path(root).exists():
        return prev
    payload = {
        "active": False,
        "released_at": datetime.now(timezone.utc).isoformat(),
        "release_reason": reason,
        "frozen_at": prev.frozen_at,
        "as_of": prev.as_of,
        "report_id": prev.report_id,
        "quant_run_id": prev.quant_run_id,
        "scores_sha256": prev.scores_sha256,
        "proposal_tickers": list(prev.tickers),
        "proposal_names": dict(prev.proposal_names or {}),
        "source": prev.source,
        "target_portfolio_written": False,
    }
    path = freeze_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        from alpha_system.journal import append_record

        append_record(
            action_kind="PROPOSAL_FREEZE_RELEASED",
            as_of=as_of or date.today(),
            subject=prev.report_id or "*",
            rationale=reason,
            payload={
                "report_id": prev.report_id,
                "proposal_tickers": list(prev.tickers),
                "target_portfolio_written": False,
            },
            journal_path=journal_path,
        )
    except Exception:
        pass
    return load_freeze(root)


def maybe_release_after_required_gates(
    root: Path,
    payload: Mapping[str, Any],
    *,
    journal_path: Path | None = None,
    as_of: date | None = None,
) -> bool:
    """Release when T2 · thesis · targets are all approved. CECS optional."""
    approved = payload.get("approved") or {}
    if not all(bool(approved.get(d)) for d in REQUIRED_GATE_DOMAINS):
        return False
    if not is_freeze_active(root):
        return False
    release_freeze(
        root,
        reason="required gates approved (t2·thesis·targets)",
        journal_path=journal_path,
        as_of=as_of,
    )
    return True


def assert_quant_refresh_allowed(root: Path) -> None:
    """Raise RuntimeError when weekly freeze blocks quant snapshot refresh."""
    if is_freeze_active(root):
        raise RuntimeError(block_message(root=root))


def pin_proposal_rows(rows: Sequence[Any], freeze: ProposalFreeze) -> list[Any]:
    """Keep UI proposal order/set equal to freeze tickers while freeze is active."""
    if not freeze.active or not freeze.tickers:
        return list(rows)
    by_tk = {str(getattr(r, "ticker", "")).zfill(6): r for r in rows}
    return [by_tk[tk] for tk in freeze.tickers if tk in by_tk]
