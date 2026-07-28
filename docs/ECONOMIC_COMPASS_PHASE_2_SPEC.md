# 경제 나침반 업그레이드 2단계 — Turbulence Index 병행 (실행 명세서)

> ROADMAP: [`ECONOMIC_COMPASS_ROADMAP.md`](ECONOMIC_COMPASS_ROADMAP.md)
> 원칙: 0·1단계와 동일 — 삭제·전면 재작성 아님, 기존 VIX 판정을 **대체하지 않고 병행 신호로 추가만**. `src/alpha/`(kr_alpha), `take_profit_thesis.py` 미변경.

## 0. 착수 전제 확인 결과 — **미충족 (2026-07-16 직접 확인)**

로드맵 2단계 조건("최소 60~120일 가격 이력 데이터 품질 확인")을 이번에 실제로 확인했습니다. 결론부터: **지금 당장 구현에 들어가면 안 됩니다.**

| 후보 데이터 | 확인 결과 |
|---|---|
| `data/market_indicators_history.csv` | **24행뿐**. 날짜 범위 2026-01-15~07-14. 앞부분(1~4월)은 월 1회 간격이고, 실질적으로 매일 단위 데이터는 최근 약 2주치(07-08~07-14)뿐 — 마할라노비스 거리 계산에 필요한 60~120영업일 이력의 1/5도 안 됨. |
| `data/prices_history.csv` | 272개 날짜는 있으나 날짜별 종목 커버리지가 매우 불규칙(같은 날인데 3종목만 있는 날 vs 2,629종목 있는 날 혼재) — 이전 세션에서 확인한 "D1 초기 버그로 9,205→7,961행 축소" 이력과 같은 계열 데이터 품질 문제. 안정적인 공분산행렬 추정에 부적합. |
| 기타(`combined_price*`, `benchmark*`) | 리포지토리에 해당 파일 없음(검색 결과 0건). |

**의미**: 억지로 지금 구현하면, 애초에 이 로드맵을 시작한 이유(하드코딩·미검증 임계값 문제)와 똑같은 함정에 빠집니다 — 데이터가 부족한 상태에서 추정한 공분산행렬은 노이즈를 "이례성"으로 오인할 위험이 큽니다. 그래서 이번 스펙은 **지금 구현하라는 지시가 아니라, 데이터가 쌓이면 자동으로 판단할 수 있는 게이트 + 그때 쓸 설계도**로 작성합니다.

## 1. 데이터 축적 게이트

**작업 지시**: 지금은 코드를 구현하지 말고, 아래 체크만 파이프라인 실행 후 보고해 주십시오.

```python
import pandas as pd
df = pd.read_csv("data/market_indicators_history.csv")
print(len(df))  # 이 값이 60 이상이면 §2로 진행, 미만이면 대기
```

- `market_indicators_history.csv`가 매 파이프라인 실행(=매일 1행)마다 누적된다면, 2026-07-16 기준 24행에서 60행 도달까지 약 36영업일(≈2개월), 120행까지 약 4개월 소요 추정.
- 이 파일이 실제로 매일 누적되는 구조인지(누락 없이 append되는지)도 함께 확인 필요 — 1월~4월분이 월 1회 간격이었던 것으로 볼 때 과거엔 매일 쌓이지 않았을 가능성이 있음. 그렇다면 게이트 통과가 더 늦어짐.
- **60행 도달 시점에 이 문서 §2를 실행**하면 됩니다(별도 스펙 재작성 불필요).

## 2. 구현 설계 (게이트 통과 후 적용)

### 2.1 개념

Chow/Jacquier/Kritzman/Lowry (1999)의 Financial Turbulence Index — 자산 벡터의 마할라노비스 거리로 "다변량 이례성"을 측정. 기존 VIX 단일임계값을 **대체하지 않고**, `_classify_risk_regime()` 옆에 별도 신호로 계산·로깅만 한다(0단계 원칙과 동일하게 실제 tilt에 즉시 반영하지 않고 관찰부터 시작).

### 2.2 입력 벡터

`market_indicators_history.csv`의 일별 수익률 벡터(변화율)를 사용 — 개별 종목이 아니라 이미 나침반이 쓰는 축과 동일한 자산군으로 통일(설계 일관성 + 데이터 가용성 둘 다 만족):

```
r_t = [Δkospi%, Δsp500%, Δusdkrw%, Δkorea_10y(bp), Δoil_brent%, Δgold%]
```

### 2.3 계산

```
μ = r_t의 표본 평균 (롤링 윈도우, 게이트 통과 시점의 가용 행 수만큼, 최대 120)
Σ = r_t의 표본 공분산행렬
FT_t = (r_t − μ)ᵀ Σ⁻¹ (r_t − μ)
```

- 신규 파일: `src/compass/turbulence_index.py` — `compute_turbulence(history_df, window=...) -> float`
- Σ가 특이행렬(singular)이 될 수 있는 표본 부족 구간 대비: `numpy.linalg.pinv` 사용 권장, 또는 최소 표본 수 미달 시 `None` 반환하고 사유를 로그에 남길 것(억지 계산 금지).

### 2.4 로깅 (0단계 로그에 병합)

`outputs/compass_judgment_log.jsonl`에 필드 추가:
```json
{
  "turbulence_score": 12.3,
  "turbulence_percentile": 0.82,
  "vix_risk_off_flag": true,
  "turbulence_risk_off_flag": false
}
```
- `turbulence_percentile`: 누적 이력 대비 백분위(표본이 적을 초기엔 신뢰구간이 넓다는 점을 별도 필드 `turbulence_sample_size`로 함께 기록해 향후 해석 시 착오 방지.
- **이 신호로 실제 tilt를 바꾸지 않는다** — VIX 판정과 얼마나 일치/불일치하는지 관찰 로그만 쌓는다(0단계와 동일하게 read-only).

### 2.5 검증 (구현 시점)

1. 과거 알려진 급락일(예: 최근 KOSPI -24% 국지 급락 사례, 로그에 이미 기록됨)에 `turbulence_score`가 실제로 튀는지 육안 확인.
2. VIX 판정(`vix_risk_off_flag`)과 `turbulence_risk_off_flag`가 병행 기록된 기간 동안 일치율 계산 — 불일치 사례를 모아 어느 쪽이 더 빨리/늦게 반응했는지 기록.
3. 표본 부족(Σ 특이/근사 특이) 경고가 실제로 뜨는지, 뜬 경우 `None` 처리가 파이프라인을 깨뜨리지 않는지 확인.

## 3. 완료 후 처리

- §1 게이트 체크 결과만 먼저 `docs/ECONOMIC_COMPASS_PHASE_2_GATE_CHECK.md`(또는 채팅)로 보고 — 60행 미만이면 여기서 멈추고 로드맵 상태를 "대기(데이터 부족, N행/60행)"로 갱신.
- 60행 이상이면 §2~2.5를 구현 후 `ECONOMIC_COMPASS_PHASE_2_RESULT.md` 작성.
