# KOSPI 알파 — CECS 티어 가중치 모듈

> 원본: `kospi_alpha_tier_weighting_spec.md` (외부 명세)  
> 구현 위치: `alpha_portfolio` 패키지
>
> **운영 연결 상태 (2026-07-12):** 이 트랙은 **live `target_portfolio` 산출에 연결되지 않은
> 별도 연구/실험 트랙**이다. 승인·밴드·QVM 제안의 운영 진실은
> `alpha_portfolio/config/target_matrix.yaml` (`satellite_cap` 등)이다.
> CECS 코드·테스트는 유지하되, 숫자를 live 캡으로 이식하지 말 것.

## 필드 매핑 (명세 vs 실제 코드)

| 명세 | alpha_portfolio 실제 필드 |
|------|---------------------------|
| `factor_score_total` | **`composite_score`** (`screener.run_screener`) |
| 6-팩터 | Q/V/SR/R/M 5축 + `composite_core` / `composite_satellite` |
| 기존 `tier` (Core/Satellite) | 스크리너 등급용 — **CECS 티어(CORE/NEAR/...)와 별개** |

## 모듈

| 파일 | 역할 |
|------|------|
| `config/tier_weighting.yaml` | CECS 가중치·임계값·비중 범위 (튜닝 가능) |
| `src/catalyst_profile.py` | `StockCatalystProfile`, `calculate_cecs`, `assign_catalyst_tier` |
| `src/tier_allocator.py` | `allocate_weights`, `build_tiered_portfolio`, 파이프라인 브릿지 |
| `src/tier_allocation_app.py` | Streamlit 수동 CECS 조정 UI |

## 실행

```powershell
cd alpha_portfolio
pip install -e ".[data,dev,ui]"
python -m src.main --kr-alpha-weight 25   # → data/output/tier_allocation.json
streamlit run src/tier_allocation_app.py
```

## 원본 명세

- 외부: `kospi_alpha_tier_weighting_spec.md` (동준님 Downloads → Cursor 전달)
- P1~P8(`investment-saa-alpha/docs/`)와 **별개**

## 검증 피드백 반영 (2026-07-10)

| 이슈 | 조치 |
|------|------|
| `satellite_min` 미만도 SATELLITE 반환 (dead code) | **`EXCLUDE`** 티어 추가 — 배분 weight=0 |
| `single_name_max` 18%가 정규화 후 깨짐 | `allocate_weights` cap-and-redistribute 반복 (7종 혼합: sum=1, max≤18%) |
| receiver 부족 저투자 | cap 유지(18% 준수) — 부족분은 `_meta.unallocated_weight`로 보고 + `portfolio_allocation_warnings` (재정규화 없음, 예: CORE 3종 → 54%) |

## 미구현 (명세 2단계)

- DART 자동 `fetch_cecs_inputs.py`
- walk-forward 백테스트 티어 비교 (섹션 6)
