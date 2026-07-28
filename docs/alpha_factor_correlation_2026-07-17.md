# 알파 시스템 — 5팩터 상관 점검 리포트

- as_of: `2026-07-17`
- status: **OK**
- method: `pearson`
- high_|rho|_threshold: `0.7`
- n_names: `30`

## 데이터 요건

- DataFrame with columns: ticker + score_q, score_v, score_sr, score_r, cecs
- Each factor column numeric on a comparable scale (Q/V/SR/R typically 0~100; cecs 0~100).
- One row per name; NaN rows are dropped pairwise per correlation cell.
- Minimum distinct names: scoring.yaml correlation.min_names (default 20) after dropping all-NaN factor rows.
- Point-in-time / same as_of snapshot recommended (do not mix fiscal years across columns).
- Do not impute missing factors with peer means for this report — missingness should remain visible (pairwise complete).
- disclosure_status / independent_catalyst_flag are NOT score factors (mapped to T2 event_candidate_sources).
- Optional columns: ticker, sector — when present, report flags names whose sector peer group has < sector_min_sample rows in this snapshot (Q/V percentile uses market-wide fallback for those names).

## 높은 상관 쌍 (후보)

_임계값 이상인 쌍 없음._

## 상관 행렬

| factor | score_q | score_v | score_sr | score_r | cecs |
|---|---:|---:|---:|---:|---:|
| score_q | 1.000 | -0.208 | -0.459 | 0.111 | 0.158 |
| score_v | -0.208 | 1.000 | 0.369 | -0.183 | -0.198 |
| score_sr | -0.459 | 0.369 | 1.000 | -0.215 | -0.142 |
| score_r | 0.111 | -0.183 | -0.215 | 1.000 | 0.226 |
| cecs | 0.158 | -0.198 | -0.142 | 0.226 | 1.000 |

## 섹터 백분위 fallback (표본<5)

- `sector_min_sample`: **5** (alpha_portfolio Q/V percentile peer rule)
- fallback 적용 종목: **25** / 30 (이 CSV 스냅샷 내 동일 sector 표본 < 5)
- gate_pass 159 풀 기준 약 32개 업종이 fallback 대상 — 상관 해석 시 V/Q peer 품질 참고

| ticker | sector | sector_sample_n | sector_peer_fallback |
|---|---|---:|:---:|
| 006040 | consumer | 3 | Y |
| 021240 | consumer | 3 | Y |
| 271560 | consumer | 3 | Y |
| 030190 | data_service | 1 | Y |
| 005440 | holding | 2 | Y |
| 036530 | holding | 2 | Y |
| 005830 | insurance | 1 | Y |
| 002380 | materials | 1 | Y |
| 000660 | semiconductor | 1 | Y |
| 029780 | 기타금융 | 5 |  |
| 034730 | 기타금융 | 5 |  |
| 175330 | 기타금융 | 5 |  |
| 316140 | 기타금융 | 5 |  |
| 402340 | 기타금융 | 5 |  |
| 005930 | 반도체/IT하드웨어 | 1 | Y |
| 032830 | 보험 | 1 | Y |
| 088350 | 생명보험 | 1 | Y |
| 005380 | 운송장비·부품 | 1 | Y |
| 028260 | 유통 | 2 | Y |
| 069960 | 유통 | 2 | Y |
| 024110 | 은행 | 1 | Y |
| 055550 | 은행/금융지주 | 4 | Y |
| 086790 | 은행/금융지주 | 4 | Y |
| 105560 | 은행/금융지주 | 4 | Y |
| 138930 | 은행/금융지주 | 4 | Y |
| 000270 | 자동차 | 1 | Y |
| 005935 | 전기·전자 | 2 | Y |
| 009150 | 전기·전자 | 2 | Y |
| 015760 | 전력/유틸리티 | 1 | Y |
| 032640 | 통신 | 1 | Y |

## 통합·단순화 제안 메모

- Score axes are FIVE_FACTORS after CECS-T2 overlap cleanup (disclosure_status / independent_catalyst_flag → T2 candidates).
- Prefer merging among atomic axes when |rho| stays high out-of-sample.
- No pair with |rho| >= 0.7 in this snapshot.
- sector_peer_fallback: 25/30 names have sector peer sample < 5 in this CSV — Q/V percentile uses market-wide fallback for those rows (see gate_pass pool: ~32 sectors).

최종 팩터 단순화 여부는 **OK 리포트의 high_pairs**를 보고 사용자가 판단한다.
