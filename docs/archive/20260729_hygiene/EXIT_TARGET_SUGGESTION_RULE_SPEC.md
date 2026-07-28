# 익절 목표 제안값 계산기 — role+ROE 2요인 규칙 (경량)

> 배경: `data/kr_alpha_exit_targets.yaml`의 7종 초기값(2026-07-15)은 채팅 중 role 태그와 현재 ROE 수준을 함께 판단해 정한 것. 재구성해보니 **role 하나만으로는 재현 안 됨**(코웨이·오리온이 같은 role인데 ROE 수준 차이로 FUND leg 포함 여부가 갈림, KT는 role상 예외 처리). 신규 kr_alpha 종목 편입 시마다 매번 대화로 다시 정하지 않도록, **실제로 쓴 2요인 로직을 그대로 규칙화**.
> 원칙: 이 규칙은 **숫자를 "더 정확하게" 만드는 게 아니라 "일관되게 재현 가능하게" 만드는 것.** 배수·버퍼 자체는 여전히 검증 안 된 임의값 — `EXIT_TARGET_STATUS_MARKER_SPEC` 등 기존 "자동 목표산정 금지" 원칙과 동일하게, 계산 결과는 **제안값**일 뿐 yaml에 자동 기입되지 않음.

## 1. 규칙 정의

### 규칙 A — PBR_max 배수 (role 기준)
| role | 배수 |
|---|---|
| quality_dividend, quality_defensive | ×1.2 |
| shareholder_return, dividend_value | ×1.3 |
| value_rerating | ×1.6 |
| 그 외(defensive_consumer 등 미분류/왜곡 가능 role) | **제안 안 함** — "role 배수 규칙 부적용, 수동 판단 필요" 표시 (SK하이닉스 케이스처럼 사이클·특수 상황 배제 목적) |

`suggested_pbr_max = round(current_pbr * 배수, 2)`

### 규칙 B — FUND leg 포함 여부 (role + ROE 2요인)
1. `role == "quality_dividend"` → **FUND 생략** (성숙 배당주, 개선 스토리 가정 안 함)
2. `role == "value_rerating"` → **FUND 포함** (재평가 스토리 자체가 펀더멘털 개선 전제)
3. 그 외 role → `현재 ROE < roe_threshold(기본 13.0)`이면 **FUND 포함**, 아니면 **생략**
4. 규칙 A에서 "제안 안 함"으로 분류된 role(예: defensive_consumer)은 FUND도 함께 **제안 보류**

FUND 포함 시: `suggested_roe_min = round(current_roe + roe_buffer(기본 2.5), 1)`

### 검증 — 기존 7종 재현
| 티커 | role | ROE | 규칙 A 결과 | 규칙 B 결과 | 기존 yaml과 일치 |
|---|---|---|---|---|---|
| KT | quality_dividend | 9.72 | ×1.2 → 0.86 | 생략(규칙1) | ✅ |
| 코웨이 | quality_defensive | 16.9 | ×1.2 → 2.24 | 생략(13 이상) | ✅ |
| DB손해보험 | shareholder_return | 16.5 | ×1.3 → 1.20 | 생략(13 이상) | ✅ |
| 동원산업 | dividend_value | 11.0 | ×1.3 → 0.53 | 포함, roe_min 13.5 | ✅ |
| 오리온 | quality_defensive | 10.05 | ×1.2 → 1.57 | 포함, roe_min 12.5 | ✅ |
| SNT홀딩스 | shareholder_return | 9.65 | ×1.3 → 0.70 | 포함, roe_min 12.0 | ✅ |
| 현대지에프홀딩스 | value_rerating | 10.3 | ×1.6 → 0.86 | 포함(규칙2), roe_min 12.5 | ✅ |
| SK하이닉스 | defensive_consumer | 36.12 | 제안 안 함 | 제안 보류 | ✅ (이미 미설정 유지 중) |

7종 전부 기존 값과 일치, SK하이닉스도 동일하게 배제됨 — 규칙이 실제 판단을 정확히 재현.

## 2. 구현 범위
- `src/alpha/exit_target_worksheet.py`에 `suggest_exit_targets(role, roe, pbr, *, roe_threshold=13.0, roe_buffer=2.5) -> dict` 함수 추가 — 위 규칙 A·B 그대로 구현
- 워크시트에 컬럼 추가: `suggested_roe_min`, `suggested_pbr_max` (기존 `target_roe_min`/`target_pbr_max`는 **여전히 빈 칸 유지** — 사람이 최종 입력하는 자리, 절대 자동 채움 금지)
- 신규 kr_alpha 종목이 워크시트에 나타날 때마다 이 제안값이 자동 계산되어 참고용으로 뜸

## 3. 절대 금지
- `suggested_*` 값을 `target_*`(yaml에 실제 반영되는 값) 컬럼에 자동 복사 금지 — 사람이 보고 별도로 yaml에 입력
- 배수(1.2/1.3/1.6)·버퍼(2.5)·임계값(13.0)을 "검증된 값"으로 문서화하지 말 것 — 전부 재현성 목적의 임의 정책이라고 주석에 명시
- role이 규칙 A/B에 없는 새 값이면 반드시 "제안 안 함"으로 처리 — 임의 fallback(예: 기본 배수 적용) 금지

## 4. 검증 요청
1. 위 8종 재현 표와 실제 함수 출력이 일치하는지 (SK하이닉스는 "제안 안 함")
2. 워크시트에 `suggested_roe_min`/`suggested_pbr_max` 컬럼이 뜨고, `target_roe_min`/`target_pbr_max`는 여전히 공란인지
3. role이 4개 카테고리 밖의 새 값일 때 "제안 안 함"으로 안전하게 처리되는지 (KeyError 없이)
