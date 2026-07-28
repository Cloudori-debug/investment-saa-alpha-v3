# 익절 목표 근접도 (Proximity) — 명세서 (경량)

> 배경: 목표 미도달 구간(`exit_leg=NONE`)에서는 `signal_strength=0.0`으로만 표시되어 "0 아니면 1"처럼 보임. 계단식으로 올라가는 도중에도 "지금 목표까지 몇 %쯤 왔는지" 참고하고 싶다는 요청.
> 원칙: **"근접도"는 현재 상태의 순수 거리 측정값 — 미래 예측/확률 아님.** `signal_strength`(도달 후 percentile 기반 강도)와는 **다른 지표**이며 혼동되지 않게 컬럼·용어를 분리한다.

## 1. 정의

### A. 계산 로직 (`src/alpha/take_profit_thesis.py` 신규 함수)
```python
def compute_leg_proximity(
    fundamentals: dict[str, Any],
    targets: dict[str, Any],
) -> tuple[float | None, float | None]:
    """Return (fund_proximity_pct, val_proximity_pct), 0~100, capped.

    Purely mechanical distance-to-threshold. NOT a probability/forecast.
    None if that leg has no target defined for this ticker.
    """
```
- **FUND leg 근접도**: `roe_min`이 정의된 경우 `min(100.0, max(0.0, current_roe / roe_min * 100))`. `payout_min`/`buyback_done`도 정의돼 있으면 각 서브조건 근접도 계산 후 **최솟값**(가장 먼 조건이 병목 — `fund_hit`이 전 조건 AND이므로 근접도도 가장 안 된 조건 기준)을 leg 근접도로 사용.
- **VAL leg 근접도**: `pbr_max`가 정의된 경우 `min(100.0, max(0.0, current_pbr / pbr_max * 100))`. `premium_to_fair_pct` 등 다른 서브조건이 있으면 동일하게 최솟값 규칙.
- 이미 `exit_leg`가 해당 leg에서 hit인 경우(현재값이 목표 이상) 근접도는 100으로 고정 표시하고, 그 뒤 실제 트림 판단은 기존 `signal_strength`(percentile 기반)를 그대로 사용 — **근접도는 신호강도·계단구간 계산을 대체하지 않음**.
- `targets_missing=True`(yaml 자체가 없음)인 경우 근접도도 `None`("—")으로 표시 — 목표 미설정과 혼동 금지.

### B. `TakeProfitAssessment`에 필드 추가
```python
fund_proximity_pct: float | None = None
val_proximity_pct: float | None = None
```
`assess_take_profit()` 내부에서 `compute_leg_proximity()` 호출해 채움. 기존 필드(`signal_strength`, `exit_leg`, `suggested_action` 등) 계산 로직·순서는 변경 없음 — 근접도는 부가 정보로만 추가.

## 2. 명칭·표시 규칙
- **"근접도"만 사용. "확률"/"도달확률"/"예상확률"/"성공확률"/"승률" 등 예측 함의 단어 절대 금지** (기존 §4 금지어 목록에 편입)
- 표시 형식: `"VAL 84% 근접"` / `"FUND 60% 근접"` 처럼 leg 이름과 함께 — 어느 leg 기준인지 항상 명시 (여러 leg 있을 때 혼동 방지)
- `exit_leg` leg가 이미 hit이면 근접도 표시 대신 기존 계단구간(예: "80-90 (20%)")을 그대로 보여줌 — 두 지표가 같은 자리에 동시에 뜨지 않게 함

## 3. UI 반영 (표시만)
- **알파 → 보유 리뷰 → 익절 신호강도 표**: `계단구간` 컬럼 옆에 `근접도` 컬럼 추가. 미도달 구간에서는 "VAL 84% 근접" 같은 텍스트, 도달 후에는 기존 계단구간 유지(근접도 칸은 "도달" 표시로 대체).
- **Gap 표(종합 포트)**: "미도달" 라벨 뒤에 괄호로 근접도 추가 — 예: `"미도달 (VAL 84%)"`. 상세 근접도 계산 근거는 여전히 보유 리뷰 탭에서만.

## 4. 절대 금지
- 근접도를 신호강도·계단식 트림비율(`resolve_partial_frac_from_strength`) 계산에 섞어 쓰지 않음 — 완전히 별도 표시 지표
- 근접도 기반 자동 매매/승인 로직 추가 금지 (읽기 전용 참고)
- "확률"류 단어 재사용 금지 (테스트에 정적 검사 추가)

## 5. 검증 요청
1. KT(030200, pbr_max=0.86, 현재 pbr≈0.72): VAL 근접도 ≈ 83.7% 나오는지
2. 동원산업(006040, roe_min=13.5·pbr_max=0.53, 현재 roe=11.0·pbr=0.41): FUND 근접도 ≈ 81.5%, VAL 근접도 ≈ 77.4% 각각 맞는지 (서브조건 각각 leg별로 분리 표시)
3. SK하이닉스(000660, targets_missing=True): 근접도 "—"로 뜨는지 (0%나 100%처럼 오해되지 않게)
4. 이미 hit된 leg는 근접도 대신 기존 계단구간이 뜨는지 (두 지표 동시 노출 안 됨)
5. "확률" 등 금지어 정적 검사 통과
