"""필요 데이터 갱신 막힘 → 화면 알림 (Review-only · target 불변).

확인①·나침반·수급 등에서 실패한 사유를 `data/local/data_fetch_alerts.json`에
남기고, 모든 주메뉴 상단(운영 여정)에 띄운다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ALERTS_REL = Path("data") / "local" / "data_fetch_alerts.json"
_KST = timezone(timedelta(hours=9))


# key → 사용자가 바로 할 조치 (화면 경고에 항상 표시)
_ACTION_BY_KEY: dict[str, str] = {
    "krx_login": "설정 › 비밀키/KRX 로그인 확인 → 확인① 다시 실행",
    "fred": "나침반「다시 계산」또는 확인① · FRED 키·네트워크 확인",
    "dart": "설정 › OpenDART API 키 확인 → 확인① 재실행",
    "pension": "형제 fund-screener 기동 후 확인①·수급「다시 읽기」",
    "korea_10y": "확인① 또는 나침반「다시 계산」· 하루 뒤 재시도",
    "market_indicators": "나침반「다시 계산」· 확인① (VIX/코스피)",
    "market_stale": "나침반「다시 계산」또는 확인①으로 시장지표 갱신",
    "household_lab": "전략 › 정적 Lab 수동 갱신 · Soft/target 불변",
    "quant_missing": "확인 › ① 「중기·단기 정량·정성 한 번에」실행",
    "quant_stale": "확인 › ① 통합 갱신 재실행 (시장별)",
    "job_fail": "사이드바 실패 메시지 확인 → 확인① 재실행 · 설정 KRX 테스트",
    "fetch_other": "설정 › KRX/API 테스트 후 확인① 또는 나침반「다시 계산」",
}


@dataclass(frozen=True)
class DataFetchAlert:
    key: str
    severity: str  # error | warning
    title: str
    detail: str
    where: str = ""  # 확인① · 나침반 · 설정 …
    as_of: str = ""
    action_ko: str = ""  # 조치 안내


@dataclass
class DataFetchAlertsBundle:
    alerts: list[DataFetchAlert] = field(default_factory=list)
    updated_at: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def alerts_path(root: Path) -> Path:
    return Path(root) / ALERTS_REL


def load_persisted_alerts(root: Path) -> list[DataFetchAlert]:
    path = alerts_path(root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[DataFetchAlert] = []
    for row in raw.get("alerts") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        ak = str(row.get("action_ko") or "").strip()
        if not ak:
            ak = _ACTION_BY_KEY.get(key, _ACTION_BY_KEY["fetch_other"])
        out.append(
            DataFetchAlert(
                key=key,
                severity=str(row.get("severity") or "warning"),
                title=str(row.get("title") or key),
                detail=str(row.get("detail") or "")[:400],
                where=str(row.get("where") or ""),
                as_of=str(row.get("as_of") or ""),
                action_ko=ak,
            )
        )
    return out


def save_persisted_alerts(root: Path, alerts: Sequence[DataFetchAlert]) -> Path:
    path = alerts_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now(),
        "review_only": True,
        "writes_target": False,
        "alerts": [asdict(a) for a in alerts],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def clear_alert_keys(root: Path, keys: Iterable[str]) -> None:
    drop = {str(k) for k in keys}
    keep = [a for a in load_persisted_alerts(root) if a.key not in drop]
    save_persisted_alerts(root, keep)


def record_fetch_issues(
    root: Path,
    *,
    where: str,
    errors: Sequence[str] | None = None,
    warnings: Sequence[str] | None = None,
    clear_keys: Sequence[str] | None = None,
) -> list[DataFetchAlert]:
    """Merge new issues into persisted alerts · optionally clear resolved keys."""
    by_key = {a.key: a for a in load_persisted_alerts(root)}
    for k in clear_keys or ():
        by_key.pop(str(k), None)

    def _add(sev: str, key: str, title: str, detail: str) -> None:
        by_key[key] = DataFetchAlert(
            key=key,
            severity=sev,
            title=title,
            detail=detail[:400],
            where=where,
            as_of=_now(),
            action_ko=_ACTION_BY_KEY.get(key, _ACTION_BY_KEY["fetch_other"]),
        )

    for err in errors or ():
        text = str(err or "").strip()
        if not text:
            continue
        key, title = _classify_issue(text)
        _add("error", key, title, text)
    for warn in warnings or ():
        text = str(warn or "").strip()
        if not text:
            continue
        # skip noisy / informational (not a real problem)
        if "regime_" in text and "미갱신" in text:
            continue
        if _is_info_only_warning(text):
            continue
        key, title = _classify_issue(text)
        # warnings stay yellow unless clearly a hard blocker
        sev = "error" if _is_blocker_text(text) else "warning"
        _add(sev, key, title, text)

    alerts = list(by_key.values())
    save_persisted_alerts(root, alerts)
    return alerts


def _is_info_only_warning(text: str) -> bool:
    """성공·폴백 안내 문구 — 화면 알림에 올리지 않음."""
    if "history 유효값 사용" in text:
        return True
    # as_of 전진 로그 (예: as_of 2026-11-05→2026-11-06)
    if text.strip().startswith("as_of ") and "→" in text:
        return True
    return False


def _is_blocker_text(text: str) -> bool:
    """warning 목록이어도 빨간 막힘으로 올릴 강한 실패만."""
    if _is_info_only_warning(text):
        return False
    # PyKRX 포함 문구의 'krx' 부분일치·단순 '실패'는 폴백 성공과 혼동됨
    needles = (
        "비밀번호",
        "패스워드",
        "로그인 실패",
        "로그인에 실패",
        "자격 증명",
        "api 키",
        "키가 없",
        "timeout",
        "타임아웃",
        "blocked",
        "미설정",
        "수동 갱신 필요",
        "갱신 필드 없음",
    )
    return any(n in text.lower() or n in text for n in needles)


def _classify_issue(text: str) -> tuple[str, str]:
    low = text.lower()
    if "비밀번호" in text or "패스워드" in text or "로그인" in text or "자격" in text:
        return "krx_login", "KRX 로그인 막힘"
    if "fred" in low or "FRED" in text:
        return "fred", "FRED 국면 갱신 문제"
    if "dart" in low or "opendart" in low:
        return "dart", "OpenDART 갱신 문제"
    if "pension" in low or "수급" in text:
        return "pension", "연기금 수급 갱신 문제"
    if "korea_10y" in low or "국채" in text:
        return "korea_10y", "국채 10Y 갱신 주의"
    if "market_indicators" in low or "시장지표" in text or "vix" in low:
        return "market_indicators", "시장지표(VIX·코스피) 갱신 문제"
    if "가계" in text or "household" in low:
        return "household_lab", "가계 ETF Lab 문제"
    return "fetch_other", "데이터 갱신 문제"


def action_for_issue(text: str) -> str:
    """오류/경고 문구 → 사용자 조치 한 줄."""
    key, _ = _classify_issue(str(text or ""))
    return _ACTION_BY_KEY.get(key, _ACTION_BY_KEY["fetch_other"])


def action_for_key(key: str) -> str:
    return _ACTION_BY_KEY.get(str(key or ""), _ACTION_BY_KEY["fetch_other"])


def _quant_age_days(root: Path) -> int | None:
    try:
        from alpha_system.screen_book import provenance_rel

        path = Path(root) / provenance_rel("KOSPI")
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        generated = str(raw.get("generated_at") or "").strip()
        if not generated:
            return None
        dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days)
    except Exception:  # noqa: BLE001
        return None


def collect_data_fetch_alerts(root: Path) -> list[DataFetchAlert]:
    """Persisted + 로컬 파일로 보이는 막힘(네트워크 재호출 없음)."""
    root = Path(root)
    by_key = {a.key: a for a in load_persisted_alerts(root)}

    # 시장지표 정체
    try:
        from alpha_system.ui.services.compass_inputs_refresh import (
            market_indicators_as_of,
            market_indicators_stale_days,
        )

        stale = market_indicators_stale_days(root)
        as_of = market_indicators_as_of(root)
        if stale is not None and stale >= 3:
            by_key["market_stale"] = DataFetchAlert(
                key="market_stale",
                severity="warning",
                title="시장지표가 오래됨",
                detail=f"as_of {as_of or '—'} · {stale}일 전",
                where="나침반·확인①",
                as_of=_now(),
                action_ko=_ACTION_BY_KEY["market_stale"],
            )
        else:
            by_key.pop("market_stale", None)
    except Exception:  # noqa: BLE001
        pass

    # 정량 오래됨
    q_age = _quant_age_days(root)
    if q_age is None:
        by_key["quant_missing"] = DataFetchAlert(
            key="quant_missing",
            severity="warning",
            title="정량 스냅샷 없음",
            detail="아직 통합 갱신 이력이 없습니다.",
            where="확인①",
            as_of=_now(),
            action_ko=_ACTION_BY_KEY["quant_missing"],
        )
    else:
        by_key.pop("quant_missing", None)
        if q_age >= 2:
            by_key["quant_stale"] = DataFetchAlert(
                key="quant_stale",
                severity="warning",
                title="정량이 이틀 이상 전",
                detail=f"KOSPI 정량 약 {q_age}일 전.",
                where="확인①",
                as_of=_now(),
                action_ko=_ACTION_BY_KEY["quant_stale"],
            )
        else:
            by_key.pop("quant_stale", None)

    # 수급 마지막 실패
    try:
        from alpha_system.ui.services.pension_briefing_refresh import (
            load_pension_refresh_status,
        )

        st = load_pension_refresh_status(root)
        if isinstance(st, dict) and str(st.get("status") or "") == "error":
            msg = str(st.get("message") or st.get("stderr_tail") or "수급 갱신 실패")[:280]
            by_key["pension"] = DataFetchAlert(
                key="pension",
                severity="error",
                title="연기금 수급 갱신 실패",
                detail=msg,
                where="확인①·나침반 수급",
                as_of=str(st.get("finished_at") or _now()),
                action_ko=_ACTION_BY_KEY["pension"],
            )
        elif isinstance(st, dict) and str(st.get("status") or "") in {"ok", "success"}:
            by_key.pop("pension", None)
    except Exception:  # noqa: BLE001
        pass

    # 최근 백그라운드 작업 실패 (3시간)
    try:
        from alpha_system.ui.services.background_job import load_job

        job = load_job(root)
        if job is not None and not job.busy and not job.ok and job.state != "cancelled":
            ended = str(job.ended_at or "")
            show = True
            if ended:
                try:
                    dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    show = (datetime.now(timezone.utc) - dt) < timedelta(hours=3)
                except ValueError:
                    show = True
            if show:
                by_key["job_fail"] = DataFetchAlert(
                    key="job_fail",
                    severity="error",
                    title=f"{job.label} 실패",
                    detail=str(job.message or "작업 실패")[:400],
                    where="확인①·사이드바 작업",
                    as_of=ended or _now(),
                    action_ko=_ACTION_BY_KEY["job_fail"],
                )
            else:
                by_key.pop("job_fail", None)
        elif job is not None and job.ok:
            by_key.pop("job_fail", None)
    except Exception:  # noqa: BLE001
        pass

    # 비밀키 누락 (환경만 확인 · 로그인 시도 없음)
    try:
        from src.settings.user_secrets import apply_secrets_to_env, load_user_secrets
        import os

        apply_secrets_to_env(Path(root) / "data")
        sec = load_user_secrets(Path(root) / "data")
        if not (
            (os.environ.get("KRX_ID") or sec.krx_id or "").strip()
            and (os.environ.get("KRX_PW") or sec.krx_pw or "").strip()
        ):
            by_key["krx_secrets"] = DataFetchAlert(
                key="krx_secrets",
                severity="error",
                title="KRX ID/비밀번호 미설정",
                detail="정량·코스피·수급이 막힙니다.",
                where="설정",
                as_of=_now(),
                action_ko="설정 › API 키에 KRX ID·비밀번호 저장 후 확인①",
            )
        else:
            by_key.pop("krx_secrets", None)
        if not (os.environ.get("FRED_API_KEY") or sec.fred_api_key or "").strip():
            by_key["fred_secrets"] = DataFetchAlert(
                key="fred_secrets",
                severity="warning",
                title="FRED API 키 없음",
                detail="나침반 국면 단계가 비어 있을 수 있습니다.",
                where="설정·나침반",
                as_of=_now(),
                action_ko="설정 › API 키에 FRED 저장 → 나침반「다시 계산」",
            )
        else:
            by_key.pop("fred_secrets", None)
    except Exception:  # noqa: BLE001
        pass

    # severity: errors first
    alerts = sorted(
        by_key.values(),
        key=lambda a: (0 if a.severity == "error" else 1, a.title),
    )
    return alerts


def _format_alert_block(a: DataFetchAlert, *, compact: bool = False) -> str:
    where = f" · {a.where}" if a.where else ""
    action = (a.action_ko or _ACTION_BY_KEY.get(a.key) or _ACTION_BY_KEY["fetch_other"]).strip()
    if compact:
        return f"**{a.title}**{where} — {a.detail}\n\n→ **조치:** {action}"
    return (
        f"**{a.title}**{where}\n\n{a.detail}\n\n"
        f"→ **조치:** {action}"
    )


def render_data_fetch_alerts(root: Path) -> None:
    """운영 여정 아래 · 막힘 + 조치 안내."""
    import streamlit as st

    alerts = collect_data_fetch_alerts(Path(root))
    if not alerts:
        return
    errors = [a for a in alerts if a.severity == "error"]
    warns = [a for a in alerts if a.severity != "error"]
    if errors:
        lines = [_format_alert_block(a) for a in errors[:5]]
        st.error("데이터 갱신이 막혔습니다\n\n" + "\n\n---\n\n".join(lines))
        st.caption("Soft/target 불변 · 조치 후 확인① 또는 나침반「다시 계산」")
    if warns:
        lines = [_format_alert_block(a, compact=True) for a in warns[:4]]
        st.warning("데이터 신선도 주의\n\n" + "\n\n---\n\n".join(lines))


def record_from_compass_bundle(root: Path, bundle: Any) -> None:
    errors = list(getattr(bundle, "errors", None) or [])
    warnings = list(getattr(bundle, "warnings", None) or [])
    clear: list[str] = []
    if getattr(bundle, "ok", False) and not errors:
        clear.extend(["market_indicators", "fred", "krx_login", "fetch_other"])
    if any("비밀번호" in str(e) or "로그인" in str(e) for e in errors + warnings):
        # keep krx_login
        pass
    elif getattr(bundle, "market_as_of", ""):
        clear.append("market_stale")
    record_fetch_issues(
        root,
        where="나침반·확인①",
        errors=errors,
        warnings=warnings,
        clear_keys=clear,
    )


def record_from_quant_detail(root: Path, *, ok: bool, message: str, detail: dict[str, Any]) -> None:
    errors: list[str] = []
    warnings: list[str] = []
    if not ok:
        errors.append(message or "정량 갱신 실패")
    qual = detail.get("qual_layers") if isinstance(detail, dict) else None
    if isinstance(qual, dict):
        if qual.get("pension_briefing_error"):
            errors.append(str(qual["pension_briefing_error"]))
        pb = qual.get("pension_briefing") or {}
        if isinstance(pb, dict) and str(pb.get("status") or "") == "error":
            errors.append(str(pb.get("message") or "수급 갱신 실패"))
        if qual.get("opendart_watch_error"):
            warnings.append(str(qual["opendart_watch_error"]))
        if qual.get("killswitch_watch_error"):
            warnings.append(str(qual["killswitch_watch_error"]))
    eco = detail.get("compass_inputs") if isinstance(detail, dict) else None
    if isinstance(eco, dict):
        for e in eco.get("errors") or []:
            errors.append(str(e))
        for w in eco.get("warnings") or []:
            warnings.append(str(w))
    hh = detail.get("household_alloc_lab") if isinstance(detail, dict) else None
    if isinstance(hh, dict) and hh.get("error"):
        warnings.append(str(hh["error"]))
    clear = ["job_fail", "quant_missing"] if ok else []
    if ok and not any("로그인" in e or "비밀번호" in e for e in errors):
        clear.append("krx_login")
    record_fetch_issues(
        root,
        where="확인①",
        errors=errors,
        warnings=warnings,
        clear_keys=clear,
    )


__all__ = [
    "DataFetchAlert",
    "DataFetchAlertsBundle",
    "action_for_issue",
    "action_for_key",
    "clear_alert_keys",
    "collect_data_fetch_alerts",
    "load_persisted_alerts",
    "record_fetch_issues",
    "record_from_compass_bundle",
    "record_from_quant_detail",
    "render_data_fetch_alerts",
    "save_persisted_alerts",
]
