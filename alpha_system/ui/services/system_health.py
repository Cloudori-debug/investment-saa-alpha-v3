"""시스템 건강 점검 — 믿어도 되는지 한눈에 (Review-only · target 불변).

네트워크 재호출 없이 로컬 파일·상태만 본다.
막힘/정체면 Soft·나침반 숫자를 그대로 믿지 말라는 문구를 띄운다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

_KST = timezone(timedelta(hours=9))
Status = Literal["ok", "warn", "fail", "skip"]
Trust = Literal["trust", "caution", "blocked"]


@dataclass(frozen=True)
class HealthCheck:
    key: str
    label: str
    status: Status
    when: str = ""  # 사람용 시각
    detail: str = ""
    trust_note: str = ""  # 실패/주의 시 무엇을 믿지 말지


@dataclass
class SystemHealth:
    trust: Trust
    headline: str
    checks: list[HealthCheck] = field(default_factory=list)
    fail_n: int = 0
    warn_n: int = 0
    ok_n: int = 0

    @property
    def all_ok(self) -> bool:
        return self.fail_n == 0 and self.warn_n == 0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10 and text[4] == "-":
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=_KST)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _fmt_when(dt: datetime | None, fallback: str = "") -> str:
    if dt is None:
        return fallback
    return dt.astimezone(_KST).strftime("%Y-%m-%d %H:%M")


def _age_days(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return max(0, (_now_utc() - dt.astimezone(timezone.utc)).days)


def _age_hours(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return max(0.0, (_now_utc() - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)


def _quant_when(root: Path, market: str) -> tuple[str, datetime | None]:
    try:
        from alpha_system.screen_book import provenance_rel

        path = Path(root) / provenance_rel(market)
        if not path.is_file():
            return "", None
        raw = json.loads(path.read_text(encoding="utf-8"))
        generated = str(raw.get("generated_at") or "").strip()
        dt = _parse_dt(generated)
        if dt is None:
            as_of = str(raw.get("as_of") or "").strip()[:10]
            dt = _parse_dt(as_of)
        if dt is not None:
            return _fmt_when(dt), dt
        as_of = str(raw.get("as_of") or "").strip()[:10]
        return as_of, _parse_dt(as_of)
    except Exception:  # noqa: BLE001
        return "", None


def collect_system_health(root: Path) -> SystemHealth:
    """필수 파이프라인 점검표. 네트워크 없음."""
    root = Path(root)
    checks: list[HealthCheck] = []

    # --- 자격 ---
    krx_ok = dart_ok = fred_ok = False
    try:
        from src.settings.user_secrets import apply_secrets_to_env, load_user_secrets
        import os

        apply_secrets_to_env(Path(root) / "data")
        sec = load_user_secrets(Path(root) / "data")
        krx_ok = bool(
            (os.environ.get("KRX_ID") or sec.krx_id or "").strip()
            and (os.environ.get("KRX_PW") or sec.krx_pw or "").strip()
        )
        dart_ok = bool(
            (os.environ.get("DART_API_KEY") or os.environ.get("OPENDART_API_KEY") or sec.dart_api_key or "").strip()
        )
        fred_ok = bool((os.environ.get("FRED_API_KEY") or sec.fred_api_key or "").strip())
    except Exception:  # noqa: BLE001
        pass

    checks.append(
        HealthCheck(
            key="krx_creds",
            label="KRX 로그인 정보",
            status="ok" if krx_ok else "fail",
            detail="설정됨" if krx_ok else "미설정 · 설정 › API 키",
            trust_note="" if krx_ok else "코스피·정량·수급 숫자를 믿지 마세요",
        )
    )
    checks.append(
        HealthCheck(
            key="dart_creds",
            label="OpenDART 키",
            status="ok" if dart_ok else "warn",
            detail="설정됨" if dart_ok else "미설정 · 펀더멘털·공시 레이어 약함",
            trust_note="" if dart_ok else "공시·펀더멘털 보조는 비어 있을 수 있음",
        )
    )
    checks.append(
        HealthCheck(
            key="fred_creds",
            label="FRED 키",
            status="ok" if fred_ok else "warn",
            detail="설정됨" if fred_ok else "미설정 · 나침반 국면 단계 약함",
            trust_note="" if fred_ok else "경제 국면 Soft를 그대로 믿지 마세요",
        )
    )

    # --- 정량 ---
    for market, label, fail_missing in (
        ("KOSPI", "정량 · 코스피", True),
        ("KOSDAQ", "정량 · 코스닥", False),
    ):
        when_s, dt = _quant_when(root, market)
        age = _age_days(dt)
        if dt is None:
            checks.append(
                HealthCheck(
                    key=f"quant_{market.lower()}",
                    label=label,
                    status="fail" if fail_missing else "warn",
                    when="",
                    detail="스냅샷 없음 · 확인①",
                    trust_note=f"{market} Soft·점수를 믿지 마세요",
                )
            )
        elif age is not None and age >= 2:
            checks.append(
                HealthCheck(
                    key=f"quant_{market.lower()}",
                    label=label,
                    status="warn",
                    when=when_s,
                    detail=f"약 {age}일 전 · 확인① 권장",
                    trust_note=f"{market} 점수가 어제·그제 이전일 수 있음",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    key=f"quant_{market.lower()}",
                    label=label,
                    status="ok",
                    when=when_s,
                    detail="신선",
                )
            )

    # --- 시장지표 ---
    try:
        from alpha_system.ui.services.compass_inputs_refresh import (
            market_indicators_as_of,
            market_indicators_stale_days,
        )

        as_of = market_indicators_as_of(root)
        stale = market_indicators_stale_days(root)
        if not as_of:
            checks.append(
                HealthCheck(
                    key="market_indicators",
                    label="시장지표 (VIX·코스피)",
                    status="fail",
                    detail="파일 없음 · 나침반「다시 계산」",
                    trust_note="Fear&Greed Soft·변동 Soft를 믿지 마세요",
                )
            )
        elif stale is not None and stale >= 5:
            checks.append(
                HealthCheck(
                    key="market_indicators",
                    label="시장지표 (VIX·코스피)",
                    status="fail",
                    when=as_of,
                    detail=f"{stale}일 전 · 정체",
                    trust_note="나침반 Soft·변동 신호를 믿지 마세요",
                )
            )
        elif stale is not None and stale >= 3:
            checks.append(
                HealthCheck(
                    key="market_indicators",
                    label="시장지표 (VIX·코스피)",
                    status="warn",
                    when=as_of,
                    detail=f"{stale}일 전 · 주말 제외해도 다소 김",
                    trust_note="나침반 Soft가 하루·이틀 늦을 수 있음",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    key="market_indicators",
                    label="시장지표 (VIX·코스피)",
                    status="ok",
                    when=as_of,
                    detail="신선",
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            HealthCheck(
                key="market_indicators",
                label="시장지표 (VIX·코스피)",
                status="warn",
                detail=str(exc)[:120],
            )
        )

    # --- FRED 국면 ---
    try:
        from alpha_system.economy_signal import load_cached_signal

        sig = load_cached_signal(root)
        fetched = str(getattr(sig, "fetched_at", "") or "") if sig else ""
        dt = _parse_dt(fetched)
        age = _age_days(dt)
        if sig is None or not fetched:
            checks.append(
                HealthCheck(
                    key="economy_fred",
                    label="경제 국면 (FRED)",
                    status="warn",
                    detail="캐시 없음 · 나침반「다시 계산」",
                    trust_note="국면 단계·바를 믿지 마세요",
                )
            )
        elif age is not None and age >= 7:
            checks.append(
                HealthCheck(
                    key="economy_fred",
                    label="경제 국면 (FRED)",
                    status="warn",
                    when=_fmt_when(dt, fetched[:16]),
                    detail=f"약 {age}일 전",
                    trust_note="국면 Soft가 오래됐을 수 있음",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    key="economy_fred",
                    label="경제 국면 (FRED)",
                    status="ok",
                    when=_fmt_when(dt, fetched[:16]),
                    detail="캐시 있음",
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            HealthCheck(
                key="economy_fred",
                label="경제 국면 (FRED)",
                status="warn",
                detail=str(exc)[:120],
            )
        )

    # --- 수급 ---
    try:
        from alpha_system.ui.services.pension_briefing_refresh import (
            load_pension_refresh_status,
        )

        st = load_pension_refresh_status(root)
        if not isinstance(st, dict):
            checks.append(
                HealthCheck(
                    key="pension",
                    label="연기금 수급",
                    status="warn",
                    detail="갱신 기록 없음 · 확인① 또는 나침반 수급",
                    trust_note="수급 브리핑을 Soft 근거로 쓰지 마세요",
                )
            )
        else:
            status = str(st.get("status") or "")
            when = str(st.get("finished_at") or st.get("asof") or "")[:19]
            msg = str(st.get("message") or "")[:160]
            if status == "error":
                checks.append(
                    HealthCheck(
                        key="pension",
                        label="연기금 수급",
                        status="fail",
                        when=when,
                        detail=msg or "갱신 실패",
                        trust_note="수급 화면·확인① 수급 결과를 믿지 마세요",
                    )
                )
            elif status in {"ok", "success", "noop"}:
                checks.append(
                    HealthCheck(
                        key="pension",
                        label="연기금 수급",
                        status="ok",
                        when=when,
                        detail=msg or status,
                    )
                )
            else:
                checks.append(
                    HealthCheck(
                        key="pension",
                        label="연기금 수급",
                        status="warn",
                        when=when,
                        detail=f"{status} · {msg}".strip(" ·"),
                        trust_note="수급이 불완전할 수 있음",
                    )
                )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            HealthCheck(
                key="pension",
                label="연기금 수급",
                status="warn",
                detail=str(exc)[:120],
            )
        )

    # --- 가계 Lab ---
    try:
        from alpha_system.shadow.household_alloc_lab import load_report

        raw = load_report(root)
        as_of = str((raw or {}).get("as_of") or "").strip() if raw else ""
        dt = _parse_dt(as_of)
        hrs = _age_hours(dt)
        if not raw:
            checks.append(
                HealthCheck(
                    key="household_lab",
                    label="가계 ETF Lab",
                    status="warn",
                    detail="보고서 없음 · 확인①(하루1회)",
                    trust_note="정적 배분 Lab CAGR을 믿지 마세요",
                )
            )
        elif hrs is not None and hrs > 36:
            checks.append(
                HealthCheck(
                    key="household_lab",
                    label="가계 ETF Lab",
                    status="warn",
                    when=_fmt_when(dt, as_of[:16]),
                    detail=f"약 {int(hrs)}시간 전",
                    trust_note="Lab 수치가 하루 이상 전일 수 있음",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    key="household_lab",
                    label="가계 ETF Lab",
                    status="ok",
                    when=_fmt_when(dt, as_of[:16]),
                    detail="신선",
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            HealthCheck(
                key="household_lab",
                label="가계 ETF Lab",
                status="warn",
                detail=str(exc)[:120],
            )
        )

    # --- 듀얼 시그널 캐시 ---
    dual_path = Path(root) / "data" / "local" / "dual_momentum_signal.json"
    if dual_path.is_file():
        try:
            dual = json.loads(dual_path.read_text(encoding="utf-8"))
            as_of = str(dual.get("as_of") or dual.get("generated_at") or "")[:19]
            dt = _parse_dt(as_of)
            age = _age_days(dt)
            if age is not None and age >= 35:
                checks.append(
                    HealthCheck(
                        key="dual",
                        label="듀얼 모멘텀 시그널",
                        status="warn",
                        when=as_of,
                        detail=f"약 {age}일 전 · 월 리밸 전 갱신",
                        trust_note="듀얼 보유 추천을 Soft 집행으로 쓰지 마세요(앱 밖)",
                    )
                )
            else:
                checks.append(
                    HealthCheck(
                        key="dual",
                        label="듀얼 모멘텀 시그널",
                        status="ok",
                        when=as_of,
                        detail="캐시 있음 · Review-only",
                    )
                )
        except Exception:  # noqa: BLE001
            checks.append(
                HealthCheck(
                    key="dual",
                    label="듀얼 모멘텀 시그널",
                    status="warn",
                    detail="캐시 읽기 실패",
                )
            )
    else:
        checks.append(
            HealthCheck(
                key="dual",
                label="듀얼 모멘텀 시그널",
                status="skip",
                detail="아직 미실행 · 전략 비교 › 듀얼에서 갱신",
            )
        )

    # --- 최근 작업 ---
    try:
        from alpha_system.ui.services.background_job import load_job

        job = load_job(root)
        if job is None:
            checks.append(
                HealthCheck(
                    key="last_job",
                    label="최근 백그라운드 작업",
                    status="skip",
                    detail="기록 없음",
                )
            )
        elif job.busy:
            checks.append(
                HealthCheck(
                    key="last_job",
                    label="최근 백그라운드 작업",
                    status="warn",
                    when=str(job.started_at or "")[:19],
                    detail=f"진행 중 · {job.label} · {job.phase}",
                    trust_note="갱신 끝날 때까지 점수를 확정으로 보지 마세요",
                )
            )
        elif not job.ok and job.state != "cancelled":
            checks.append(
                HealthCheck(
                    key="last_job",
                    label="최근 백그라운드 작업",
                    status="fail",
                    when=str(job.ended_at or "")[:19],
                    detail=f"{job.label} 실패 · {str(job.message or '')[:140]}",
                    trust_note="방금 돌린 갱신 결과를 믿지 마세요",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    key="last_job",
                    label="최근 백그라운드 작업",
                    status="ok",
                    when=str(job.ended_at or job.started_at or "")[:19],
                    detail=f"{job.label} 완료",
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            HealthCheck(
                key="last_job",
                label="최근 백그라운드 작업",
                status="skip",
                detail=str(exc)[:80],
            )
        )

    # --- 막힘 알림 개수 ---
    try:
        from alpha_system.ui.services.data_fetch_alerts import collect_data_fetch_alerts

        alerts = collect_data_fetch_alerts(root)
        err_n = sum(1 for a in alerts if a.severity == "error")
        warn_n = sum(1 for a in alerts if a.severity != "error")
        if err_n:
            checks.append(
                HealthCheck(
                    key="alerts",
                    label="데이터 막힘 알림",
                    status="fail",
                    detail=f"빨강 {err_n} · 노랑 {warn_n}",
                    trust_note="상단 빨간 알림을 먼저 해결하세요",
                )
            )
        elif warn_n:
            checks.append(
                HealthCheck(
                    key="alerts",
                    label="데이터 막힘 알림",
                    status="warn",
                    detail=f"노랑 {warn_n}",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    key="alerts",
                    label="데이터 막힘 알림",
                    status="ok",
                    detail="없음",
                )
            )
    except Exception:  # noqa: BLE001
        pass

    fail_n = sum(1 for c in checks if c.status == "fail")
    warn_n = sum(1 for c in checks if c.status == "warn")
    ok_n = sum(1 for c in checks if c.status == "ok")

    if fail_n:
        trust: Trust = "blocked"
        headline = (
            f"시스템 막힘 {fail_n} · 주의 {warn_n} — "
            "빨간 항목이 고칠 때까지 Soft·나침반·수급 숫자를 그대로 쓰지 마세요"
        )
    elif warn_n:
        trust = "caution"
        headline = (
            f"시스템 주의 {warn_n} — "
            "일부 데이터가 오래됐거나 불완전합니다 · 주문 전 해당 항목을 확인하세요"
        )
    else:
        trust = "trust"
        headline = (
            "필수 데이터 갱신이 정상입니다 · Soft·target은 사람만 · Review-only"
        )

    return SystemHealth(
        trust=trust,
        headline=headline,
        checks=checks,
        fail_n=fail_n,
        warn_n=warn_n,
        ok_n=ok_n,
    )


def _mark(status: Status) -> str:
    return {"ok": "●", "warn": "▲", "fail": "✕", "skip": "·"}.get(status, "·")


def render_system_health_strip(root: Path, *, expanded: bool = False) -> SystemHealth:
    """운영 여정 아래 · 신뢰 한 줄 + 펼치면 점검표."""
    import streamlit as st

    health = collect_system_health(Path(root))
    if health.trust == "blocked":
        st.error(health.headline)
    elif health.trust == "caution":
        st.warning(health.headline)
    else:
        st.caption(f"시스템 점검 · {health.headline}")

    with st.expander(
        f"시스템 점검표 · 정상 {health.ok_n} · 주의 {health.warn_n} · 막힘 {health.fail_n}",
        expanded=expanded or health.trust == "blocked",
    ):
        rows: list[dict[str, str]] = []
        for c in health.checks:
            rows.append(
                {
                    "": _mark(c.status),
                    "항목": c.label,
                    "시각": c.when or "—",
                    "상태": c.detail,
                    "주의": c.trust_note or ("—" if c.status == "ok" else ""),
                }
            )
        try:
            import pandas as pd

            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        except Exception:  # noqa: BLE001
            for c in health.checks:
                note = f" — {c.trust_note}" if c.trust_note else ""
                st.markdown(
                    f"{_mark(c.status)} **{c.label}** · {c.when or '—'} · {c.detail}{note}"
                )
        st.caption(
            "확인①=정량·수급·Lab · 나침반「다시 계산」=FRED·시장지표 · "
            "설정 › API 키 테스트 · Soft/target 자동 없음"
        )
    return health


def render_system_health_panel(root: Path) -> SystemHealth:
    """설정 › 데이터 상태용 전체 패널."""
    import streamlit as st

    st.subheader("시스템 점검")
    st.caption(
        "필수 파이프라인이 살아 있는지 로컬 상태만 봅니다. "
        "막히면 Soft·나침반 숫자를 그대로 믿지 마세요."
    )
    return render_system_health_strip(root, expanded=True)


__all__ = [
    "HealthCheck",
    "SystemHealth",
    "collect_system_health",
    "render_system_health_panel",
    "render_system_health_strip",
]
