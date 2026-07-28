# 알파 시스템 — 5팩터 상관 점검 리포트

- as_of: `2026-07-16`
- status: **SKIPPED**
- method: `pearson`
- high_|rho|_threshold: `0.7`
- n_names: `0`

## 데이터 요건

- DataFrame with columns: ticker + score_q, score_v, score_sr, score_r, cecs
- Each factor column numeric on a comparable scale (Q/V/SR/R typically 0~100; cecs 0~100).
- One row per name; NaN rows are dropped pairwise per correlation cell.
- Minimum distinct names: scoring.yaml correlation.min_names (default 20) after dropping all-NaN factor rows.
- Point-in-time / same as_of snapshot recommended (do not mix fiscal years across columns).
- Do not impute missing factors with peer means for this report — missingness should remain visible (pairwise complete).
- disclosure_status / independent_catalyst_flag are NOT score factors (mapped to T2 event_candidate_sources).

## SKIP 사유

- no factor DataFrame provided (or empty)

> 가짜 상관·합성 표본으로 수치를 채우지 않음. 요건을 충족하는 스냅샷을 넣은 뒤 재실행할 것.

## 높은 상관 쌍 (후보)

_분석 미실행 — 쌍 목록 없음._

## 통합·단순화 제안 메모

- Cannot propose merges until a real cross-section is supplied.

최종 팩터 단순화 여부는 **OK 리포트의 high_pairs**를 보고 사용자가 판단한다.
