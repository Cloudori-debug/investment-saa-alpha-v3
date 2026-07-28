# 레짐 재분류 (YELLOW_STABLE → CAUTION) — 결과

> 명세: `docs/REGIME_CAUTION_RECLASSIFICATION_SPEC.md`  
> 실행일: 2026-07-14  
> 원칙: 사람 재분류(AC-05b 대응). 자동 완화/해제 아님.

## 1. 선행 버그 수정

| 항목 | 내용 |
|------|------|
| 파일 | `src/policy_cap.py::fsr_policy_permissions` |
| 변경 | `_normalize_regime_key` 후 `{"YELLOW_STABLE","CAUTION"}` 동일 권한 dict |
| 테스트 | `test_fsr_policy_permissions_caution_matches_yellow` |

검증: `fsr_policy_permissions("CAUTION") == fsr_policy_permissions("YELLOW_STABLE")` → True.  
`ETF_CHASE_BUY`가 `blocked_capabilities`에 포함됨.

## 2. 시장지표 재분류

| 필드 | 값 |
|------|-----|
| `regime` | `CAUTION` |
| `regime_set_date` | `2026-07-14` |
| `regime_expires_date` | `2026-08-14` (1개월 제안; 원장 조정 가능) |
| 근거 | KOSPI 국지 급락·교차자산 평온 → CRISIS와 YELLOW_STABLE 절충 |

`data/market_indicators.csv` 및 `data/market_indicators_history.csv` 동일 일자 행 반영.

## 3. 검증 (명세 §4)

| # | 항목 | 결과 |
|---|------|------|
| 1 | CAUTION≡YELLOW 권한 dict | **pass** |
| 2 | AC-05 / AC-05b | AC-05 **pass**(설정일=오늘). gap **3→2**. consecutive **리셋→1**, escalated **false** |
| 3 | TAA kr_alpha | `regime_tilt=-5` → allocation **final 20.66%**. 운영 `target_portfolio.csv` kr_alpha 합 **23.63% 유지**(가드·사람 승인만) |
| 4 | scope / Actual Buy | **ETF_ONLY** 불변, Actual Buy **0** |
| 5 | history | 2026-07-14 CAUTION / set·exp 기록됨 |

부수: divergence 로그 **당일 upsert** + `applied_regime` 변경 시 consecutive 에피소드 끊기  
(`src/validation/regime_override_divergence.py`). 당일 행을 CAUTION/gap=2로 갱신.

## 4. 라이브 스냅샷 (2026-07-14)

- compass: computed=`CRISIS`, applied=`CAUTION`, override active  
- policy_cap: CAUTION → ETF_ONLY  
- AC-05b: gap=2, consecutive_days=1, escalated=false (warn은 gap≥2로 유지)

## 5. 금지 준수

- `_POLICY_MAX_SCOPE` 미변경  
- override 자동 해제 로직 미신설  
- `data/target_portfolio.csv` 자동 미반영 (의도됨 — 사람 승인 필요)
