# 주간 통합 정성 AI 리포트 SPEC

**상태:** 구현 (2026-07-17) · 실측범위 (2026-07-31) · **익절 앵커·CECS 원장 고정 (2026-08-03)**  
**코드:** `alpha_system/ui/services/weekly_qual_report.py`, `weekly_domain_gates.py`  
**UI:** 이벤트 탭 → 주간 정성 수집·승인  
**정량 경로:** 홈 「정량 전체 갱신」 또는
`scripts/run_alpha_quant_snapshot.py`  
**프롬프트:** [`WEEKLY_QUAL_CDE_PROMPT.md`](WEEKLY_QUAL_CDE_PROMPT.md)  
**익절 정책:** [`EXIT_TARGET_ANCHOR_POLICY.md`](EXIT_TARGET_ANCHOR_POLICY.md)

## 실측·증명 원칙

웹검색만으로 재현·교차확인이 안 되는 질문은 **주간 AI 필수에서 제외**한다.

| 항목 | 주간 | 소스 |
|------|------|------|
| C T2 | 선택 | 관보 · MSCI 공식 · 금융위/KASB |
| D 논지 | 선택 | 제도 훼손 **확정** 여부 |
| E 목표가 | 대기분·선택 | **실측 앵커만** (BPS·trailing PBR·52주) · 증권사 SoT **금지** |
| A execution | 템플릿 | DART — **순위는 `score_sr` SR4** |
| A pension / purpose | 템플릿 잠정 50 | Ops A 순위 미반영 |
| 월간 CECS | 선택 원장 | execution만 · 순위·편입 **무관** |

- 요청서 생성 시 pension/purpose는 `50` + `system:weekly_neutral_hold`(주간) /
  `system:monthly_neutral_hold`(월간).
- E = 익절 YAML **장부 재료** (공정가치 예측 아님). 기존 YAML 일괄 재계산 없음.
- Self-check가 “passed”인데 execution이 `_____`이면 **미완**으로 취급.

### CECS 역할 (모순 해소)

| 역할 | 어디 | 순위 |
|------|------|------|
| 환원 연속성 | 정량 `score_sr` SR4 | **반영** |
| CECS execution | 월간 원장 CSV | **미반영 (Ops A)** |
| pension / purpose | 잠정 50 | **미반영** |

CECS를 `total_score`에 재혼합하지 않는다.

## 운영 리듬

| 시점 | 작업 |
|------|------|
| 금요일 장후 | 요청서 생성 (`weekly_qual_report_YYYYMMDD.md`) → **제안 스냅샷 고정** |
| 주말 | 외부 AI/운용자 작성 (정량 재실행 차단) — C→D→E→A(execution) |
| 월요일 장전 | (선택) 업로드 → 출처 확인 → T2·논지·목표가 승인. 홈 필수 아님 · 증권사 SoT 거부 |

### 제안 스냅샷 고정 (2026-07-25)

- 요청서 생성 시 `data/weekly_qual_proposal_freeze.json` 기록 (proposal tickers pin)
- 고정 중: `run_quant_snapshot_refresh` / `run_alpha_quant_snapshot` 차단 · UI proposal_book은 pin 순서 유지
- 해제: 정책 on일 때 `t2` · `thesis` · `targets` 승인 시 자동 (CECS·주간은 홈 비필수 · freeze 기본 off)
- `target_portfolio.csv` 불변 · 순위 엔진은 Ops A(정량 100%) 유지

## 단순화된 조작

1. 요청서 생성·다운로드
2. 완성본 업로드 1회 — 파서가 A~E를 영역별 `ai_suggested`로 분리
3. 공통 승인자 1회 입력
4. 영역 카드에서 출처를 확인하고 **그 영역만 승인**

- 출처 확인 저장과 영역 적용은 승인 버튼 한 번으로 처리한다.
- T2 2단계·논지 3단계 확인은 영향이 큰 해당 카드에만 유지한다.
- 실패 영역은 승인할 수 없고 재업로드로 보완한다. 다른 영역 승인은 유지한다.

## 섹션

| ID | 내용 | 승인 domain |
|----|------|-------------|
| A_CECS_SUMMARY | execution(+잠정 pension/purpose) | `cecs` (월간 레인) |
| B_FINAL6_DEEP | 제안 심층(선택·DART/IR) | (참고) |
| C_T2_EVENTS | 상법/MSCI/IFRS18 | `t2` |
| D_THESIS | 논지 훼손 | `thesis` |
| E_TARGET_VALUATION | 익절 장부 재료 | `targets` |

## 불변

- AI는 제안만. 엔진은 **승인된 입력만** 소비
- 영역 실패/미승인이 다른 영역을 자동 승인·취소하지 않음
- `target_portfolio.csv` 자동 쓰기 금지 (목표가 승인은 exit YAML만)
- 업로드만으로 CECS `final`을 덮어쓰지 않음
- FASTJUSIK 금지 · `proposal_mode: pure_qvm` 유지 · Ops A CECS 가중 0

## 목표가 대기 보충 (E only)

제안 북 중 `kr_alpha_exit_targets.yaml`에 아직 없는 종목만. 실측 앵커 정책 적용.

## 저장물

- 요청서: `docs/weekly_qual_report_YYYYMMDD.md`
- 월간 CECS: `docs/monthly_cecs_report_YYYYMMDD.md`
- 목표가 보충: `docs/weekly_qual_targets_supplement_YYYYMMDD.md`
- 미승인 제안: `data/weekly_qual_suggestions.json` · `data/monthly_cecs_suggestions.json`

## 검수

1. 요청서 A~E · pension/purpose 잠정 50
2. 월간 요청서는 A만 · `system:monthly_neutral_hold`
3. E 규칙에 EXIT_TARGET_ANCHOR 문구
4. 목표가 승인 후 `target_portfolio.csv` 해시 불변
5. CECS 승인만으로 순위·편입 불변
