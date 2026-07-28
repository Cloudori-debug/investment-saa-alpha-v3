# 스크린 → 객관 6종 dry 리포트 — SPEC

> **상태:** 원장 결정 확정 · dry CLI 구현 완료 (2026-07-17)  
> **결정:** 선정 정책 **B**  
> **불변:** `target_portfolio.csv` 자동 변경 금지 · `proposal_mode: pure_qvm` · kr_alpha Review-only · 매매는 시스템 밖

---

## 0. 원장 결정 (B)

| 항목 | 결정 |
|------|------|
| 목표 | 레거시 보유를 “기본 포트”로 쓰지 않고, **현재 시스템 스크린·채점 결과로 객관 후보 6종**을 뽑는다 |
| shortlist | 보유 종목이 **들어가도 된다** (참고·청산 재료 포함 가능) |
| 선정 | **점수·eligibility만** — 보유 여부 가산·강제 포함 **금지** |
| 결과 | 레거시가 상위 적격이면 잔류 가능 / 아니면 탈락 — 둘 다 정상 |

A(완전 배제)와의 차이: 점수가 높은 보유는 B에서만 살아남을 수 있음.

---

## 1. 기존 문서와의 관계

| 문서 | 관계 |
|------|------|
| `CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md` | 30종 shortlist의 **P0=보유 전원 포함**·`1000×is_held`는 **채점 풀 구성**용. **본 SPEC의 포트 선정에는 적용하지 않음** |
| `KR_ALPHA_HYBRID_TRANSITION_*` | 슬리브 축소(2종+ETF) 트랙 — **별도**. 본 SPEC은 **종목 선정 방법** |
| `KR_ALPHA_STRATEGY_ROADMAP.md` | forward-return 전 “성급한 집중” 금지와 충돌하지 않음 — 본 산출은 **dry 리포트·승인 후보**만, live 집중 전환은 별도 게이트 |
| `ALPHA_SYSTEM_UIUX_MASTER_SPEC.md` | 포트 UI는 당분간 레거시 감시면 “이행대기” 유지; 승인 북 반영 후 감시 대상 교체 |

---

## 2. 파이프라인 (자동 target 쓰기 없음)

```
CECS template (status=final 우선) + 팩터 스코어
  → scoring.score_cutoff 확정 (아직 null이면 dry는 “컷 가정” 시나리오만)
  → eligibility=True 집합
  → total_score / weight_input 내림차순
  → 상위 sizing.target_names(=6)  (is_held 부스트 없음)
  → 종목별 비중 초안 (allocate_tranche 규칙, 트랜치 합산은 별도)
  → outputs/ 또는 docs/ 리포트만 기록
  → 사람 승인 시에만 target_portfolio / 목표가 yaml
```

**금지**

- `is_held`·`positions.csv`로 순위 올리기  
- dry 결과를 `target_portfolio.csv` / `positions.csv`에 자동 기록  
- 하케다카·수급으로 순위 변경 (`pure_qvm`)

---

## 3. 산출물 (구현 시)

| 산출 | 내용 |
|------|------|
| dry 리포트 MD/CSV | 적격 전체 순위 · 선정 6종 · 탈락 보유(점수·사유) · 비중 초안 |
| 메타 | as_of, cutoff(확정값 또는 가정값), `selection_policy: B` |
| 저널(선택) | `SCREEN_DRY_REPORT` append-only — 파일 경로만 |

UI: 홈/스코어에 “dry 6종 (미승인)” 읽기 전용 섹션은 **후순위** (리포트 파일이 1차).

---

## 4. 선행 조건 (체크리스트)

1. CECS 30종 중 가능한 범위 `status=final` (전부 전이면 분포·cutoff 논의)  
2. 원장이 `score_cutoff` 확정 **또는** dry용 가정 컷 명시  
3. `kospi_market_pbr_history` 등은 go-live용 — **dry 선정에는 비필수**  
4. 선정 6종에 대해 목표가 워크시트는 **승인 직전** (채점 전 소급 목표가 금지 — 기존 B안과 동일)

---

## 5. 검수

1. 동일 입력에서 `is_held=true`를 꺼도 선정 6종이 불변인가 (부스트 없음)  
2. 보유이면서 컷 미달인 종목이 “탈락 보유”로 리포트에 나오는가  
3. `target_portfolio.csv` mtime/해시가 dry 실행 전후 동일한가  
4. 리포트에 `selection_policy: B`가 명시되는가  

---

## 6. 다음 구현 단위

1. ~~cutoff 분포 요약 스크립트/리포트 (final 진행률 포함)~~ — dry 리포트 메타에 포함  
2. ~~`selection_policy=B` dry allocator CLI → CSV+MD~~ — 구현 완료  
3. CECS `final` 채점 후 원장이 cutoff 확정 또는 dry 가정값 승인  
4. (선택) 대시보드 읽기 전용 노출  

### 실행

```powershell
python scripts/run_kr_alpha_screen_dry.py --assumed-cutoff <원장 승인 가정값>
```

- config의 `scoring.score_cutoff`가 확정되면 `--assumed-cutoff` 생략 가능
- 기본 입력:
  - `alpha_portfolio/data/output/alpha_scores.csv`
  - `data/cecs_manual_scoring_template.csv`
  - `data/positions.csv` (보유 표시만; 순위 입력 아님)
- 기본 출력:
  - `outputs/kr_alpha_screen_dry.csv`
  - `outputs/kr_alpha_screen_dry.md`
- `status=final`만 선정에 사용한다. 연구용 `--allow-draft`도 CECS 완성 행만 계산한다.
- `target_portfolio.csv`는 실행 전후 SHA-256 불변을 검사한다.

*승인·go-live·실매매는 본 SPEC 범위 밖.*
