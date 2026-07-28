# 위성 단일 종목 상한 정렬 — 결과

> 명세: `docs/SATELLITE_CAP_ALIGNMENT_SPEC.md`  
> 운영 진실: **B** (`target_matrix.satellite_cap.single_name_sleeve_pct: 5`)  
> 정책 캡 / execution_scope / throttle / auto_trading: **미변경**

## 1. 구현 요약

### A. QVM 제안 캡 동적 정렬
- `src/alpha/portfolio_selector.py`
  - `load_satellite_single_name_sleeve_pct()` / `sleeve_pct_to_portfolio()` / `resolve_proposed_weight_cap()`
  - **satellite** role만: `sleeve% × kr_alpha_budget` 포트 환산 상한
  - non-satellite: 기존 `max_proposed_weight_pct`(8.0)
  - 두 값이 어긋나면 warning으로 명시
- `data/alpha_scoring.yaml`: `max_proposed_weight_pct`는 non-satellite용임을 주석

### B. 071050 축소 (감사 경로)
- `scripts/align_071050_satellite_cap.py --apply`
- `apply_proposed_target(..., write_reason="satellite_cap_alignment")`
- 축소분 → **CASH** 파킹 (합계 100% 유지, 다른 kr_alpha 재배분으로 캡 재초과 방지)
- CASH max를 파킹 후 target에 맞게 정합 (`satellite_cap_alignment` 감사)

### C. CECS 문서화
- `alpha_portfolio/docs/05_CECS_TIER_WEIGHTING.md` + `tier_allocator.py` 모듈 docstring  
  → **live target 비연결 연구 트랙**, 운영 진실은 `target_matrix`

## 2. 전/후 diff

| 항목 | 전 | 후 |
|------|-----|-----|
| 071050 target | 5.56 | **1.09** |
| 071050 min/max | 0.0 / 5.56 | **0.0 / 1.09** |
| CASH target | 3.08 | **7.55** (+4.47) |
| CASH max | 6.0 | **7.55** |
| 캡 산출 | — | sleeve 5% × budget **21.85%** = **1.09%** |

## 3. 검증

| 항목 | 결과 |
|------|------|
| `tests/test_portfolio_selector.py` satellite 예산 15%/25% 동적 캡 | **pass** |
| `tests/test_target_bridge.py` | **pass** (기존) |
| `validate_inputs` band 위반 | **0건** → gate **GREEN** |
| `target_write_audit.jsonl` | `target_write_reason=satellite_cap_alignment` |
| CECS 비연결 문구 | 문서·모듈 docstring 반영 |

### 매매 아님 (필수 명시)
이번 조치는 **`target_portfolio` 목표 비중만** 변경한 것이다.  
`policy_cap` / ETF_ONLY 등으로 **Actual Buy Allowed는 계속 차단**된다. 주문이 나가지 않는다.

### 게이트
- `input_validation_gate`: **GREEN** (밴드 기준)
- `portfolio_gate` / `data_gate` / 실매수: **policy_cap(~2026-09-24) 때문에 YELLOW 유지 예상** — 이번 정렬 실패 아님

## 4. 재실행

```powershell
cd C:\Cursor\investment-saa-alpha
$env:PYTHONPATH='.'
python -m pytest tests/test_portfolio_selector.py -q -k satellite
python scripts/align_071050_satellite_cap.py          # dry-run
# --apply 는 이미 반영됨
```
