# 레짐 격차 지속일 에스컬레이션 — 구현 결과

> 명세: `docs/REGIME_DIVERGENCE_ESCALATION_SPEC.md`  
> 선행: `docs/REGIME_OVERRIDE_DIVERGENCE_ALERT_RESULT.md` (AC-05b)

## 구현 요약

**B안(지속일 기반 재촉)**만 구현. 뉴스 자동 반영 파이프라인은 범위 외.

| 항목 | 내용 |
|------|------|
| 로그 | `outputs/regime_divergence_log.jsonl` — 일별 `date/computed/applied/gap/override_active` append, **동일 date 중복 스킵** |
| 카운트 | `count_consecutive_divergence_days()` — 최신일 역순, `override_active ∧ gap≥warn_gap` 연속 일수 |
| 에스컬레이션 | 연속 **≥3일**(기본) 시 메시지에 `N일째 지속` + `recommended_review_by`(as_of+2일) |
| 설정 | `compass_rules.yaml` → `override_divergence_escalation_days: 3`, `override_divergence_review_buffer_days: 2` |
| 연동 | `assess_regime_divergence_with_persistence()` → AC-05b, `system_health.regime_computed` |

## 불변 (명세 준수)

- `regime_expires_date`(예: 2026-09-24) **변경 없음**
- 오버라이드 자동 해제 없음
- `status`는 여전히 `warn`만 — `fail`/실행 차단 없음
- **과거 날짜 소급 채우기 금지** — 로그 시작 시점부터 정직하게 카운트 (dry-run과 동일 원칙)

## 검증

`tests/test_regime_override_divergence.py` — **13 passed**

1. 합성 로그 3일 연속 gap≥2 → 에스컬레이션 + `recommended_review_by=2026-07-14` ✓  
2. 중간 gap<threshold 또는 override 비활성 → 카운트 리셋 ✓  
3. 로그 없음/1일 → 기존 AC-05b warn만, 에스컬레이션 없음 ✓  
4. AC-05 시간 기반 회귀 ✓  
5. 동일 date 중복 append 스킵 ✓  

## 라이브 한계 (명시)

현재 라이브(override 2026-06-24~)는 **로그가 오늘부터 쌓이므로** 첫 실행은 연속 1일, 3일째 실행부터 에스컬레이션 메시지가 뜹니다. 6월부터 소급 반영하지 않습니다.

## 다음 (운영)

- 매일 `실행.bat` / standard 파이프라인 3회 이상 연속 실행 후 AC-05b 메시지에 `N일째 지속` 확인
- 필요 시 `override_divergence_escalation_days`만 조정 (게이트 로직은 그대로)
