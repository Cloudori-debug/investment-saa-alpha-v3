# 주간 통합 정성 AI 리포트 SPEC

**상태:** 구현 (2026-07-17)  
**코드:** `alpha_system/ui/services/weekly_qual_report.py`, `weekly_domain_gates.py`  
**UI:** 이벤트 탭 → 주간 정성 수집·승인  
**정량 경로:** 홈 「정량 전체 갱신」 또는
`scripts/run_alpha_quant_snapshot.py`

## 운영 리듬

| 시점 | 작업 |
|------|------|
| 금요일 장후 | 요청서 생성 (`weekly_qual_report_YYYYMMDD.md`) → **제안 스냅샷 고정** |
| 주말 | 외부 AI/운용자 작성 (정량 재실행 차단) |
| 월요일 장전 | 업로드 → 영역별 출처 확인 → **필수 게이트**(T2·논지·목표가) 승인 → 고정 해제 |

### 제안 스냅샷 고정 (2026-07-25)

- 요청서 생성 시 `data/weekly_qual_proposal_freeze.json` 기록 (proposal tickers pin)
- 고정 중: `run_quant_snapshot_refresh` / `run_alpha_quant_snapshot` 차단 · UI proposal_book은 pin 순서 유지
- 해제: 필수 게이트 `t2` · `thesis` · `targets` 모두 승인 시 자동 (CECS는 선택·해제 조건 아님)
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
| A_CECS_SUMMARY | shortlist 30종 CECS 3축 | `cecs` |
| B_FINAL6_DEEP | 제안 6종 심층 | (참고, CECS 인접) |
| C_T2_EVENTS | 상법/MSCI/IFRS18 | `t2` |
| D_THESIS | 논지 훼손 | `thesis` |
| E_TARGET_VALUATION | 목표가/PBR | `targets` |

## 불변

- AI는 제안만. 엔진은 **승인된 입력만** 소비
- 영역 실패/미승인이 다른 영역을 자동 승인·취소하지 않음
- `target_portfolio.csv` 자동 쓰기 금지 (목표가 승인은 exit YAML만)
- 업로드만으로 CECS `final`을 덮어쓰지 않음
- CECS 영역 승인 시에는 출처 확인·명시적 승인 동작 안에서만
  `final → ai_suggested → final`을 즉시 수행하고 원장에 기록
- FASTJUSIK 금지 · `proposal_mode: pure_qvm` 유지

## 목표가 대기 보충 (E only)

제안 북 중 `kr_alpha_exit_targets.yaml`에 아직 없는 종목만 대상으로 한다.

| 단계 | 동작 |
|------|------|
| 생성 | `weekly_qual_targets_supplement_YYYYMMDD.md` — `E_TARGET_VALUATION`만 |
| 업로드 | `persist_targets_supplement` — **targets만** 병합, CECS/T2/논지 유지 |
| 승인 | 기존 목표가 카드만 · exit YAML만 갱신 · `target_portfolio.csv` 불변 |

- `deep_tickers` = 현재 proposal_book 전체 (편입 게이트 allowlist)
- proposal 밖·대기 목록 밖 종목은 업로드 거부

## 저장물

- 요청서: `docs/weekly_qual_report_YYYYMMDD.md`
- 목표가 보충: `docs/weekly_qual_targets_supplement_YYYYMMDD.md`
- 미승인 제안 봉투: `data/weekly_qual_suggestions.json`
- 정량 provenance: `data/alpha_quant_snapshot_provenance.json`
- 스코어: `alpha_portfolio/data/output/alpha_scores.csv`

## 검수

1. 요청서 1개에 A~E 섹션 존재
2. 업로드 후 domain `ai_suggested`, 출처 미확인 시 승인 불가
3. CECS 승인만으로 T2/논지/목표가 미확정
4. UI 제안 6종 = dry CLI 6종
5. 목표가 승인 후 `target_portfolio.csv` 해시 불변
6. 미승인 정성 입력이 eligibility/트리거에 미반영
7. 대기 보충은 E만 생성·병합하며 다른 domain 상태를 지우지 않음
