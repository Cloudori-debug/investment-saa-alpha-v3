# 위성(Satellite) 비중 룰 — 이중/삼중 정의 조사

> 배경: 검증자 지적 — `target_matrix` 위성 캡(~1.09% 포트) vs CECS 설계(8~10%) 불일치  
> 범위: **원인·단위·경로 규명만** (071050 축소/룰 변경 미실행)  
> 관련: `docs/TARGET_MINMAX_BAND_FIX_RESULT.md`

## 1. 한 줄 결론

같은 단어 **「위성 / Satellite」** 아래에 **서로 다른 모듈 3개**가 공존한다.  
검증자가 본 “5~9배 차이”는 상당 부분 **단위(슬리브% vs 포트폴리오%)를 섞어 읽은 결과**이고,  
071050의 5.56%는 CECS·target_matrix 캡이 아니라 **QVM `portfolio_selector`의 포트폴리오 균등 상한 8%** 경로에서 왔다.

## 2. 세 갈래 (의도·단위·코드)

| # | 모듈 | 설정 | “위성” 의미 | 단위 | 단일 위성 상한 (kr_alpha≈21.8% 시) | live target 연결 |
|---|------|------|-------------|------|-----------------------------------|------------------|
| **A** | CECS 티어 | `alpha_portfolio/config/tier_weighting.yaml` | 촉매 티어 `SATELLITE` (CORE/NEAR/…) | **kr_alpha 장부 합=1 기준 비중** | 종목 **8~10% of sleeve** → 포트 **≈1.7~2.2%** · 위성 합 15~20% of sleeve | `tier_allocator` / `tier_allocation.json` — **별도 트랙**, draft/live 자동 반영 아님 |
| **B** | Target matrix | `alpha_portfolio/config/target_matrix.yaml` | 스크리너 tier Core/Satellite | sleeve % + 포트 `portfolio_max` | `single_name_sleeve_pct: 5` → 포트 **≈1.09%** · `bands.satellite.portfolio_max: 5.0` | `target_draft` 밴드·normalize |
| **C** | QVM 포트 제안 | `data/alpha_scoring.yaml` → `portfolio_selector.py` | role 라벨 `satellite` (모멘텀 우세) | **전체 포트폴리오 %** | `max_proposed_weight_pct: 8.0` (균등배분 캡) | `alpha_portfolio_proposal` → `default_add_candidates` → 승인 시 target |

문서 근거:

- CECS: `alpha_portfolio/docs/05_CECS_TIER_WEIGHTING.md` — 스크리너 Core/Satellite와 **별개**라고 명시. `allocate_weights()`는 합=1 정규화.
- Matrix: `target_matrix.py` `compute_bands` + `satellite_cap.single_name_sleeve_pct`.
- QVM: `equal = budget/n_sel`, `weight = min(equal, max_proposed_weight_pct)`.

## 3. “8~10% vs ~1%” 재해석

| 읽기 | CECS 8~10% | Matrix 5% sleeve | 배수 |
|------|------------|------------------|------|
| **둘 다 슬리브 %로** | 8~10% of sleeve | 5% of sleeve | **1.6~2×** (긴장 있음, 5~9× 아님) |
| **CECS를 포트 %로 오인** | 8~10% of portfolio | 1.09% of portfolio | **5~9×** ← 검증자 표와 유사 |

→ 숫자 충돌은 실재하지만, **같은 시스템 한 룰의 두 버전**이라기보다 **다른 제품 레이어 + 단위 혼동**에 가깝다.

## 4. 071050이 5.56%인 이유 (룰 관점)

1. QVM proposal이 WATCH 위성에 **포트 8%**급 제안 비중을 달 수 있음 (`max_proposed_weight_pct`).
2. 승인 브리지 add 시 그 비중이 들어오고, 예산 스케일로 **~5.56%**까지 줄어듦.
3. 그 과정에서 **CECS 8~10% sleeve 룰도, matrix 5% sleeve 캡도 강제되지 않음** (당시 밴드 기본 1/4 + weight-only scale).

즉 071050은 “느슨한 CECS”로 들어온 것이 아니라 **QVM 균등·8% 포트 캡 경로**로 들어왔다.

## 5. 옵션 재배치 (검증자 ①②③에 대응)

| 옵션 | 의미 (이번 조사 후) | 비고 |
|------|---------------------|------|
| ① 071050을 matrix 5% sleeve(~1.09%)에 맞춤 | **B 룰을 운영 진실로 채택** | QVM 8% 제안·현 보유 논리와 충돌 가능 — 투자 논거 확인 필요 |
| ② 예외 유지 | 확장성 없음 — 검증자 지적 그대로 | 비권장 |
| ③ 룰 재설계 | **먼저 “운영 진실” 레이어를 하나로 고름** | 후보: (B) matrix 5% sleeve · (A′) CECS 8~10% sleeve(~2% 포트) · (C′) QVM 단일명 포트 상한을 sleeve 캡과 정합 |

권장 순서:

1. **운영 진실 선택:** live `target_portfolio` / 승인 UI가 따를 단일 캡 (권장 후보: **B target_matrix**, draft·밴드 원천과 일치).  
2. **QVM proposal(C)을 그 캡에 맞춤:** `max_proposed_weight_pct`를 “포트 %”가 아니라 sleeve 환산 또는 matrix와 동일 상한으로.  
3. **CECS(A)** 는 문서대로 스크리너 Core/Satellite와 분리 유지하되, UI/문서에 “슬리브 분율” 단위를 명시해 재혼동 방지.  
4. 그 다음에야 071050을 ① 축소 vs ③에 맞춰 재설정.

## 6. 하지 말 것 (이번 라운드)

- policy_cap / execution_scope / throttle 변경 없음  
- 071050 비중·구성 임의 변경 없음 (운영자 결정 전)  
- validators 완화 없음  

## 7. 다음 액션 (승인 대기)

운영자에게 질문 한 줄:

> live target의 위성 단일 종목 상한을 **(B) sleeve 5% ≈ 포트 1.1%** 로 할까요, **(A 정합) sleeve 8~10% ≈ 포트 1.7~2.2%** 로 올릴까요, 아니면 **(C) 포트 8%급**을 공식 정책으로 승격할까요?

선택 후에야 071050 목표 비중과 `max_proposed_weight_pct` / `target_matrix.satellite_cap` 정렬 PR을 진행.
