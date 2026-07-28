# kr_alpha 절충안 전환 — RESULT (제안 단계)

> SPEC: [`KR_ALPHA_HYBRID_TRANSITION_SPEC.md`](KR_ALPHA_HYBRID_TRANSITION_SPEC.md)  
> 후속: [`KR_ALPHA_DOMESTIC_BETA_CONCENTRATION_RESULT.md`](KR_ALPHA_DOMESTIC_BETA_CONCENTRATION_RESULT.md) · [`KR_ALPHA_HYBRID_TRANSITION_SCENARIO_B_ADOPT_SPEC.md`](KR_ALPHA_HYBRID_TRANSITION_SCENARIO_B_ADOPT_SPEC.md)  
> 원칙: **제안만**. `target_portfolio.csv` / `user_target_portfolio.csv` / `kr_alpha_exit_targets.yaml` **미수정**.  
> 유동성: 네이버 일봉 API 근사값 `종가×거래량` 20일 평균 (2026-06-01~07-15). 임계값은 유니버스 standard `min_20d_avg_trading_value_krw=1.5e9`(15억). PyKRX는 세션에 `KRX_ID`/`KRX_PW` 없어 미사용.

### 갱신 이력

| 일시 | 내용 |
|---|---|
| 2026-07-16 | 최초 RESULT — §4에 069500 domestic_beta 6.87% 포함(시나리오 A) |
| 2026-07-16 | **시나리오 B 채택** — §4·§2.4·§0b·§7 개정. domestic_beta 신설 철회, freed→161510/279530 |

## 0. 원장 §3 답변 (확정)

| # | 질의 | 답변 |
|---|---|---|
| 1 | KT 처리 | **ETF 대체** (satellite 제외) |
| 2 | 배분 | Cursor 초안 → **§4 숫자 원장 승인** (아래 §0b) |
| 3 | §1 target–실제 괴리 | **별도 리밸런싱으로 분리** — 이번 RESULT는 신규 목표안만 |

### 0b. 배분·정책 (2026-07-16 후속 확정)

| 항목 | 원장 결정 |
|---|---|
| §4 숫자 (최종) | **시나리오 B**: DB손보 3.5 / 현대GF 2.5 / 161510→**11.79** / 신규 279530→**7.08** / **domestic_beta 신설 없음** |
| 정책 floor | approval 전제: **`kr_alpha_min`·`kr_alpha_overlay_min_pct` 하한 2건만** 개정(또는 한시 예외). yaml은 **지금 수정하지 않음**. `domestic_beta_note` 개정은 **불필요(종결)** — B는 069500 미도입 |

## 1. 유지 / 제거 (원장 합의 반영)

### 1.1 satellite 유지 (kr_alpha)

| ticker | 종목 | 제안 목표 | role (현행) | 비고 |
|---|---|---:|---|---|
| 005830 | DB손해보험 | **3.5%** | shareholder_return | 스펙 3~4% 중간 |
| 005440 | 현대지에프홀딩스 | **2.5%** | value_rerating | 스펙 2~3% 중간 |

**kr_alpha 합계 제안: 6.0%** (현행 목표 합 21.28% → **−15.28%p** freed)

### 1.2 kr_alpha에서 제거 (목표행 삭제 / 비중 0)

KT(030200), 코웨이(021240), 동원산업(006040), 오리온(271560), SNT홀딩스(036530), 쿠쿠홀딩스(192400), 현대그린푸드(453340), SK하이닉스(000660, 미보유·목표 2.5%).

쿠쿠·그린푸드는 이미 target 행 없음 — 제안 상 변경점 없음(실행 잔량만 별도 리밸).

### 1.3 exit_targets

이번 스펙 범위에서 `data/kr_alpha_exit_targets.yaml` **미변경**.  
DB손보·현대GF 엔트리(pbr_max 1.20 / 0.86 등) 유지 확인. 제거 종목 엔트리는 포지션 청산 후 **별도**로 정리(임의 삭제 금지).

---

## 2. ETF 후보 조사 (§2.3)

### 2.1 판정 기준

- 20일 평균 거래대금(종가×거래량 근사) ≥ **15억**
- income_alt `161510` / 신규 배당·가치 ETF와 **과도한 중복** 지양
- domestic_beta는 현재 **목표·보유 모두 0%** — 조사 단계에서 재개 후보였으나 **시나리오 B로 미신설 확정**

### 2.2 후보표

| ticker | 이름 | 역할 후보 | ≈20일 거래대금 | 15억 컷 | 비고 |
|---|---|---|---:|:---:|---|
| **161510** | PLUS 고배당주 | income_alt 증액 | **~378억** | PASS | 이미 target 3.59% — **마찰 최소** |
| **279530** | KODEX 고배당주 | 신규 income_alt | **~99억** | PASS | FnGuide 고배당 Plus — 161510과 지수 다름·보완 |
| **069500** | KODEX 200 | domestic_beta(기각) | **~3.2조** | PASS | 집중도 재검토 후 **B에서 미채택** (삼전닉스 ~63%) |
| 102110 | TIGER 200 | domestic_beta 대안 | ~680억 | PASS | 069500 대체 가능 |
| 278530 | KODEX 200TR | domestic_beta 대안 | ~970억 | PASS | TR 선호 시 |
| 226490 | KODEX 코스피 | 광의 베타 | ~506억 | PASS | 200 대비 커버리지 넓음 |
| 091170 | KODEX 은행 | 가치/금융 틸트 대안 | ~433억 | PASS | 섹터 집중 — **배당 ETF와 금융 중복 ↑** (보류 추천) |
| 139230 | TIGER 경기방어 | 방어 틸트 | ~70억 | PASS | “가치”와 비동일 — 2순위 |
| 211900 | KODEX 코리아배당성장 | 배당성장 | ~14억 | **FAIL** | 임계값 미달 |
| 211560 | TIGER 배당성장 | 배당성장 | ~5.5억 | **FAIL** | |
| 210780 | TIGER 코스피고배당 | 고배당 | ~5.9억 | **FAIL** | |
| **275290** | KODEX 가치주 | 순수 가치 | **~3.0억** | **FAIL** | 스펙 “가치 ETF” 기대와 충돌 — **편입 비추천** |
| 227560 | TIGER 지주회사 | 홀딩스 틸트 | ~1억 | **FAIL** | |

### 2.3 조사 결론

1. **순수 가치주 ETF(275290 등)는 이 시스템 유동성 컷을 통과하지 못함.**  
2. 집중도 재검토 후 **시나리오 B 채택**: domestic_beta(069500 등) **미신설**. freed weight는 **161510·279530**에만 배분.  
3. **161510은 현재 보유 0**(income_alt 그룹 전체 미보유) — “증액”은 **목표만 올려 매수 여력 확보**하는 의미. 실제 매수는 승인·실행 단계.

### 2.4 정책 충돌 (승인 전 필수) — B 채택 후 재평가

남는 충돌은 **kr_alpha 하한 2건뿐**:

| 문서 | 설정 | 제안 6%와 |
|---|---|---|
| `data/portfolio_policy.yaml` | `kr_alpha_min: 20` | **충돌(변경 필요)** |
| `data/absolute_return_policy.yaml` | `kr_alpha_overlay_min_pct: 15.0` | **충돌(변경 필요)** |

| 항목 | 상태 |
|---|---|
| `absolute_return_policy.yaml`의 `domestic_beta_note` | **개정 불필요 · 종결** — B는 069500을 넣지 않으므로 “국내주식 노출=kr_alpha가 대신한다”는 기존 전제가 깨지지 않음. (kr_alpha 자체가 6%로 줄었을 때 그 전제가 실질적으로 충분한지는 **별도 논의·이번 범위 밖**.) |

**approval_bridge로 target을 반영하기 전에** 위 하한 2건 개정(또는 한시 예외)만 원장이 별도 승인하면 된다. 이 RESULT만으로 yaml을 바꾸지 않음.

---

## 3. §1 괴리 — 이번 범위 밖 (정보)

별도 리밸런싱으로 분리(원장). 참고만:

| 종목 | 현행 target | 실제(≈) |
|---|---:|---:|
| KT | 4.99% | 0.45% |
| DB손해보험 | 3.81% | 5.81% |
| 동원산업 | 1.28% | 4.25% |
| 오리온 | 1.28% | 2.98% |
| SNT홀딩스 | 1.28% | 3.84% |
| 현대지에프홀딩스 | 1.15% | 4.21% |
| 쿠쿠·그린푸드 | (행 없음=0) | 보유 중 |
| SK하이닉스 | 2.50% | 0% |

실제 kr_alpha 합 ≈ **31.91%** vs 목표 21.28% — 실행 지연 오버웨이트는 전환 매도 스케줄과 별도 논의.

---

## 4. 최종 배분 — 시나리오 B (freed ≈ 15.28%p → income_alt만)

현행 그룹 합 100%. kr_alpha 21.28→6.0 후 잔량 **15.28%p 전부 income_alt**(161510·279530). **domestic_beta 그룹은 이번 전환에서 생성하지 않음.**

| 그룹 | ticker | 현행 target | 제안 target(B) | Δ |
|---|---|---:|---:|---:|
| kr_alpha | 005830 DB손해보험 | 3.81 | **3.50** | −0.31 |
| kr_alpha | 005440 현대GF홀딩스 | 1.15 | **2.50** | +1.35 |
| kr_alpha | 그 외 6+SK행 | 16.32 | **0** | −16.32 |
| income_alt | 161510 PLUS 고배당 | 3.59 | **11.79** | **+8.20** |
| income_alt | **279530** KODEX 고배당주(신규) | — | **7.08** | **+7.08** |
| domestic_beta | (신설 안 함) | — | — | — |
| income_alt | 458730/329200/352560 | 각 3.59 | **유지** | 0 |
| 기타 그룹 | (cash/global/hedge) | | **유지** | 0 |

검산(틱커 Δ): (−0.31+1.35−16.32) + 8.20 + 7.08 = **0**.  
income_alt 합(B): 11.79 + 7.08 + 3×3.59 = **29.64** (= 현행 14.36 + 15.28).  
(참고: ADOPT SPEC 본문의 “income_alt 합 22.77”은 시나리오 A 시절 income 소계. B는 구 domestic 6.87%p를 income에 흡수하므로 **29.64**가 맞음.)

### 그룹 합 (제안 B)

| asset_group | 현행 | 제안(B) |
|---|---:|---:|
| kr_alpha | 21.28 | **6.00** |
| income_alt | 14.36 | **29.64** |
| domestic_beta | 0 | **0** (신설 안 함) |
| 그 외 | 64.36 | 64.36 |
| **합** | 100 | **100** |

### 실행 비용(정보)

- 매도 7종(주식): `securities_tx_tax_bps: 18` 등 `cost_assumptions.yaml` 가정치 — **운용 확정치 아님**.  
- `avg_price` 결측 → 실현손익·양도세는 시스템 산출 불가.  
- income_alt(161510·279530)는 **현재 미보유** → 목표 반영 후 Core/스로틀·게이트 규칙을 따르는지 실행 단계에서 확인.

---

## 5. 절대 금지 준수

| 항목 | 상태 |
|---|---|
| `target_portfolio.csv` 직접 수정 | **하지 않음** |
| `user_target_portfolio.csv` 직접 수정 | **하지 않음** |
| `kr_alpha_exit_targets.yaml` 임의 변경 | **하지 않음** (005830·005440 유지) |
| 매매 실행 | **하지 않음** |

승인 경로: 원장이 숫자·정책 floor 개정 합의 → `approval_bridge` / Target 승인 UI.

---

## 6. 검증 체크리스트

1. target 파일 미변경: 이 RESULT 문서 개정만 — **준수**.  
2. §4 B 숫자: 161510 **11.79** / 279530 **7.08** / domestic_beta **없음** — **반영**.  
3. §2.4: `domestic_beta_note` 개정 **불필요·종결**, 남는 충돌은 kr_alpha 하한 2건 — **반영**.  
4. exit_targets DB손보·현대GF 임계값 유지: **파일 미수정으로 유지**.

## 7. 원장 다음 액션

1. ~~§4 시나리오 B 채택~~ — **완료**(§0b).  
2. **정책 하한 스펙(별도, approval 직전)**: `kr_alpha_min` / `kr_alpha_overlay_min_pct` 하향(또는 한시 예외) **2건만** — `domestic_beta_note`는 제외. yaml은 그 승인 후에만 변경.  
3. 정책 반영 후 `approval_bridge`로 target draft 반영 — 매도·매수는 분할·§1 별도 리밸과 스케줄 분리.  
4. 로드맵「결정된 다음 단계」는 원장 패턴대로 **검증 후** 일괄 갱신.
