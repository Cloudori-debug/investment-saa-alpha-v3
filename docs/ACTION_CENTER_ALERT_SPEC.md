# 운영자 액션 센터 알림 명세서 (P7)

> 작성: Claude (독립 검증자) · 대상: Cursor 구현
> 목적: 원장님이 앱을 열 때마다 "지금 뭘 확인·승인해야 하는지"를 직접 찾아다니지 않아도, **앱 진입 즉시 한 곳에서** 보고 그 자리에서 처리할 수 있게 한다.
> 원칙: **새 판단 로직을 만들지 않는다.** 이미 존재하는 검증된 게이트/승인 함수들의 결과를 모아서 "보여주기"만 한다 — 계산 로직 재구현 금지, 안전 게이트 우회 금지.

---

## 0. 배경 — 왜 필요한가

지금까지 확인한 바로는, "운영자가 뭔가 해야 하는 상태"를 나타내는 신호가 이미 여러 곳에 흩어져 있다:

| 신호 | 이미 존재하는 판정 함수/필드 | 현재 UI 노출 위치 |
|---|---|---|
| PMI KR 수동 확인 필요 | `validate_pmi_kr_manual_ready()` (`src/data_refresh/kosis_tier2_manual.py`) | `src/ui/pmi_kr_manual_panel.py` — 설정/운용승인 탭 안에 있어야 발견 가능 |
| 타겟 포트폴리오 승인 대기 | `is_target_draft_pending(data_dir, draft_path)` (`src/ui/target_draft_workflow.py`) | 해당 탭 진입해야 확인 가능 |
| 레짐 수동 오버라이드(policy_cap) 만료 임박/만료 | `days_to_expiry`, `expiry_status`("ACTIVE"/"EXPIRED_REVIEW_REQUIRED") (`src/policy_cap.py`) | 별도 배너 없음 — 아무도 안 보면 만료 후에도 방치 가능 |
| core_etf 장기 차단 | `outputs/core_etf_blocking_duration.json`의 `streak_days` | 진단 패널 안에만 있음 |

지금은 원장님이 매번 여러 탭을 돌아다니며 "혹시 뭐 승인할 거 있나" 확인해야 한다. **이 스펙은 그 4가지 신호를 앱 최상단 한 곳에 모으는 것**이 전부다.

---

## 1. 신규 파일 — `src/ui/action_center.py`

### 1.1 데이터 수집 함수 (신규 로직 없음 — 기존 함수 호출만)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["critical", "warning", "info"]

@dataclass
class ActionItem:
    id: str
    severity: Severity
    title: str
    detail: str
    action_label: str          # 버튼 텍스트, 예: "PMI 패널로 이동"
    nav_target: str | None     # nav_shortcuts.navigate() 대상 메뉴명 (이동형)
    inline_action: str | None  # "target_approve_one_click" 등 인라인 처리 가능한 경우만


def collect_action_items(data_dir: Path, output_dir: Path) -> list[ActionItem]:
    items: list[ActionItem] = []

    # 1) PMI KR 수동 확인
    from src.data_refresh.kosis_tier2_manual import validate_pmi_kr_manual_ready
    from src.report.io_utils import read_output_json

    pmi_validation = validate_pmi_kr_manual_ready(data_dir)
    core_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    if not pmi_validation.get("ready") and "data_gate=YELLOW→core_etf_REVIEW_ONLY" in (core_doc.get("restriction_reasons") or []):
        blocking = read_output_json(output_dir / "core_etf_blocking_duration.json") or {}
        streak = blocking.get("streak_days")
        items.append(ActionItem(
            id="pmi_kr_manual_confirm",
            severity="warning",
            title="PMI KR 데이터 확인 필요",
            detail=f"data_gate=YELLOW로 ETF 매수 {core_doc.get('eligible_etf_underweight_count', 0)}건 차단 중"
                   + (f" ({streak}일째)" if streak else "") + " — S&P Global 공식 수치 확인 후 승인 필요",
            action_label="PMI 확인 패널로 이동",
            nav_target="설정",  # 실제 메뉴명은 MENU_OPTIONS 값에 맞춰 조정
            inline_action=None,
        ))

    # 2) 타겟 포트폴리오 승인 대기
    from src.ui.target_draft_workflow import is_target_draft_pending
    draft_path = output_dir / "target_portfolio_draft.csv"  # 실제 경로는 기존 코드 상수 재사용
    if is_target_draft_pending(data_dir, draft_path):
        items.append(ActionItem(
            id="target_draft_pending",
            severity="critical",
            title="타겟 포트폴리오 승인 대기",
            detail="새 제안이 있습니다 — 검토 후 승인해야 target_portfolio.csv에 반영됩니다.",
            action_label="승인 화면으로 이동",
            nav_target="운용 승인",  # 실제 메뉴명에 맞춰 조정
            inline_action=None,
        ))

    # 3) policy_cap(레짐 override) 만료 임박/만료
    compass = read_output_json(output_dir / "compass_regime.json") or {}
    # days_to_expiry / expiry_status는 policy_cap 모듈 산출값을 daily_brief 또는 compass_regime에 이미 반영 중인지 확인 후 사용.
    # 없다면 src.policy_cap의 평가 함수를 직접 호출 (신규 계산 아님, 기존 함수 재사용).
    from src.policy_cap import evaluate_policy_cap  # 실제 함수명은 policy_cap.py 내 공개 API로 대체
    cap_state = evaluate_policy_cap(data_dir)  # 시그니처는 기존 코드 확인 후 맞출 것
    days_left = getattr(cap_state, "days_to_expiry", None)
    expiry_status = getattr(cap_state, "expiry_status", "NONE")
    if expiry_status == "EXPIRED_REVIEW_REQUIRED":
        items.append(ActionItem(
            id="policy_cap_expired",
            severity="critical",
            title="정책 캡(레짐 오버라이드) 만료 — 재검토 필요",
            detail=f"수동 레짐 오버라이드가 만료되었습니다: {cap_state.reason if hasattr(cap_state, 'reason') else ''}",
            action_label="나침반/레짐 화면으로 이동",
            nav_target="나침반",
            inline_action=None,
        ))
    elif days_left is not None and 0 <= days_left <= 14:
        items.append(ActionItem(
            id="policy_cap_expiring_soon",
            severity="warning",
            title=f"정책 캡 만료 {days_left}일 전",
            detail="만료 시 자동으로 컴퓨티드 레짐으로 복귀합니다 — 계속 유지할지 사전 검토 권장.",
            action_label="나침반/레짐 화면으로 이동",
            nav_target="나침반",
            inline_action=None,
        ))

    return items
```

**중요**: 위 3)의 `evaluate_policy_cap` 함수명·시그니처는 실제 `src/policy_cap.py` 공개 API를 그대로 사용할 것 — **`src/policy_cap.py` 파일 자체는 절대 수정 금지** (안전불변식, 아래 3장 참고). 이미 계산된 값을 어디선가 읽어올 수 있다면(예: `daily_brief.json`이나 `compass_regime.json`에 이미 필드가 있다면) 새로 함수를 호출하지 말고 그 값을 그대로 읽는 것을 우선한다.

### 1.2 렌더링 함수

```python
def render_action_center(data_dir: Path, output_dir: Path) -> None:
    import streamlit as st
    from src.ui.nav_shortcuts import navigate

    items = collect_action_items(data_dir, output_dir)
    if not items:
        return

    today = date.today().isoformat()
    dismissed = st.session_state.get("action_center_dismissed_date")
    if dismissed == today and st.session_state.get("action_center_dismissed_all"):
        # 오늘 하루 전체 닫기 상태 — 단, critical 항목은 무시하고 항상 노출
        items = [i for i in items if i.severity == "critical"]
        if not items:
            return

    has_dialog = hasattr(st, "dialog")  # Streamlit >= 1.37 여부 확인 후 분기

    def _body():
        for item in items:
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[item.severity]
            st.markdown(f"{icon} **{item.title}**")
            st.caption(item.detail)
            if st.button(item.action_label, key=f"ac_{item.id}"):
                if item.nav_target:
                    navigate(item.nav_target)
                st.rerun()
            st.divider()
        if st.button("오늘 하루 닫기 (긴급 항목 제외)", key="ac_dismiss_today"):
            st.session_state["action_center_dismissed_date"] = today
            st.session_state["action_center_dismissed_all"] = True
            st.rerun()

    if has_dialog:
        @st.dialog(f"확인이 필요합니다 ({len(items)}건)")
        def _popup():
            _body()
        if st.session_state.get("action_center_popup_shown_date") != today:
            st.session_state["action_center_popup_shown_date"] = today
            _popup()
        else:
            # 팝업은 세션당 1회만 자동으로 뜸 — 이후엔 상단 배너로만 노출
            with st.expander(f"⚠️ 확인 필요 {len(items)}건", expanded=any(i.severity == "critical" for i in items)):
                _body()
    else:
        # Streamlit 버전이 st.dialog 미지원 시 폴백 — 상단 고정 배너
        with st.container(border=True):
            st.markdown(f"### ⚠️ 확인이 필요합니다 ({len(items)}건)")
            _body()
```

**Streamlit 버전 확인**: `st.dialog`는 Streamlit ≥1.37에서 안정 지원. 구현 전 `pip show streamlit` 또는 `streamlit.__version__`으로 실제 설치 버전을 확인하고, 미지원이면 위 폴백(고정 컨테이너 배너)만 사용할 것 — 없는 API를 억지로 흉내내지 말 것.

---

## 2. `app.py` 연결 지점

`app.py`의 사이드바 렌더링 이후, `page = st.radio(...)` 이전에 삽입 (즉 어떤 메뉴에 있든 항상 최상단에 먼저 평가되도록):

```python
from src.ui.action_center import render_action_center
render_action_center(DATA_DIR, OUTPUT_DIR)
```

이 한 줄 추가 외에 `app.py`의 기존 라우팅/사이드바 로직은 건드리지 않는다.

---

## 3. 안전불변식 (반드시 유지)

- **절대 수정 금지**: `src/policy_cap.py`, `src/execution_scope.py`, `src/execution_guards.py`, `src/validation/bundle_consistency.py`, target_write/approval_bridge 관련 파일. 이번 스펙은 이 파일들의 **공개 함수를 읽기 전용으로 호출**할 뿐이다.
- **버튼은 전부 "이동(navigate)" 또는 기존에 이미 검증된 1-클릭 승인 함수 호출만 허용** — 이 스펙에서 새로운 승인/실행 로직을 만들지 않는다. 예: PMI 확인은 값 검토·수정이 필요한 작업이므로 팝업에서 바로 처리하지 않고 반드시 기존 `pmi_kr_manual_panel`로 이동시켜서 처리하게 한다(원본 검토 없이 원클릭으로 확정시키지 않기 위함).
- 타겟 포트폴리오 승인처럼 이미 완전히 검증된 1-클릭 버튼(`target_approval_actions.py`의 "✅ 승인 반영")이 존재하는 항목이라도, 이번 스펙에서는 **팝업에 그 버튼 자체를 복제해서 넣지 않는다** — 대신 "이동" 버튼으로 기존 화면으로 보내서 원본 컨텍스트(diff 미리보기 등)를 반드시 보고 승인하게 한다. 이는 성급한 승인을 방지하기 위한 의도적 설계이며, 원장님이 이후 "정말 진짜 원클릭으로 승인까지 팝업에서 끝내고 싶다"고 명시적으로 요청하면 그때 범위를 넓힌다.
- `actual_buy_allowed`, `target_write`, 자동매매 관련 로직에는 이 스펙이 어떤 형태로도 관여하지 않는다.
- 팝업/배너는 세션당 최초 1회만 자동으로 뜨고, "오늘 하루 닫기"를 눌러도 **critical 항목(타겟 승인 대기, policy_cap 만료)은 계속 노출**된다 — 조용히 묻히는 것을 방지.

---

## 4. 검증 체크리스트

1. `collect_action_items()`가 호출하는 함수들이 실제로 기존 코드에 있는 함수인지 확인 (특히 `evaluate_policy_cap` 실명은 `src/policy_cap.py`를 직접 열어 실제 공개 함수명으로 교체했는지)
2. PMI 미확인 상태에서 앱 로드 시 배너/팝업에 해당 항목이 뜨는지 스크린샷 또는 텍스트로 확인
3. PMI를 `verified=true`로 승인한 뒤 재기동 시 해당 항목이 사라지는지 확인
4. 타겟 드래프트가 없는 평소 상태에서는 해당 항목이 안 뜨는지 확인 (즉 false positive 없음)
5. `st.dialog` 지원 여부 확인 결과와 실제 적용한 분기(팝업 vs 폴백 배너) 기록
6. 절대 금지 파일 mtime 변경 없음 확인
7. `python scripts/verify_claude_review.py` 재실행 — `overall_pass` 유지 확인
8. 기존 `pmi_kr_manual_panel`, `target_approval_actions` 화면의 기존 동작(버튼 등)이 이번 변경으로 회귀하지 않았는지 확인 (import만 추가되고 로직 변경 없어야 함)

## 5. 향후 확장 (이번 범위 아님, 참고만)

- `outputs/quarantine/` 하위에 미확인 사고 아티팩트가 쌓이는 경우도 액션 센터에 추가할 수 있으나, "확인됨" 상태를 추적할 파일이 아직 없다 — 별도 스펙에서 다룰 것.
- 여러 항목을 진짜 "팝업에서 원클릭 승인"까지 확장하고 싶다면, 그건 이번 스펙과 별개로 명시적 요청 후 안전 검토를 거쳐 진행한다.
