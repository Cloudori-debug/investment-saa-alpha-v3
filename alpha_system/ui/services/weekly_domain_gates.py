"""Domain-separate approval gates for weekly qualitative report.

CECS / T2 / thesis / targets each require source review + explicit approve.
Approving one domain never auto-approves another. Unapproved AI inputs are
never consumed by eligibility / triggers / exit engines.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import yaml

from alpha_system.journal import append_record
from alpha_system.ui.services.cecs_ai_research import (
    ParsedResearchAxis,
    ParsedResearchSuggestion,
)
from alpha_system.ui.services.cecs_workbench import (
    approve_ai_suggestions,
    import_ai_suggestions,
)
from alpha_system.ui.services.runtime_state import RuntimeState
from alpha_system.ui.services.weekly_qual_report import (
    DOMAIN_KEYS,
    SUGGESTIONS_LANE_MONTHLY,
    SUGGESTIONS_LANE_WEEKLY,
    _exit_entry_has_usable_target,
    lane_for_domain,
    load_weekly_suggestions,
    suggestions_path,
)

SUGGESTIONS_NAME = "weekly_qual_suggestions.json"  # legacy alias


def mark_sources_reviewed(
    *,
    root: Path,
    domain: str,
    keys: Sequence[str],
) -> dict[str, Any]:
    domain = _require_domain(domain)
    lane = lane_for_domain(domain)
    payload = _load(root, lane=lane)
    if not payload:
        raise ValueError(
            "월간 CECS 제안 파일이 없습니다. 먼저 월간 메뉴에서 업로드하세요."
            if lane == SUGGESTIONS_LANE_MONTHLY
            else "주간 정성 제안 파일이 없습니다. 먼저 주간 메뉴에서 업로드하세요."
        )
    reviewed = set(payload.setdefault("source_reviewed", {}).setdefault(domain, []))
    reviewed.update(str(k) for k in keys if str(k).strip())
    payload["source_reviewed"][domain] = sorted(reviewed)
    _save(root, payload, lane=lane)
    return payload


def approve_domain(
    *,
    root: Path,
    domain: str,
    approved_by: str,
    as_of: date,
    reviewed_keys: Sequence[str],
    journal_path: Path | None = None,
    cecs_path: Path | None = None,
    exit_targets_path: Path | None = None,
    runtime_path: Path | None = None,
    confirm_steps: int = 0,
) -> dict[str, Any]:
    """Apply one domain after source review. Never touches target_portfolio.csv."""
    domain = _require_domain(domain)
    if not str(approved_by or "").strip():
        raise ValueError("승인자(approved_by)가 필요합니다.")
    lane = lane_for_domain(domain)
    payload = _load(root, lane=lane)
    if not payload:
        raise ValueError(
            "월간 CECS 제안 파일이 없습니다. 먼저 월간 메뉴에서 업로드하세요."
            if lane == SUGGESTIONS_LANE_MONTHLY
            else "주간 정성 제안 파일이 없습니다."
        )
    if payload.get("approved", {}).get(domain):
        raise ValueError(f"{domain} 영역은 이미 승인되었습니다.")

    required = _required_review_keys(payload, domain)
    reviewed = set(str(k) for k in reviewed_keys)
    missing = [k for k in required if k not in reviewed]
    if missing:
        raise ValueError(f"출처 미확인: {', '.join(missing)}")

    if domain == "t2" and confirm_steps < 2:
        raise ValueError("T2 승인은 2단계 확인이 필요합니다.")
    if domain == "thesis" and confirm_steps < 3:
        raise ValueError("논지 훼손 승인은 3단계 확인이 필요합니다.")

    applied: dict[str, Any] = {"domain": domain, "applied": False}

    if domain == "cecs":
        applied = _apply_cecs(
            root=root,
            payload=payload,
            as_of=as_of,
            approved_by=approved_by,
            reviewed_keys=sorted(reviewed),
            journal_path=journal_path,
            cecs_path=cecs_path,
        )
    elif domain == "t2":
        applied = _apply_t2(
            root=root,
            payload=payload,
            as_of=as_of,
            approved_by=approved_by,
            journal_path=journal_path,
            runtime_path=runtime_path,
        )
    elif domain == "thesis":
        applied = _apply_thesis(
            root=root,
            payload=payload,
            as_of=as_of,
            approved_by=approved_by,
            journal_path=journal_path,
            runtime_path=runtime_path,
        )
    elif domain == "targets":
        applied = _apply_targets(
            root=root,
            payload=payload,
            as_of=as_of,
            approved_by=approved_by,
            journal_path=journal_path,
            exit_targets_path=exit_targets_path,
        )

    payload.setdefault("approved", {})[domain] = True
    payload.setdefault("approved_meta", {})[domain] = {
        "approved_by": approved_by.strip(),
        "as_of": as_of.isoformat(),
        "applied": applied,
    }
    payload.setdefault("domain_status", {})[domain] = "approved"
    _save(root, payload, lane=lane)

    append_record(
        action_kind="WEEKLY_DOMAIN_APPROVED",
        as_of=as_of,
        subject=domain,
        rationale=f"weekly domain approved: {domain}",
        payload={
            "domain": domain,
            "lane": lane,
            "approved_by": approved_by.strip(),
            "report_id": payload.get("report_id"),
            "applied": applied,
            "target_portfolio_written": False,
        },
        journal_path=journal_path,
    )
    from alpha_system.ui.services.proposal_freeze import maybe_release_after_required_gates

    maybe_release_after_required_gates(
        root,
        payload,
        journal_path=journal_path,
        as_of=as_of,
    )
    return {"domain": domain, "payload": payload, "applied": applied}


def _apply_cecs(
    *,
    root: Path,
    payload: dict[str, Any],
    as_of: date,
    approved_by: str,
    reviewed_keys: Sequence[str],
    journal_path: Path | None,
    cecs_path: Path | None,
) -> dict[str, Any]:
    path = cecs_path or (root / "data" / "cecs_manual_scoring_template.csv")
    suggestions = [_dict_to_suggestion(item) for item in payload.get("cecs") or []]
    if not suggestions:
        raise ValueError("CECS AI 제안이 비어 있습니다.")
    # Upload alone never touches finals. This call runs only after the operator
    # reviewed sources and clicked this domain's approval button, so the
    # re-open + immediate re-finalization is explicit and audited.
    staged = import_ai_suggestions(
        path=path,
        suggestions=suggestions,
        report_name=str(payload.get("report_name") or "weekly_qual"),
        as_of=as_of,
        journal_path=journal_path,
        allow_reopen_final=True,
    )
    if not staged.imported_tickers:
        raise ValueError(
            "CECS 제안 적용 불가: 적용 가능한 종목이 없습니다. "
            f"상세: {'; '.join(staged.failures) or '없음'}"
        )
    approve_tickers = list(staged.imported_tickers)
    approved = approve_ai_suggestions(
        path=path,
        tickers=approve_tickers,
        reviewed_tickers=list(reviewed_keys),
        approved_by=approved_by,
        as_of=as_of,
        journal_path=journal_path,
    )
    return {
        "applied": True,
        "mode": "approve_ai_suggestions",
        "imported": list(staged.imported_tickers),
        "import_failures": list(staged.failures),
        "approved": list(approved.approved_tickers),
    }


def _apply_t2(
    *,
    root: Path,
    payload: dict[str, Any],
    as_of: date,
    approved_by: str,
    journal_path: Path | None,
    runtime_path: Path | None,
) -> dict[str, Any]:
    runtime_path = runtime_path or (root / "data" / "alpha_dashboard_runtime.json")
    runtime = RuntimeState.load(runtime_path)
    recorded: list[str] = []
    for item in payload.get("t2") or []:
        if not item.get("fired"):
            continue
        eid = str(item.get("event_id") or "").strip()
        if not eid:
            continue
        rationale = str(item.get("rationale") or "").strip()
        sources = item.get("sources") or []
        append_record(
            action_kind="T2_EVENT_RECORD",
            as_of=as_of,
            subject=eid,
            rationale=f"{rationale}\n출처: {'; '.join(sources)}\n승인: {approved_by}",
            trigger_snapshot={"event_id": eid, "source": "weekly_qual"},
            payload={
                "event_id": eid,
                "sources": sources,
                "approved_by": approved_by,
                "weekly_report_id": payload.get("report_id"),
            },
            journal_path=journal_path,
        )
        runtime.events_fired.add(eid)
        recorded.append(eid)
    runtime.save(runtime_path)
    rescore_note = _journal_rescore_hook(
        root=root,
        as_of=as_of,
        fired_events=recorded,
        journal_path=journal_path,
    )
    return {"applied": True, "events": recorded, "rescore_hook": rescore_note}


def _apply_thesis(
    *,
    root: Path,
    payload: dict[str, Any],
    as_of: date,
    approved_by: str,
    journal_path: Path | None,
    runtime_path: Path | None,
) -> dict[str, Any]:
    thesis = payload.get("thesis") or {}
    if not thesis.get("damage"):
        return {"applied": True, "damage": False, "note": "damage=false — 엔진 미반영"}
    runtime_path = runtime_path or (root / "data" / "alpha_dashboard_runtime.json")
    runtime = RuntimeState.load(runtime_path)
    sources = thesis.get("sources") or []
    rationale = str(thesis.get("rationale") or "").strip()
    append_record(
        action_kind="THESIS_DAMAGE_FLAG",
        as_of=as_of,
        subject="*",
        rationale=f"{rationale}\n출처: {'; '.join(sources)}\n승인: {approved_by}",
        trigger_snapshot={"thesis_damage": True, "source": "weekly_qual"},
        payload={
            "sources": sources,
            "approved_by": approved_by,
            "weekly_report_id": payload.get("report_id"),
        },
        journal_path=journal_path,
    )
    runtime.thesis_damage_active = True
    runtime.thesis_damage_cancelled = False
    runtime.save(runtime_path)
    return {"applied": True, "damage": True}


def _apply_targets(
    *,
    root: Path,
    payload: dict[str, Any],
    as_of: date,
    approved_by: str,
    journal_path: Path | None,
    exit_targets_path: Path | None,
) -> dict[str, Any]:
    """Update kr_alpha_exit_targets.yaml only — never target_portfolio.csv.

    Already-usable YAML entries (pbr_max or target_price) are **not** overwritten.
    Waiting-supplement / weekly re-upload must not wipe prior approved valuations.
    """
    path = exit_targets_path or (root / "data" / "kr_alpha_exit_targets.yaml")
    target_portfolio = root / "data" / "target_portfolio.csv"
    before_hash = _file_hash(target_portfolio)

    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tickers = data.setdefault("tickers", {})
    updated: list[str] = []
    protected: list[str] = []
    allowed_raw = payload.get("deep_tickers") or payload.get("final_tickers") or []
    allowed = {str(t).zfill(6) for t in allowed_raw if str(t).strip()}
    if not allowed:
        raise ValueError(
            "목표가 승인 거부: deep_tickers(최종 선정)가 비어 있습니다. "
            "요청서를 proposal_book 기준으로 다시 생성·업로드하세요."
        )
    rejected: list[str] = []
    for item in payload.get("targets") or []:
        ticker = str(item.get("ticker") or "").zfill(6)
        if not ticker:
            continue
        if ticker not in allowed:
            rejected.append(ticker)
            continue
        existing_entry = tickers.get(ticker)
        if _exit_entry_has_usable_target(
            existing_entry if isinstance(existing_entry, dict) else None
        ):
            protected.append(ticker)
            continue
        entry = dict(existing_entry or {}) if isinstance(existing_entry, dict) else {}
        valuation = dict(entry.get("valuation") or {})
        if item.get("pbr_max") is not None:
            valuation["pbr_max"] = float(item["pbr_max"])
        if item.get("target_price") is not None:
            entry["target_price"] = float(item["target_price"])
        entry["valuation"] = valuation
        entry["rationale"] = str(item.get("rationale") or "")
        entry["fundamental_reason"] = str(item.get("fundamental_reason") or "")
        entry["sources"] = list(item.get("sources") or [])
        entry["approved_by"] = approved_by
        entry["approved_as_of"] = as_of.isoformat()
        entry["source"] = "weekly_qual_ai_approved"
        tickers[ticker] = entry
        updated.append(ticker)

    if rejected:
        raise ValueError(
            "목표가 승인 거부: 최종 선정(proposal_book)에 없는 종목 — "
            + ", ".join(rejected)
            + ". 요청서를 현재 final로 다시 생성하세요."
        )
    if not updated and not protected and (payload.get("targets") or []):
        raise ValueError("목표가 승인 거부: 최종 선정과 일치하는 목표가 제안이 없습니다.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    after_hash = _file_hash(target_portfolio)
    if before_hash != after_hash:
        raise RuntimeError("불변 위반: target_portfolio.csv가 변경되었습니다.")

    append_record(
        action_kind="TARGET_VALUATION_MODIFY",
        as_of=as_of,
        subject=",".join(updated) or "none",
        rationale="weekly qual targets approved → exit_targets yaml only",
        payload={
            "tickers": updated,
            "protected": protected,
            "approved_by": approved_by,
            "target_portfolio_hash": after_hash,
            "yaml_path": str(path),
        },
        journal_path=journal_path,
    )
    return {
        "applied": True,
        "tickers": updated,
        "protected": protected,
        "yaml_path": str(path),
        "target_portfolio_hash": after_hash,
        "target_portfolio_written": False,
    }


def _required_review_keys(payload: dict[str, Any], domain: str) -> list[str]:
    if domain == "cecs":
        return [str(x.get("ticker")) for x in payload.get("cecs") or [] if x.get("ticker")]
    if domain == "t2":
        return [
            str(x.get("event_id"))
            for x in payload.get("t2") or []
            if x.get("fired") and x.get("event_id")
        ] or ["t2_none"]
    if domain == "thesis":
        return ["thesis"]
    if domain == "targets":
        return [str(x.get("ticker")) for x in payload.get("targets") or [] if x.get("ticker")]
    return []


def _dict_to_suggestion(item: dict[str, Any]) -> ParsedResearchSuggestion:
    def axis(raw: dict[str, Any]) -> ParsedResearchAxis:
        return ParsedResearchAxis(
            score_100=float(raw.get("score_100")),
            rationale=str(raw.get("rationale") or ""),
            sources=tuple(raw.get("sources") or ("확인 불가",)),
            provisional=bool(raw.get("provisional", False)),
        )

    return ParsedResearchSuggestion(
        ticker=str(item["ticker"]).zfill(6),
        name=str(item.get("name") or ""),
        execution=axis(item.get("execution") or {}),
        pension=axis(item.get("pension") or {}),
        purpose=axis(item.get("purpose") or {}),
    )


def _require_domain(domain: str) -> str:
    domain = str(domain or "").strip().lower()
    if domain not in DOMAIN_KEYS:
        raise ValueError(f"알 수 없는 domain: {domain}")
    return domain


def _load(
    root: Path,
    *,
    lane: str = SUGGESTIONS_LANE_WEEKLY,
) -> dict[str, Any]:
    return load_weekly_suggestions(root, lane)


def _save(
    root: Path,
    payload: dict[str, Any],
    *,
    lane: str = SUGGESTIONS_LANE_WEEKLY,
) -> None:
    path = suggestions_path(root, lane)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _journal_rescore_hook(
    *,
    root: Path,
    as_of: date,
    fired_events: Sequence[str],
    journal_path: Path | None,
) -> dict[str, Any]:
    """Compare-only rescore hook after T2 approval — never auto-runs scoring."""
    try:
        from alpha_system.loader import load_config
        from alpha_system.scoring.pending_rescore import pending_path, upsert_pending
        from alpha_system.scoring.rescore import (
            build_rescore_queue_item,
            evaluate_rescore_triggers,
        )

        cfg = load_config(root / "alpha_system" / "config" / "alpha_system.yaml")
        decision = evaluate_rescore_triggers(
            cfg, as_of=as_of, fired_events=fired_events
        )
        note = {
            "should_rescore": decision.should_rescore,
            "matched_triggers": list(decision.matched_triggers),
            "reason": decision.reason,
            "scores_auto_changed": False,
        }
        append_record(
            action_kind="RESCORE_HOOK_EVAL",
            as_of=as_of,
            subject="weekly_t2",
            rationale=decision.reason,
            payload=note,
            journal_path=journal_path,
        )
        queue_item = build_rescore_queue_item(
            decision, as_of=as_of, tickers=(), source="t2_disclosure"
        )
        if queue_item is not None:
            payload = {
                "key": queue_item.key,
                "title": queue_item.title,
                "detail": queue_item.detail,
                "triggers": list(queue_item.triggers),
                "tickers": list(queue_item.tickers),
                "as_of": queue_item.as_of,
                "source": queue_item.source,
            }
            upsert_pending(payload, path=pending_path(root))
            append_record(
                action_kind="RESCORE_TRIGGER_FIRED",
                as_of=as_of,
                subject="weekly_t2",
                rationale=queue_item.detail,
                payload={
                    **payload,
                    "scores_auto_changed": False,
                },
                journal_path=journal_path,
            )
            note["queue_key"] = queue_item.key
        return note
    except Exception as exc:
        return {"error": str(exc)}
