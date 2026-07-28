# NAV MTD Judgment Fix (P4f)

> **변경 금지 영역 유지:** gate / policy_cap / target_write / approval_bridge / Actual Buy Allowed 계산 미변경.  
> **범위:** 대시보드·NAV metrics 표시/판단 정합성만.

## 전제 (클로드 교차검증으로 확정)

- 시스템에 **입금/자산등록 이벤트 원장(cashflow ledger)은 없음**.
- 따라서 완전한 DIH(Deposit In Hand) 분리는 새 데이터 스키마가 필요하며, 이번 패치는 **heuristics + 가격 기반 holdings return**으로 판단 왜곡을 제거한다.

## 변경 요약

| 파일 | 내용 |
|------|------|
| `src/alpha/nav_log.py` | `nav_return_mtd_detail()` — raw vs adjusted. cash/core 버킷 점프를 capital-like로 추정 |
| `src/alpha/benchmark_data.py` | `ticker_return_mtd` stale/단건 → **None** (가짜 0.0 제거) |
| `src/alpha/performance_dashboard.py` | actual MTD 우선순위: holdings price → adjusted NAV → shadow → raw fallback |
| `tests/test_nav_mtd_adjustment.py` | 등록 점프·stale 가격 단위 테스트 |

## 판단용 숫자 (2026-07-08 재계산 예시)

| metric | 값 | 의미 |
|--------|-----|------|
| `raw_nav_return_mtd` | **35.00%** | 등록 점프 포함 — **운용 판단에 쓰지 말 것** |
| `adjusted_nav_return_mtd` | ~**3.80%** | capital-like ~2,747만 원 제외 |
| `actual_portfolio_return_mtd` (source=`holdings_price_return`) | ~**1.26%** | **권장 판단 지표** |
| `kr_alpha_return_mtd` | ~**1.26%** | 알파 슬리브 가격 MTD |
| `kospi200_return_mtd` | **null** (`stale_price`) | 069500 시세 6/26 1건뿐 — 가짜 0.0 아님 |
| `kr_alpha_excess_vs_kospi200` | **null** | 벤치 결측 시 excess 미표기 |

## 한계 / 후속

1. capital-like 감지는 **버킷 휴리스틱** — 정확한 입금 원장이 생기면 교체 권장.
2. `069500` July 가격 보강(가격 리프레시) 전에는 KOSPI200 excess를 표시하지 않음.
3. `target_guard_conflict` (B층) 원인 규명은 본 패치 범위 밖.

## 검증

```powershell
python -m pytest tests/test_nav_mtd_adjustment.py tests/test_benchmark_data_quality.py tests/test_alpha_performance_dashboard.py -q
```
