# alpha_gate YELLOW 원인 조사 명세서 — PIT 펀더멘털 데이터 갭

> 작성: Claude(검증자) · 대상: Cursor · 목적: `data_gate`가 YELLOW에 머무는 원인 중 "고칠 수 있는 부분"만 특정해서 조사/수정.

## 1. 배경 (독립 검증으로 확인된 사실)

`Actual Buy Allowed=0`은 다음 체인으로 발생합니다.

```
data_gate = YELLOW  (portfolio_gate=YELLOW AND alpha_gate=YELLOW 이면 무조건 YELLOW)
  → execution_scope.py: derive_execution_scope()에서 data_gate=="YELLOW" → scope="ETF_ONLY"로 캡
  → core_deployment_throttle.py: _gate_allows_throttle()가 data_gate=="GREEN"을 요구 → YELLOW면 전부 "Wait"
  → execution_scope.py: derive_alpha_permissions()가 ETF_ONLY를 REVIEW_ONLY_ALPHA_SCOPES로 취급 → kr_alpha 신규매수 차단
```

dry_run_days(15)는 이미 요건(10) 충족 — 지금 매수를 막는 이유가 **아님**. 이 문서는 그 사실관계를 바로잡기 위한 조사이지, 실행 게이트를 완화하기 위한 것이 아닙니다.

`portfolio_gate=YELLOW`의 원인은 두 갈래입니다.

- **손대면 안 되는 부분**: `policy_cap_active=true` (BOK FSR 2026-06: FSI 17.2 경고단계, FVI 46.0 > 장기평균 45.7). 실제 매크로 판단이며 다음 재평가는 2026-09-24. **이 조사 범위 밖.**
- **조사 대상**: `input_validation_gate=YELLOW` — 이번 명세서 범위에 포함하되, 원인이 정책 캡과 동일한 파생값이라면(순환 참조) 별도 조치 불필요.

`alpha_gate=YELLOW`의 원인은 `pit_fundamental_gate=YELLOW`이며, 최근 export 기준 `alpha_screening_meta.excluded_summary`에 다음이 잡혀 있습니다.

```
"missing_price": 2,
"stale_data": 1,
"missing_fundamentals": 2
```

(전체 유니버스 2,768종목 중 극소수 — 재무데이터 커버리지 자체는 98% 수준으로 별도 확인됨.)

## 2. 조사 목표

**이 2~3개(missing_fundamentals 2건 + stale_data 1건, 필요시 missing_price 2건도 함께) 종목이 정확히 어떤 티커인지 특정하고, 원인을 분류한다.**

## 3. 조사 단계

1. `outputs/alpha_gate_diagnostics.json` 및 `alpha_screening_meta`를 생성하는 스크리닝 파이프라인(유니버스 필터링 단계, `src/alpha/universe_filter.py` 등)에서 `missing_fundamentals`, `stale_data`, `missing_price`로 분류된 개별 종목 리스트(티커+종목명)를 출력하도록 확인/로깅.
2. 각 종목에 대해 원인 분류:
   - **FIXABLE (수집 실패/버그)**: 정상 상장·거래 중인 종목인데 API 호출 실패, 필드 매핑 오류, 타임아웃 등으로 데이터가 안 들어온 경우.
   - **EXPECTED (정당한 제외)**: 상장폐지, 거래정지, 관리종목 지정, 최근 상장으로 재무제표 미공시 등 — 데이터가 실제로 없는 게 맞는 경우.
3. FIXABLE로 분류된 건만 수정 (재수집 로직, 재시도, 필드 매핑 등). EXPECTED 건은 코드 수정 없이 "정상 제외"로 문서화만 함.
4. `input_validation_gate=YELLOW`의 실제 산출 근거를 `src/validation/gate_detail_builders.py` 흐름에서 확인 — `policy_cap`/`regime` 파생값과 별개의 독립적인 원인이 있는지 확인.
5. 수정 후 재실행하여 `alpha_gate` 및 `data_gate`가 어떻게 바뀌는지 보고. **주의**: `portfolio_gate`는 `policy_cap_active`가 유효한 한(2026-09-24까지) YELLOW로 남을 가능성이 높음 — 이 경우 `data_gate`도 YELLOW로 유지될 수 있음. 이는 실패가 아니라 예상된 결과.

## 4. 절대 금지 사항 (운영자 판단 영역 — 건드리지 말 것)

- `policy_cap_active`, `policy_cap_reason`, BOK FSR 연동 로직 수정 금지.
- `execution_scope.py`의 `derive_execution_scope`, `apply_dry_run_scope_cap`, `derive_alpha_permissions`, `derive_alpha_approval` 임계값/조건 완화 금지.
- `core_deployment_throttle.py`의 `gate_required`, `dry_run_required`, throttle 한도값 조정 금지.
- `execution_guards.py`의 `auto_trading_disabled` 가드 제거/우회 금지.
- 위 항목은 전부 "의도된 안전장치"이며, 이번 조사는 여기 손대는 게 아니라 **alpha_gate의 데이터 누락 원인만** 다룹니다.

## 5. 보고 형식 (요청)

| 티커 | 종목명 | 분류 (FIXABLE/EXPECTED) | 원인 | 조치 | 재검증 결과 |
|---|---|---|---|---|---|

수정 여부와 무관하게, 위 표와 함께 "수정 후 alpha_gate/data_gate 최종 상태"를 함께 보고해 주세요.
