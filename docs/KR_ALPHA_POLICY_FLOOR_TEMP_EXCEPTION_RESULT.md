# kr_alpha 정책 하한 — 한시 예외 RESULT

> SPEC: [`KR_ALPHA_POLICY_FLOOR_TEMP_EXCEPTION_SPEC.md`](KR_ALPHA_POLICY_FLOOR_TEMP_EXCEPTION_SPEC.md)  
> 선행: [`KR_ALPHA_HYBRID_TRANSITION_RESULT.md`](KR_ALPHA_HYBRID_TRANSITION_RESULT.md) 시나리오 B  
> 원칙: **하한 숫자 미변경** · 예외 메타/주석·로드맵만. `target_portfolio.csv` **미수정**.

## 한줄 결론

`kr_alpha_min: 20` / `kr_alpha_overlay_min_pct: 15.0`은 **그대로** 두고, 승인 목표 6%는 yaml **한시 예외 메타**로만 기록했다. 리뷰 트리거(forward-return 60~120일 충족, 잠정 2026 Q4)에 재결정이 없으면 **예외 실효 → 원 하한 복귀**. 코드는 현재 하한을 강제하지 않아 **이번 스펙에서 로직 변경 없음**(후속 선택).

---

## 1. yaml 반영 내역

| 파일 | 하한 키 | 숫자 | 추가 메타 |
|---|---|---:|---|
| `data/portfolio_policy.yaml` | `risk_limits.kr_alpha_min` | **20** (미변경) | `kr_alpha_min_temp_exception` |
| `data/absolute_return_policy.yaml` | `portfolio_structure.kr_alpha_overlay_min_pct` | **15.0** (미변경) | `kr_alpha_overlay_min_temp_exception` |

공통 메타 필드:

| 필드 | 값 |
|---|---|
| `active` | true |
| `approved_target_pct` | 6.0 |
| `reason` | KR_ALPHA_HYBRID_TRANSITION_RESULT scenario B (2026-07-16) |
| `start_date` | 2026-07-16 |
| `review_trigger` | `alpha_grade_forward_return.csv` / `hakedaka_forward_return_tracker.csv`에 forward_return_60d~120d **실제 채워짐** |
| `review_window_provisional` | 2026-Q4 (Oct–Dec 2026) |
| `lapse_if_unreviewed` | 트리거 충족·미재검토 시 **예외 실효**, 원 하한(20 / 15.0)이 다시 유효 — 예외가 silent default가 되지 않음 |

`domestic_beta_note`는 **미수정**(시나리오 B·069500 미도입).

---

## 2. 코드가 예외를 인식하는가? (SPEC §2-3)

| 위치 | 동작 | 예외 인식 |
|---|---|---|
| `src/risk_limits.py` | `kr_alpha_min`을 **읽기만** 하고, 하한 미만 **위반을 만들지 않음**(max만 HARD) | N/A — 강제 없음 |
| `src/policy_cap.py` | `overlay_min` / `kr_alpha_min` **미참조** | N/A |
| 기타 `src/**/*.py` | `kr_alpha_overlay_min_pct` **소비처 없음** | N/A |

**결론:** 현재 런타임은 목표 6%를 “하한 위반 에러/강제 리밸”로 올리지 않는다. 이번 스펙 범위의 **문서화만으로 운영 차단 리스크는 없음**.  
향후 UI·acceptance가 하한을 읽어 경고를 내기 시작하면, `*_temp_exception.active` + `lapse_if_unreviewed`를 읽는 **후속 스펙**이 필요(본 RESULT에서는 코드 변경 안 함).

---

## 3. 로드맵 갱신

`docs/KR_ALPHA_STRATEGY_ROADMAP.md`:

- 「결정된 다음 단계」에 시나리오 B · 한시 예외 · approval_bridge 순서 반영
- **10~20% 확대안 철회·종결** 섹션 추가(사유: 심리적 만족 vs 검증 엣지 불일치, 단일종목캡·희석 우려)
- 절대 금지에 “예외 방치 금지 / 미재검토=원 하한 복귀” 추가
- 최근 갱신에 본 RESULT 링크

---

## 4. 절대 금지 준수

| 항목 | 상태 |
|---|---|
| 하한 **숫자** 변경 | **하지 않음** (20 / 15.0 유지) |
| `target_portfolio.csv` 수정 | **하지 않음** |
| 리뷰 시점 없는 예외 문구 | **작성하지 않음** (`lapse_if_unreviewed` 포함) |

---

## 5. 검증 체크리스트

1. 하한 숫자 미변경: yaml load로 `20` / `15.0` 확인 — **통과**.  
2. 예외에 리뷰 트리거·잠정 Q4·미재검토 시 원정책 복귀 문구: **포함**.  
3. 로드맵에 10~20% 확대안 철회: **포함**.  
4. target 미변경: **준수**.

## 6. 다음

원장 RESULT 검증 후 → **`approval_bridge`로 시나리오 B target draft 반영**.
