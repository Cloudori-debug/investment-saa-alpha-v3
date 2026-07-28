"""CLI progress — 단계별 진행 표시 (배치/터미널 실행 시 멈춤 오해 방지)."""
from __future__ import annotations

_STEP_LABELS: dict[str, str] = {
    "data_refresh": "시장지표 갱신",
    "market_data_refresh": "시장 데이터 수집 (PyKRX/Yahoo)",
    "data_hooks": "수급·유니버스 훅",
    "target_guard": "목표 포트폴리오 검증",
    "target_guard_precheck": "목표 가드 사전검사",
    "pipeline_core": "핵심 파이프라인",
    "portfolio_state_build": "포트폴리오 상태",
    "saa_taa_allocation": "나침반 SAA/TAA",
    "alpha_v1_pipeline": "Alpha v1",
    "alpha_v2_pipeline": "Alpha v2",
    "flow_dashboard": "수급 대시보드",
    "final_decision_core": "최종 실행 결정",
    "post_decision_artifacts": "산출물·하케다카 리서치",
    "research_outputs": "기회·성과 리서치",
    "diagnostics": "진단·게이트",
    "bundle_reconcile": "번들 정합",
    "shadow_history": "섀도 이력",
    "report_exports": "리포트보내기",
    "post_run_commit_snapshot": "실행 스냅샷",
    "zip_bundle": "AI 검증 ZIP",
    "runtime_profile": "런타임 프로파일",
    "kosdaq_universe_sync": "KOSDAQ 유니버스",
    "flow_dashboard_hook": "수급 캐시",
}


def cli_progress_callback(status: str, step_name: str, elapsed: float) -> None:
    label = _STEP_LABELS.get(step_name, step_name)
    if status == "start":
        print(f"  >> {label}...", flush=True)
    elif status == "end" and elapsed >= 0.5:
        print(f"  OK {label} ({elapsed:.0f}초)", flush=True)


def print_cli_run_header(*, run_mode: str, entrypoint: str = "cli") -> None:
    if entrypoint != "cli":
        return
    print(
        f"\n[투자 나침반] 분석 시작 (run_mode={run_mode})\n"
        "  standard 모드는 보통 5~10분 걸립니다. 아래 단계 메시지가 나올 때까지 기다려 주세요.\n",
        flush=True,
    )
