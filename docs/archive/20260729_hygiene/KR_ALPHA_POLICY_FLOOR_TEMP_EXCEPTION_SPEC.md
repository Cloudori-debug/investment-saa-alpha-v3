# kr_alpha 정책 하한 — 한시 예외 적용 (실행 명세서)

> 선행: [`KR_ALPHA_HYBRID_TRANSITION_RESULT.md`](KR_ALPHA_HYBRID_TRANSITION_RESULT.md) §2.4·§7-2
> 원장 결정(2026-07-16): **10~20% 재검토 논의 철회, kr_alpha=6%(시나리오 B) 원안 확정.** 정책 하한은 **영구 변경이 아니라 한시 예외**로 처리.
> 원칙: 이 스펙은 **예외 근거·문서화까지만**. `approval_bridge` 승인 전까지 `target_portfolio.csv` 실변경 없음.

## 1. 대상 하한 2건

| 문서 | 키 | 현재값 | kr_alpha 제안(6%)과 |
|---|---|---:|---|
| `data/portfolio_policy.yaml` | `risk_limits.kr_alpha_min` | 20 | 충돌 |
| `data/absolute_return_policy.yaml` | `portfolio_structure.kr_alpha_overlay_min_pct` | 15.0 | 충돌 |

## 2. 한시 예외 방식 (영구 변경 아님)

1. **yaml 하한 숫자 자체는 그대로 둔다** — `kr_alpha_min: 20`, `kr_alpha_overlay_min_pct: 15.0` 유지.
2. 대신 각 파일에 **예외 주석/필드**를 추가해, "현재 kr_alpha 목표 6%는 이 하한에 대한 승인된 한시 예외"임을 명시:
   - 예외 사유: `KR_ALPHA_HYBRID_TRANSITION_RESULT.md` 절충안(시나리오 B) 채택
   - 예외 시작일: 2026-07-16
   - **리뷰 시점(고정)**: forward-return 추적 데이터(`alpha_grade_forward_return.csv`/`hakedaka_forward_return_tracker.csv`)의 60일~120일 forward_return이 실제로 채워지는 시점 — 현재 데이터 상태 감안 **2026년 10~12월경**으로 잠정 명시하되, 실제 데이터 충족 여부로 재확인.
   - 리뷰 시 판단 대상: kr_alpha 6% 유지 / 하한 정식 인하 / 원복(20%로 복귀) 중 재결정.
3. 이 예외로 인해 `kr_alpha_min`/`overlay_min` 위반 상태에서도 시스템이 **정상 운영으로 판단**하도록(에러·강제 리밸런싱 트리거 안 하도록) 관련 검증 로직(`policy_cap.py` 등 kr_alpha 하한 체크 지점)이 이 예외를 인식하는지 확인 — **코드 로직 변경이 필요하면 별도 후속 스펙으로 분리**(이 스펙은 문서화·설계까지).

## 3. 로드맵 반영 요구사항

`KR_ALPHA_STRATEGY_ROADMAP.md`에 다음을 "결정된 다음 단계"로 추가:

- kr_alpha 최종 결론: **6%(시나리오 B) 확정**, 하한은 **한시 예외**(영구 변경 아님).
- 리뷰 트리거: forward-return 60~120일 데이터 충족 시점(잠정 2026 Q4) — 이때 재검토하지 않으면 **원 정책(20%)이 자동으로 유효**하다는 점을 명시(예외가 default가 되지 않도록).
- 10~20% 확대안은 검토 후 **철회**(사유: 심리적 만족 기준 vs 검증된 엣지 기준의 불일치, 단일종목캡 8% 위반 우려) — 기록만 남기고 재론하지 않음.

## 4. 절대 금지

- 이 스펙 범위에서 `kr_alpha_min`/`kr_alpha_overlay_min_pct` **숫자 자체를 변경하지 않음** — 한시 예외 주석/메타데이터 추가까지만.
- `target_portfolio.csv`/`user_target_portfolio.csv` 직접 수정 금지 — approval_bridge 별도.
- 예외를 "이번만"이 아니라 사실상 영구 방치로 흘러가지 않도록, 리뷰 시점 없는 예외 문구는 작성하지 않음(반드시 날짜/트리거 조건 포함).

## 5. 산출물

- `docs/KR_ALPHA_POLICY_FLOOR_TEMP_EXCEPTION_RESULT.md` — 예외 문구 반영 내역, 로드맵 갱신 내역, (해당 시) `policy_cap.py` 등 코드가 예외를 인식하는지 확인 결과.

## 6. 검증 체크리스트

1. `kr_alpha_min`/`overlay_min` 숫자 자체는 미변경 확인(git diff).
2. 예외 문구에 리뷰 시점(날짜/트리거 조건)이 명시됐는지.
3. 로드맵에 "10~20% 확대안 철회" 기록이 남았는지.
4. 리뷰 시점 도래 시 자동으로 원 정책(20%)으로 복귀한다는 문구가 있는지(예외가 default화되지 않도록).
