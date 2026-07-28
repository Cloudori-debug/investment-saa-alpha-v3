# 레짐 재분류 (YELLOW_STABLE → CAUTION) — 실행 승인 명세서

> 근거: AC-05b 에스컬레이션 발동(2026-07-14, 연속 3일, 재확인 기한 2026-07-16) 후 원장님 직접 판단.
> 판단 근거: KOSPI만 -24.3% 급락, 나머지 4개 교차자산 지표(S&P500 -1.2%, VIX 17.2 평온, USD/KRW 1491 안정, 외국인 수급 중립)는 전부 평온 — 전방위 시스템 위기가 아니라 KOSPI 국지적 하락으로 판단, 컴퓨티드 CRISIS와 기존 YELLOW_STABLE의 절충 레벨인 **CAUTION**으로 재분류하기로 결정.
> 원칙 불변: 이건 override 값을 사람이 재검토해서 바꾸는 것이지, 자동 완화/해제가 아님.

## 1. 사전 발견 — 반드시 먼저 고쳐야 하는 버그

`src/policy_cap.py::fsr_policy_permissions()`가 `"YELLOW" in cap_regime.upper()`로만 분기합니다. `_POLICY_MAX_SCOPE` 테이블에서는 `CAUTION`이 `YELLOW_STABLE`과 동일하게 `ETF_ONLY` 캡을 받는데도, `fsr_policy_permissions()`는 CAUTION일 때 **빈 딕셔너리**를 반환합니다.

`src/execution_permissions.py::build_execution_permissions()` 131행 `if policy_perms:` 블록이 스킵되면서:
- 출력에 `policy_permissions` 상세(etf_new_buy/etf_chase_buy/kr_alpha_trim 등)가 아예 안 실림 — 리포트에서 세부 권한 정보 소실.
- `ETF_CHASE_BUY`가 `blocked_capabilities`에 명시적으로 추가되는 유일한 경로가 이거라, CAUTION에서는 이 capability가 "허용 목록에도 없고 차단 목록에도 없는" 애매한 상태가 됨.

**반드시 이 재분류보다 먼저 고칠 것.** `fsr_policy_permissions()`가 `CAUTION`도 `YELLOW_STABLE`과 동일한 권한 셋을 반환하도록 조건을 확장(`regime_key in {"YELLOW_STABLE", "CAUTION"}` 방식, `_normalize_regime_key`/`_POLICY_MAX_SCOPE`와 정합되게).

## 2. 승인된 작업 범위

### A. 권한 함수 수정 (선행)

`fsr_policy_permissions(cap_regime)`이 YELLOW_STABLE·CAUTION 둘 다에 대해 동일한 권한 딕셔너리를 반환하도록 수정. (RISK_OFF/CRISIS는 이번 범위 아님 — 현재 `_POLICY_MAX_SCOPE`가 이미 NO_TRADE로 별도 처리하므로 급하지 않음, 원한다면 후속 과제로 남김.)

### B. `market_indicators.csv` 최신 행 갱신 (감사 로그 남는 경로로)

| 필드 | 새 값 |
|---|---|
| `regime` | `CAUTION` |
| `regime_override_reason` | "KOSPI만 국지적 급락(-24%+), S&P500/VIX/USDKRW/외국인수급 등 교차자산 지표는 평온 — 전방위 시스템 위기 신호 아님. 컴퓨티드 CRISIS와 기존 YELLOW_STABLE의 절충 레벨로 재분류. AC-05b 에스컬레이션(2026-07-14) 대응." |
| `regime_set_date` | `2026-07-14` |
| `regime_expires_date` | `2026-08-14` (제안 — 기존 3개월 고정 관행 대신 1개월로 단축, 각도②에서 확인한 장기 고정일 리스크 반영. 원장님 확인 후 조정 가능) |

CSV 직접 편집 금지 원칙은 이 파일에는 기존에도 적용 안 됐던 수동 입력 필드이므로(시장지표 CSV는 애초에 사람이 입력하는 파일), 이번엔 직접 값 갱신 허용. 다만 변경 이력이 `market_indicators_history.csv` 또는 동등 로그에 남는지 확인할 것.

## 3. 절대 금지 (변경 없음)

- `_POLICY_MAX_SCOPE` 테이블 값 자체 — CAUTION은 여전히 ETF_ONLY 캡(YELLOW_STABLE과 동일), 이번 재분류로 오늘 당장 execution scope나 Actual Buy Allowed가 바뀌지 않음 — 그 점을 검증 보고에 명시할 것.
- `_manual_regime_effective()`의 만료 폴백 로직, A(policy_cap 만료 처리) 로직 — 지난 스펙에서 이미 구현·검증됨, 이번엔 값만 갱신.
- override 자동 해제/자동 갱신 로직 신설 금지.

## 4. 검증 요청

1. A 수정 후: `fsr_policy_permissions("CAUTION")`와 `fsr_policy_permissions("YELLOW_STABLE")`이 동일한 딕셔너리를 반환하는지 단위 테스트.
2. B 반영 후 재실행: `AC-05` 경과일이 0(오늘 갱신)으로 리셋되는지, `AC-05b`의 `consecutive_divergence_days`가 리셋되고 `gap`이 3→2로 줄어드는지(CRISIS severity4 vs CAUTION severity2), `escalated`가 다시 `false`로 돌아오는지 확인.
3. `saa_profiles.yaml`의 `taa_tilts.CAUTION` 적용 결과로 kr_alpha 그룹 목표비중이 실제로 변하는지(약 -5%p 방향) 확인하고 `target_portfolio.csv` diff를 보고에 포함.
4. execution_scope/Actual Buy Allowed가 오늘 기준 그대로인지(ETF_ONLY 캡 불변) 재확인 — 바뀐다면 그 이유를 반드시 별도 설명.
5. `market_indicators_history.csv`(또는 동등 로그)에 이번 갱신 이력이 남는지 확인.
