# kr_alpha 0점 3종목 — 원인 진단 RESULT

> SPEC: [`KR_ALPHA_ZERO_SCORE_REVIEW_SPEC.md`](KR_ALPHA_ZERO_SCORE_REVIEW_SPEC.md)  
> 범위: **§1 진단만** (원장 선택: §2 교체후보 제안 보류)  
> 산출일 기준 아티팩트: `outputs/excluded.csv`, `outputs/alpha_scored_universe.csv`, `outputs/alpha_signal_board.csv`, `data/prices.csv`, `data/universe_filter.yaml`

## 한줄 결론

세 종목 모두 **QVM이 PER/PBR을 보고 0점을 준 것이 아니라**, 유니버스 유동성 필터(`min_20d_trading_value`)에서 탈락해 **채점 유니버스에 아예 들어가지 못한 뒤**, holdings_review가 후보 부재를 `score=0` / `Reject`로 폴백한 결과다.  
`valuation_signal=stretched`는 **절대 PER/PBR 고평가 판정이 아니라** `valuation_score < 50`(여기선 후보 부재 → 0)일 때 붙는 **표시 라벨**이라, 저배수와 방향이 어긋나 보이는 것은 **라벨 오해 소지**이지 factor 계산의 PE/PB 역전 버그는 아니다.

| 관점 | 판정 |
|---|---|
| QVM `total_score`가 “진짜 최하위 계산”인가? | **아니오** — 채점 미실행(유니버스 제외) |
| 유동성 스크리너 탈락은 시스템 규칙상 정당한가? | **예** — `standard` 20일 평균 거래대금 15억 미만 |
| PER/PBR을 “stretched(고평가)”로 **계산**했는가? | **아니오** — 점수 버킷 라벨 + 재무 배수 병기 |
| §2 교체후보로 즉시 진행? | **보류** (원장) — “QVM 최하위”와 동일시하면 안 됨 |

버그 수정이 필요하면(표시 라벨·후보부재 구분) **별도 스펙**이 맞다. 이 RESULT만으로 `target_portfolio.csv` 변경/매매는 하지 않는다.

---

## 1. `total_score=0.0` 추적

### 1.1 코드 경로

1. `src/alpha/alpha_pipeline.py` — `filter_universe` → 통과분만 `score_factors` → `alpha_scored_universe` / candidates.
2. `src/alpha/holdings_review.py` — 후보 dict에 없으면:

```python
score = 0.0
grade = "Reject"
# … score > 0 아니면
action = "REPLACE_CANDIDATE"
reason = "스크리너 미통과 또는 저점수, 교체 후보"
```

3. 시그널보드 `total_score=float(cand_dict.get("total_score") or 0)` — 후보 없으면 역시 0.

### 1.2 아티팩트 증거

| 종목 | `universe.csv` | `fundamentals` / `prices` | `outputs/excluded.csv` | `alpha_scored_universe.csv` |
|---|---|---|---|---|
| 036530 SNT홀딩스 | 있음 | 있음 | **있음** `failed_rule=min_20d_trading_value` | **없음** |
| 192400 쿠쿠홀딩스 | 있음 | 있음 | 동일 | **없음** |
| 453340 현대그린푸드 | 있음 | 있음 | 동일 | **없음** |

활성 유니버스 컷(`data/universe_filter.yaml` → `universe` / standard와 동일):

- `min_20d_avg_trading_value_krw: 1_500_000_000` (15억)

| ticker | `trading_value_20d` (원) | 약 (억) | vs 15억 |
|---|---:|---:|---|
| 036530 | 728,537,236 | 7.3 | 미달 |
| 192400 | 410,681,131 | 4.1 | 미달 |
| 453340 | 967,162,616 | 9.7 | 미달 |

따라서 보드의 quality/valuation/momentum **0**은 “피어 대비 최하위 퍼센타일 합성”이 아니라 **채점 결과가 없는 상태의 0 폴백**이다. (`factor_scoring._percentile_rank`는 결측 필드를 50으로 두고, 완전 결측 시조차 전 종목 50 — **결측→0 강제 경로는 아님**.)

### 1.3 종목별 진단 요약

| 종목 | 0점 원인 | “정당한 최하위 QVM”인가? |
|---|---|---|
| 036530 | 유동성 컷 제외 → 후보 부재 → score 0 | 아니오 (스크리너 미통과는 정당, QVM 최하위는 아님) |
| 192400 | 동일 | 동일 |
| 453340 | 동일 | 동일 |

---

## 2. `valuation_signal=stretched` 근거

`src/alpha/alpha_signal_board.py` `_axis_valuation`:

- `v = float(cand.get("valuation_score") or 0)`
- 라벨: `v >= 60` → attractive / `>= 50` → fair / **그 외 → stretched**
- PER·PBR은 fund에서 **병기만** 하고, 라벨 분기에는 쓰지 않음.

후보 부재 → `valuation_score` 없음 → `v=0` → **stretched** + 화면에는 저분류 PER/PBR이 같이 찍힘.  
저PBR을 시스템이 “고평가”로 **재해석한 버그**가 아니라, **점수 없을 때 쓰는 워딩이 절대배수와 충돌**하는 UX/라벨 문제다.

의도된 상대가치 로직(업종 대비 stretch 등)과도 무관 — relative stretch 엔진이 이 축에 연결된 흔적 없음.

---

## 3. `risk_blocker` 의미

| 토큰 | 코드 의미 | 이번 3종목 |
|---|---|---|
| `screen_fail_or_low_score` | `review_action == REPLACE_CANDIDATE`일 때 부착 | 쿠쿠·그린푸드 (및 공통 리뷰 액션) |
| `flow_distribution` | `flow_signal == DISTRIBUTION` | SNT |
| `position_overweight` | **종목** `current_weight > target_weight + 2.0` (pp) | SNT: 3.84% vs 목표 1.28% |

### SNT가 Trim인 이유

리뷰는 `REPLACE_CANDIDATE`이지만 `derive_action_state`에서 **종목 overweight가 Replace-review보다 선행**해 `action_state=Trim` + `position_overweight`.

**슬리브 오버웨이트(과거 확인한 kr_alpha 현 비중 vs 목표대)와 blocker 토큰은 다른 레이어**:  
`position_overweight`는 **해당 티커 cw/tw +2pp** 규칙이다, 슬리브 합 31% vs 22~24%를 직접 참조하지 않는다. (참고: 현재 `target_portfolio` kr_alpha 행 합 ≈ 21.28% — SNT만 목표 1.28%에 대해 이름 단위로 초과.)

쿠쿠·그린푸드: `target_weight_pct=0`, `Replace-review` + `screen_fail_or_low_score`.

---

## 4. 분기 (SPEC §1)

| SPEC 분기 | 적용 |
|---|---|
| 계산 버그(QVM/PE·PB 역전)로 확인 | **해당 없음** — 다만 **보드 라벨이 후보 부재를 “stretched/weak 0점”처럼 보이게 하는 표시 결함**은 별도 스펙 후보 |
| 정당한 최하위 QVM → §2 | **해당 없음** — 정당해도 유동성 **스크리너 미통과** |
| §2 교체후보 | **원장 선택으로 보류** |

운영 함의(제안만):

- “0점이니 자동 교체”로 직행하면 **유동성으로 쳐낸 보유분**과 **진짜 QVM 최하위**를 섞어 버릴 수 있음.
- 유지/축소/교체는 유동성·슬리피지·목표편입 여부와 승인 워크플로우에서 따로 판단.

---

## 5. 검증 체크리스트

1. 3종목 각각 `total_score=0` 원인 설명: **유니버스 `min_20d_trading_value` 제외 → 후보 부재 폴백** — 완료.
2. `stretched` 근거 납득: **점수 버킷 라벨(부재=0), PER/PBR 절대 고평가 아님** — 완료.
3. `data/target_portfolio.csv` 등 미변경: 이 작업은 진단 문서만 작성 — 매매/타깃 수정 없음.
4. 교체후보 표: **해당 없음**(§2 보류).

### 후속(이 스펙 밖)

- (선택) 시그널보드: 후보 미포함/`screen_fail`일 때 `valuation 0 stretched` 대신 `not scored / universe_excluded:liquidity` 등 **부재 명시**.
- (선택) §2: 유동성 탈락 보유를 교체할지 여부는 정책 결정 후에만 후보 제안.
