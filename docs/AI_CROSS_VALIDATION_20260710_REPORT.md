# AI 교차 검증 보고서 — 2026-07-10 09:20 번들

> 검증자: Claude (독립 검증) · 대상 번들: `ai_cross_validation_20260710_0920.zip`
> as_of: 2026-07-09 · run_id: 2026-07-10T09:12:30+09:00 (승인 후 STANDARD 자동재실행 결과물)

## 종합 판정: **WARN**

핵심 발견: 오늘 시스템이 평소(`ETF_ONLY` 캡)보다 더 엄격한 **`NO_TRADE` 완전 잠금** 상태이고, 원인은 `target_guard_conflict_detected=True`입니다. `daily_report.md`는 이를 정확히 밝히고 있으나, **`acceptance` 요약(operational_verdict)과 `export_bundle_validation.json`의 자체 정합성 체크는 이 사실을 서로 다르게(또는 아예 누락) 보고**합니다. 코드 안전장치(fail-closed NO_TRADE)는 정상 작동 중이라 실행 리스크는 없지만, 보고서 간 정합성 문제이므로 WARN입니다.

---

### 데이터

- `system_health`: 36 pass / 1 warn / 0 fail — `pmi_kr` tier2 provenance stale 1건(기존에 알려진 이슈, 미해결 지속)
- Compass Tier1 필드 결측 없음, tier2 7/7 입력(단 `pmi_kr`은 fallback값 51.2 유지 — P6에서 준비한 수동값 52.1은 `verified=false`라 아직 미적용, 설계대로)
- Alpha: 재무 커버리지 98%(2650/2696), kr_alpha 운용 필수 시세/재무 결측 0건 — 문제 없음

### 레짐·배분

- `computed_regime=CRISIS`(KOSPI 고점대비 -20.0% drawdown) vs `applied_regime=YELLOW_STABLE`(수동 override, 만료 2026-09-24, D-77) — 기존과 동일한 정상 override 상태
- `policy_cap.active=true`, 근거는 BOK FSR 문구 그대로 유지 — 임의 변경 없음 확인

### Alpha

- `alpha_screening_meta`: universe 2768 → scored 260 → B등급 42 (B universe 상위 30 export) · Top30 · Replace 20건, 전부 `buy_permission=false` 일치 (모순 없음)
- Replace 후보 대체 근거: SNT홀딩스(036530, 하케다카 보유종목) 등 기존 보유분에 대해 cross-sector 대체 후보 제시 — 근거 자체는 합리적(등급·점수 순)
- `alpha_report_md.md`의 "Buy-ready" 라벨: 지난 세션에서 고친 `alpha_auto_buy 승인 필요(현재 BLOCKED)` 문구가 7건 전부에 정상 적용되어 있음 — **이전 수정 사항이 실제 이번 리포트에도 유지되는 것 확인**
- `alpha_screening_meta.buy_permission_status=BLOCKED`와 모든 후보 `buy_permission=false` — 100% 일치

### Alpha v2 Shadow

- KOSPI 4 / KOSDAQ 1 — KOSDAQ 과다 아님
- flow_score 기여도(예: 하나금융지주 총점 55.45→71.45, +16)가 있으나 등급(C) 자체를 뒤집지는 않음 — 수급 과반영으로 보기 어려움
- `policy_notes`에 "Flow signal is not buy permission" 등 디스클레이머 전부 포함 확인
- trim_watch 101건 — 근거(`pension_net_buy_20d<0`, `grade_downgrade` 등) 명시적, "Buy Watch"와 혼동될 표현 없음
- profit_sweep 후보 0건 — 이상 없음

### 실행 리스크 — 핵심 이슈

| 소스 | `target_guard_conflict` 관련 표기 |
|---|---|
| `daily_report.md` (authoritative 블록) | **`target_guard_conflict_detected: True`**, "Main block reason: target_guard_conflict_detected", Actual Buy Allowed=0 (guard conflict lock) |
| `export_bundle_validation.json` → `alignment.target_guard_conflict` | `conflict_detected: **false**`, `guard_fail: false`, `health_severity/acceptance_severity/final_severity: PASS` |
| `acceptance.items` (AC-01~AC-10) | **target_guard_conflict를 다루는 항목이 아예 없음** — `AC-01c target_portfolio_guard`는 별개 체크(target CSV 승인-hash 일치, PASS)이고 이 이슈와 무관 |
| `acceptance.operational_verdict` | "Overall YELLOW · Scope ETF_ONLY ... Policy cap: YELLOW_STABLE" — **guard conflict 언급 없이, 마치 policy_cap 캡만 있는 것처럼** 서술 |
| `bundle_consistency_validation.diagnostics_verify.warnings` | `"no_action_verify:status_alignment_pass_false"` — 관련 신호는 있으나 원인 문구가 다름 |

**해석**: `daily_report.md`는 사실대로 정확히 보고하고 있어 운영자가 이 문서를 읽으면 오해할 여지가 없습니다. 문제는 **`acceptance` 요약과 `export_bundle_validation`이 서로 다른 결론(guard 정상 vs guard 위반)을 내리고, 그 중 어느 쪽도 daily_report.md와 명시적으로 맞춰보지 않는다는 점**입니다. `acceptance`만 보고 판단하면 "정책 캡 때문에 ETF만 제한적으로 가능하다"로 오인할 수 있는데, 실제로는 오늘 **ETF 매수를 포함한 모든 신규 실행이 완전히 잠겨 있습니다(NO_TRADE)**. 실행 자체는 fail-closed로 안전하게 막혀 있어 리스크는 없지만, 세 문서 중 정확히 무엇이 최신/최종 판단인지 교차 확인 없이는 운영자가 혼동할 수 있습니다.

---

## 권고 (사람 승인 전)

### Cursor 조치 대상 (조사·수정)
1. `export_bundle_validation.py`(또는 해당 정합성 계산 모듈)에서 `target_guard_conflict.conflict_detected`를 **어떤 입력**으로 계산하는지, `final_execution_decision.json`의 `target_guard_conflict_detected`와 왜 다른 결과가 나오는지 근본 원인 조사·보고. (섣불리 값을 맞추기 위한 수정 금지 — 원인 파악 후 어느 쪽이 최신/정확한지 먼저 확인)
2. `acceptance` 생성 로직에 `target_guard_conflict_detected=True`일 때 별도 AC 항목(예: `AC-11 target_guard_conflict`) 또는 `operational_verdict` 문구에 이를 반영하는 방안 검토·제안 (즉시 구현 전 설계만 먼저 제시)

### 운영자 판단 대상 — Cursor 조치 아님
- 오늘은 `daily_report.md` 기준 **완전 NO_TRADE**임을 그대로 받아들이고 대기. 실행 리스크 없음(안전장치 정상)
- `pmi_kr` 수동값(`verified=false`) 확정 여부는 여전히 동준님 판단 대기 상태

---

## Cursor 조사 결과 (2026-07-10)

### 1. 근본 원인 — **확정**

**두 개의 다른 신호가 같은 이름으로 혼용되고, reconcile 중 transient mismatch가 sticky lock을 남깁니다.**

| 신호 | 의미 | 오늘 번들 값 |
|---|---|---|
| `detect_target_guard_conflict().conflict_detected` | health / acceptance / final **guard severity·hash·snapshot** 정합성 | **False** (전부 PASS) |
| `final_execution_decision.target_guard_conflict_detected` | **실행 잠금 플래그** (NO_TRADE fail-closed) | **True** (sticky) |

#### 재현 경로 (코드·실측 일치)

1. **타겟 승인 직후** `refresh_bundle_after_target_write()` → `reconcile_bundle_artifacts()` 실행.
2. Reconcile 초반(약 L601)에서 `detect_target_guard_conflict()` 호출 시:
   - `system_health.json` / `acceptance_report.json`은 **방금 stamp된 새 `health_snapshot_id`** 사용
   - **`ai_export_bundle.json`은 아직 디스크에 있는 이전 run 스냅샷** (`bundle_snap` 비교, L292–300)
   - → `snapshot_mismatch=True` → `conflict_detected=True` (**guard severity는 전부 PASS여도**)
3. L631 `apply_target_guard_conflict_lock()` → `target_guard_conflict_detected=True` sticky 설정.
4. L711–722에서 bundle **재빌드 후** L724 `verify_bundle_snapshot_alignment()` 재호출 → 이때는 `conflict_detected=False`.
5. **Lock 해제 로직 없음** — post-alignment 구간(L724–756)은 hash misalignment용 `snapshot_stale_lock`만 처리, conflict clear는 L639 `elif sticky` 분기인데 L631에서 이미 lock이 걸려 해당 분기 미진입.
6. 이후 STANDARD run(`09:12:30`)의 `final_decision_core`는 `target_guard_conflict_detected` 필드를 **새로 쓰지 않음** → reconcile이 다시 lock을 적용하면 sticky 유지.

**실측 검증 (outputs/):**

```
detect_target_guard_conflict().conflict_detected  → False
final.target_guard_conflict_detected              → True
acceptance.execution_scope                        → ETF_ONLY
no_action_diagnostics.status_alignment            → acceptance=ETF_ONLY != authoritative=NO_TRADE
decision_log bundle_reconciliation (09:12:30)     → conflict_detected: true (reconcile 시점 transient)
export_bundle_validation.alignment.target_guard_conflict → conflict_detected: false (export 시점 settled)
```

**시뮬레이션:** health/acceptance에 새 snapshot_id를 부여하고 bundle은 그대로 두면 `conflict_detected=True, snapshot_mismatch=True` 재현됨.

#### 부가 관찰

- `acceptance_report.json`에 `health_snapshot_id` 필드가 **파일에 persist되지 않음** (reconcile in-memory에는 설정, `AcceptanceReport.to_dict()` 스키마에 없음). export validation의 `acceptance_snapshot_id: ""` 원인.
- `bundle_reconcile` **full reconcile은 실행됨** (manifest `cache_hit_count: 0`). 이번 케이스는 cache fast path가 아니라 **mid-reconcile bundle lag** 문제.
- `always_checks_pass: false` (`no_action_verify:status_alignment_pass_false`) — authoritative NO_TRADE vs acceptance ETF_ONLY 불일치를 diagnostics는 잡지만 acceptance 요약은 미반영.

### 2. 어느 문서가 “정확”한가

| 문서 | 판단 |
|---|---|
| **`daily_report.md` authoritative 블록** | **정확** — `green_layers` + `final.target_guard_conflict_detected` sticky lock → Actual Buy Allowed=0, NO_TRADE |
| **`export_bundle_validation.alignment.target_guard_conflict`** | guard artifact 정합성만 반영 — **실행 잠금 상태와 불일치 가능** (오늘 그 사례) |
| **`acceptance.operational_verdict`** | policy_cap + scope 기준 문구 — **conflict lock·authoritative NO_TRADE 미반영** (설계 공백) |

**운영 권고:** 실행 여부 판단은 **`daily_report.md` authoritative 블록** 또는 `final_execution_decision.target_guard_conflict_detected` + `actual_buy_allowed=0` 기준. acceptance 요약만으로는 ETF 리밸런싱 가능으로 **오인하면 안 됨**.

### 3. 설계 제안 (구현 전 — 사람 승인 필요)

#### A. Reconcile lock lifecycle (bundle_consistency.py — **승인 후**)

1. **Post-bundle rebuild re-detect:** L722 `write_ai_export_json` 직후 `detect_target_guard_conflict()` 재호출. `conflict_detected=False`이면 `apply_target_guard_conflict_lock(final, conflict)`로 **sticky clear** (L639 로직과 동일, 이미 clear 동작 검증됨).
2. **Mid-reconcile detect에서 bundle_snap 제외 (대안):** reconcile 내부 호출(L601)에 `skip_bundle_snapshot=True` 옵션 — bundle이 같은 pass에서 rebuild될 예정이므로 transient mismatch 무시.
3. **`acceptance_report`에 `health_snapshot_id` persist** — `AcceptanceReport.to_dict()` 또는 reconcile write 경로에 필드 추가.

#### B. Export gate 교차 검증 (ai_export.py — **승인 후**)

`validate_export_bundle_readiness()`에 **cross-check** 추가:

```python
final_flag = bool(final.get("target_guard_conflict_detected"))
detect_flag = bool(alignment["target_guard_conflict"]["conflict_detected"])
if final_flag != detect_flag:
    failures.append(
        f"target_guard_conflict mismatch: final={final_flag} vs detect={detect_flag}"
    )
```

→ 번들 export 시 불일치를 **fail-closed**로 표면화 (값을 억지로 맞추지 않음).

#### C. AC-11 `target_guard_conflict` (acceptance_check.py — **승인 후**)

| 필드 | 제안 |
|---|---|
| id | `AC-11` |
| name | `target_guard_conflict_lock` |
| status | `fail` if `final.target_guard_conflict_detected` **or** `detect.conflict_detected` |
| scope | `ops` |
| message | `target_guard_conflict_detected=True — NO_TRADE lock active` / `guard snapshot mismatch across artifacts` |

`operational_verdict` 보강 (lock active 시):

```
"Overall YELLOW · Authoritative NO_TRADE (target_guard_conflict lock) · "
"Display scope ETF_ONLY — ETF_ONLY는 ETF 매수 허가가 아님 · Actual Buy Allowed=0"
```

`resolve_authoritative_execution()`의 `force_no_trade` 조건에 `final_doc.get("target_guard_conflict_detected")` 추가 검토 (authoritative scope 일원화).

#### D. 변경 금지 영역 준수

- `policy_cap.py`, `execution_scope.py`, `execution_guards.py`, target write / approval_bridge — **미변경**
- fail-closed 방향 유지: 불확실 시 lock 유지 > premature unlock

### 4. 즉시 조치 없음 — 운영 상태

- 실행 차단은 **의도대로 fail-closed** 동작 중.
- 코드 수정은 위 설계안 **사람 승인 후** 착수.
