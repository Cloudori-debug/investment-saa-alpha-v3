# PMI_KR 데이터게이트 차단 해소 명세서 (P6)

> 작성: Claude (독립 검증자) · 대상: Cursor 구현
> 목적: `core_etf_permission=RESTRICTED` 의 1차 원인(`pmi_kr` tier2 필드 stale)을 근본 수정하고, 그 결과로 ETF 매수 차단이 실제로 풀리는지 측정한다.
> 원칙: 이 스펙은 실행 게이트 완화를 "주장"하지 않는다 — 데이터 문제를 고치고, 그 다음 실제 게이트가 어떻게 재계산되는지 있는 그대로 기록한다. 게이트가 안 풀려도 그 자체가 유효한 결과다.

---

## 0. 왜 이 작업인가 (배경)

이전 검증 라운드에서 확인된 사실:

- `core_etf_permission_diagnostics.json`: `core_etf_permission=RESTRICTED`, 7일 연속 스트릭, `eligible_etf_underweight_count=11`, `hypothetical_etf_buy_count_if_unrestricted=11`
- 1차 원인은 `data_gate=YELLOW` → `tier2_provenance: pmi_kr stale`
- `data/tier2_provenance.json`의 `pmi_kr` 항목: `status=stale`, `fetch_status=failed`, `error="KOSIS err=21: 해당 통계표가 존재하지 않습니다. (tbl=DT_1C8013)"`, `source=preserved`(캐시된 과거값 51.2, 날짜 없음)
- `data/tier2_sources.yaml`의 `kosis.queries.pmi_kr.tblId: DT_1C8013` — 이 값은 코드 자체가 이미 `INVALID_TBL_IDS = frozenset({"DT_1J20001", "DT_1C8013"})` (`src/data_refresh/kosis_tblid_discovery.py:47`)로 알고 있는 **무효 테이블 ID**다. yaml 코멘트에도 "tblId may need KOSIS statisticsList verification (err 21 if invalid)"라고 이미 경고돼 있었다.
- `cpi_kr_yoy`는 동일한 문제를 이미 겪었고, discovery 도구로 `DT_1J22042`로 교체되어 현재 `fresh`로 정상 동작 중 (yaml 코멘트: "KOSIS discovery selected DT_1J22042"). **즉 같은 도구로 같은 종류의 문제를 고친 선례가 이미 이 저장소 안에 있다.**
- `pmi_kr`만 이 수정이 적용되지 않은 채 방치되어 있었다.
- 이미 구현되어 있으나 미사용 중인 도구 체인:
  - `src/data_refresh/kosis_tblid_discovery.py::run_kosis_tblid_discovery_pipeline()` — KOSIS statisticsList 검색 → 후보 검증 → 확신도 높은 경우 `tier2_sources.yaml` 자동 반영 → refresh 재실행까지 한 번에 수행
  - `src/data_refresh/kosis_tier2_manual.py` + `src/validation/pmi_kr_manual_verified_reevaluation.py` — 수동 확인값 입력 경로 (KOSIS에 정확히 일치하는 지표가 없을 때의 대안), `verified=true`로 표시된 값만 적용, 적용 후 `data_gate`/`core_etf_permission`/`actual_buy_allowed` 재평가까지 자동 수행

**중요한 판단 보류 사항**: 한국은 정부 통계(KOSIS)로 "PMI"를 직접 발표하지 않는다. 실제 "S&P Global South Korea Manufacturing PMI"는 S&P Global(舊 Markit/Nikkei)이 발표하는 민간 지표이며 KOSIS API에는 존재하지 않을 가능성이 높다 — 코드가 `pmi_kr_alt_candidate`(경기실사지수/업황전망/경기종합지수/BSI) 폴백 경로를 이미 만들어둔 것도 이 때문으로 보인다(추정, 코드 설계자 의도 확인 불가). 따라서 아래 작업 A(자동 discovery)가 실패(정확 일치 없음)하는 것은 **버그가 아니라 예상 가능한 결과**이며, 그 경우 작업 B(수동 확인)로 넘어가는 것이 정상 경로다.

---

## 1. 작업 A — 자동 KOSIS tblId 재탐색 (먼저 시도, 안전·저비용)

### 실행
```python
from pathlib import Path
from src.data_refresh.kosis_tblid_discovery import run_kosis_tblid_discovery_pipeline

result = run_kosis_tblid_discovery_pipeline(Path("data"), Path("outputs"), refresh_after_apply=True)
```

### 판정 기준 (이미 코드에 내장돼 있음 — 새로 만들 필요 없음)
- `result["pmi_kr"]["selected"]`가 존재하고 `confidence == "high"`이면 → `apply_selected_to_tier2_sources()`가 이미 자동으로 `data/tier2_sources.yaml`을 갱신했을 것 (`tier2_sources_applied`에 `"pmi_kr"` 포함 여부로 확인)
- 못 찾았거나 `confidence != "high"` (즉 `pmi_kr_alt_candidate`만 나옴) → **자동 반영되지 않음이 정상** (코드가 alt를 pmi_kr에 자동 매핑하지 않도록 이미 막아둠). 이 경우 실패로 취급하지 말고 바로 작업 B로 진행.

### 산출물
- `outputs/kosis_tblid_discovery.json`, `outputs/kosis_tblid_candidates.csv` (기존 함수가 자동 생성)
- 이 문서에 추가할 것: `docs/PMI_KR_DATA_GATE_UNBLOCK_SPEC.md`에 "작업 A 결과" 표로 실제값 기록 — `pmi_kr_kosis_unavailable`, 발견된 후보 개수, 채택 여부

---

## 2. 작업 B — 수동 확인(manual_verified) 경로 (작업 A가 정확 일치를 못 찾은 경우)

### 사전 확인된 실제 값 (Claude가 방금 웹 검색으로 확인 — 참고용, 아래 "필수 확인" 항목 반드시 재확인)

- **S&P Global South Korea Manufacturing PMI, 2026년 6월: 52.1** (5월 54.8에서 하락, 4개월 만의 최저 확장 속도)
- 발표일: 2026-07-01
- 출처: S&P Global 공식 보도자료 (pmi.spglobal.com/Public/Home/PressRelease)

**필수 확인 (Cursor가 반드시 재검증 후 적용)**: 이 수치는 Claude의 웹 검색 결과이며, 시스템 내부에서 실시간 크로스체크된 값이 아니다. 적용 전 아래 중 최소 하나로 재확인할 것:
1. S&P Global/PMI 공식 페이지에서 최신 릴리즈 날짜·수치 재확인
2. 또는 이미 이 시스템에 KOSIS 외 다른 신뢰 가능한 API 경로(예: 별도 유료/무료 데이터 벤더)가 있다면 그쪽에서 크로스체크
3. 운영자(동준) 최종 확인 없이 `verified: true`로 설정하지 말 것 — `kosis_tier2_manual.py`의 설계 의도 자체가 "사람이 최종 확인한 값만 시스템에 주입"이므로, Cursor가 이 게이트를 스스로 허물면 안 됨. 재확인 완료 후 `verified: true`로 설정.

### 구현
`data/tier2_kosis_manual.yaml` 생성 (현재 파일 없음 — 신규 생성):
```yaml
pmi_kr:
  verified: true   # 운영자 최종 확인 후에만 true로 설정 — 위 "필수 확인" 항목 통과 전에는 false로 두고 PR/보고만 할 것
  value: 52.1
  value_date: "2026-06-30"
  source: "S&P Global South Korea Manufacturing PMI (released 2026-07-01)"
  updated_by: "claude_web_verification_pending_operator_confirm"
  update_reason: "KOSIS tblId DT_1C8013 invalid (err21, no KOSIS-native PMI series exists). Manual entry per existing manual-verified path. Operator confirmation required before verified=true is trusted for gating."
```

`validate_pmi_kr_manual_ready()` (`src/data_refresh/kosis_tier2_manual.py`)가 요구하는 필드(`value`, `verified` 등)는 이미 정의돼 있으니 스키마 그대로 채울 것 — 새 필드 추가 금지.

### 실행
```python
from pathlib import Path
from src.validation.pmi_kr_manual_verified_reevaluation import run_pmi_kr_manual_verified_reevaluation

doc = run_pmi_kr_manual_verified_reevaluation(Path("data"), Path("outputs"))
```
이 함수가 이미 다음을 자동 수행:
- `kosis_tier2_refresh`를 manual override로 재실행
- `write_core_etf_permission_diagnostics()`, `write_data_gate_diagnostics()` 재계산
- `outputs/pmi_kr_manual_verified_reevaluation.json`에 before/after 기록 (이미 스키마 완비 — `checks` 8개 항목, `actual_buy_trace`, `core_etf_reevaluation` 등)

---

## 3. 안전불변식 — 반드시 유지 (이전 라운드와 동일)

절대 수정 금지 파일: `src/policy_cap.py`, `src/execution_scope.py`, `src/execution_guards.py`, `src/validation/bundle_consistency.py`, target_write / approval_bridge 관련 모든 파일.

- `policy_cap_active`(YELLOW_STABLE, 9/24 만료)는 이 작업과 **완전히 독립**이다. `data_gate`가 GREEN이 되고 `core_etf_permission`이 `ALLOWED`가 되더라도, `policy_cap`이 `execution_scope`를 `ETF_ONLY` 이하로 계속 누르고 있을 수 있다 — 이는 정상이며 건드리지 말 것. (단, `ETF_ONLY`는 ETF 매수 자체를 막지 않는다 — `core_etf_permission=ALLOWED`이면 ETF_ONLY scope 하에서도 실제 ETF 매수가 열릴 수 있음. 이것이 이번 작업의 실질적 기대 효과.)
- `actual_buy_allowed`는 반드시 실제 `final_execution_decision.json` 재계산 결과에서 나와야 하며, 하드코딩 금지 (기존 원칙 동일).
- 이번 작업으로 인해 자동매매/자동집행은 발생하지 않는다 — 여전히 사람 승인(`target_write`/`approval_bridge`) 경로만 유효.
- `data/tier2_provenance.json`, `data/tier2_sources.yaml`, `data/tier2_kosis_manual.yaml` 외 다른 데이터 파일은 이 작업에서 건드리지 않는다.

---

## 4. 검증 체크리스트 (보고 시 반드시 포함)

1. 작업 A 결과: discovery가 pmi_kr 정확 일치를 찾았는가? (예/아니오 + 후보 개수 + confidence)
2. (A 실패 시) 작업 B 적용 여부, `verified` 값이 실제로 `true`로 바뀐 시점과 누가 확인했는지
3. `data/tier2_provenance.json`의 `pmi_kr.status`: `stale` → 무엇으로 바뀌었는가 (그대로 `stale`이어도 사실대로 보고)
4. `outputs/data_gate_diagnostics.json`: `data_gate_status` before/after
5. `outputs/core_etf_permission_diagnostics.json`: `core_etf_permission` before/after, `eligible_etf_underweight_count`가 실제 몇 건 매수 가능으로 전환됐는지 (11건 중 몇 건, 0건이면 0건이라고 명시 — 가짜 숫자 금지)
6. `actual_buy_allowed`: before/after (0 → 0일 수도 있음, 그래도 사실대로)
7. `python scripts/verify_claude_review.py` 재실행 결과 (`overall_pass`, blocking_failures)
8. 3번 항목의 절대 금지 파일 mtime 변경 없음 확인
9. 이번 변경이 `execution_scope`/`policy_cap` 자체를 바꾸지 않았음을 명시적으로 확인 (둘 다 여전히 YELLOW_STABLE 캡 기준으로 동작해야 함)

## 5. 실패/부분 성공도 유효한 결과

작업 A, B 모두 실패해도(즉 pmi_kr을 끝내 fresh 상태로 못 만들어도), 그 자체가 "이 차단은 데이터 소스 부재라는 실질적 이유가 있다"는 결론이 되므로 유효한 산출물이다. 억지로 우회하거나 임계값을 낮추는 방식으로 게이트를 통과시키지 말 것.

---

## 6. 실행 결과 (2026-07-09, Cursor)

### 6.1 작업 A — KOSIS tblId 재탐색

| 항목 | 결과 |
|------|------|
| 실행 | `run_kosis_tblid_discovery_pipeline(data, outputs, refresh_after_apply=True)` (~8분) |
| `pmi_kr_kosis_unavailable` | **true** |
| 정확 PMI 후보 (`exact_pmi_candidates`) | **0** |
| 비정확 대안 (`non_exact_candidates`, BSI/경기실사 등) | **10** (confidence=low, 자동 매핑 안 함) |
| `pmi_kr` high-confidence 채택 | **아니오** (`selected=null`) |
| `tier2_sources_applied` | `["cpi_kr_yoy"]` only — **`pmi_kr` 미적용** |
| `data/tier2_sources.yaml` `pmi_kr.tblId` | **여전히 `DT_1C8013`** (무효 ID) |
| 산출물 | `outputs/kosis_tblid_discovery.json`, `outputs/kosis_tblid_candidates.csv`, `outputs/pmi_kr_task_a_discovery_summary.json` |

**판정:** 예상된 결과 — KOSIS에 S&P Global PMI에 해당하는 공식 시리즈 없음. 작업 B로 진행.

### 6.2 작업 B — 수동 확인 경로 (prefill, `verified=false`)

| 항목 | 결과 |
|------|------|
| `data/tier2_kosis_manual.yaml` | prefill 적용: `value=52.1`, `value_date=2026-06-30`, S&P Global 출처 명시 |
| **`verified`** | **`false`** (운영자 재확인 전 — Cursor가 true로 설정하지 않음) |
| `run_pmi_kr_manual_verified_reevaluation()` | `status=manual_required_skipped` — tier2 refresh 미적용 |
| 산출물 | `outputs/pmi_kr_manual_verified_reevaluation.json` 갱신 |

### 6.3 게이트 before/after (작업 B prefill만, verified=false)

| 지표 | before (아침 파이프라인) | after (A+B, verified=false) |
|------|------------------------|----------------------------|
| `pmi_kr` provenance `status` | `stale` | **`manual_required`** (KOSIS fetch 여전히 err21) |
| `data_gate_status` | YELLOW | **YELLOW** (변화 없음) |
| `core_etf_permission` | RESTRICTED | **RESTRICTED** |
| `eligible_etf_underweight_count` | 11 | **11** (0건 전환) |
| `actual_buy_allowed` | 0 | **0** |
| `policy_cap` active | true | **true** (미변경) |
| `execution_scope` | ETF_ONLY / NO_TRADE | **동일** (게이트 완화 없음) |

### 6.4 안전 검증

| 체크 | 결과 |
|------|------|
| `verify_claude_review.py` | **overall_pass=true**, blocking_failures=[] |
| 절대 금지 파일 mtime | `policy_cap.py`, `execution_scope.py`, `execution_guards.py`, `bundle_consistency.py` — **변경 없음** |
| `target_write` / `approval_bridge` | **미연결, write_count=0** |

### 6.5 운영자 다음 단계 (게이트 해소를 원할 때)

1. S&P Global 공식 릴리즈에서 2026-06 PMI **52.1** / 발표일 **2026-07-01** 재확인
2. 확인 후 `data/tier2_kosis_manual.yaml` → `fields.pmi_kr.verified: true`
3. `python -c "from pathlib import Path; from src.validation.pmi_kr_manual_verified_reevaluation import run_pmi_kr_manual_verified_reevaluation; run_pmi_kr_manual_verified_reevaluation(Path('data'), Path('outputs'))"`
4. 이후 **full/standard 파이프라인 재실행**으로 `final_execution_decision.json`의 `actual_buy_allowed`를 실제 재계산 (하드코딩 금지)
5. `core_etf_permission`이 ALLOWED로 바뀌는지 `outputs/core_etf_permission_diagnostics.json`에서 확인 — policy_cap(YELLOW_STABLE)은 별도로 유지될 수 있음
