# kr_alpha 목표값 설정 워크시트 — 명세서 (경량)

> 근거: `EXIT_TAKEPROFIT_THESIS_SPEC.md` §3.1b(목표값은 사람이 유지) 실행 이후, "현재값을 시스템이 불러와 정리해줄 수 있는가"라는 후속 요청 (2026-07-15)
> 원칙: **목표값 자동 산정·제안 아님.** 현재 관측값만 한 곳에 모아 보여주는 순수 읽기 전용 워크시트. `kr_alpha_exit_targets.yaml`은 여전히 사람이 직접 채움.
> 범위: Review-only 출력물 생성. 실행·게이트·target 관련 로직 전혀 변경 없음.

## 0. 전체 그림 — 뭐가 자동이고 뭐가 수동인가 (2026-07-15 확인)

| 단계 | 상태 | 위치 |
|---|---|---|
| ① 알파 후보 추출·스코어링(QVM-SR) | **자동** (기존) | `src/alpha/factor_scoring.py`, `portfolio_selector.py` |
| ② 익절 판정 엔진(계단매핑·모멘텀카운터체크) | **자동** (2026-07-15 구현) | `src/alpha/take_profit_thesis.py` |
| ③ 익절 "목표치"(ROE/PBR 임계값 자체) | **수동 — 사람이 결정** | `data/kr_alpha_exit_targets.yaml` (현재 `tickers: {}`, 전부 비어있음) |
| **본 SPEC** = ③을 쉽게 하기 위한 현재값 정리 워크시트 | 자동이지만 **목표 숫자는 안 채움** | 아래 §2 |

**핵심**: ③이 비어있는 한 ②는 전부 `Hold`/`targets_missing`만 출력한다. 본 워크시트는 ③ 결정에 필요한 현재 관측값을 자동으로 모아주는 것이지, ③ 자체를 자동화하는 게 아니다(자동 목표산정은 `EXIT_TAKEPROFIT_THESIS_SPEC.md` 논의에서 이미 보류 결정됨).

## 1. 왜 낮은 리스크인가

`EXIT_TAKEPROFIT_THESIS_SPEC.md` 논의에서 "목표값(임계치)을 시스템이 자동으로 정하는 것"은 검증 안 된 새 모델을 만드는 것이라 보류했다. 이번 건은 다르다 — **이미 매일 계산되는 현재 관측값(ROE·PBR·배당·소각공시)을 한 표에 모으기만** 하는 것으로, 목표 숫자를 제안하거나 추천하지 않는다.

## 2. 승인 범위

### A. 대상 종목

`data/target_portfolio.csv`에서 `asset_group=kr_alpha`인 현재 7종목 (030200 KT, 021240 코웨이, 005830 DB손해보험, 000660 SK하이닉스, 006040 동원산업, 271560 오리온, 005440 현대지에프홀딩스) + Park 후보(있다면). `EXIT_TAKEPROFIT_THESIS_SPEC.md` §3.1b MVP 범위와 동일.

### B. 출력 컬럼 (전부 "현재 관측값" — 제안·추천 아님)

| 컬럼 | 출처 |
|---|---|
| ticker, name, sector, role | `data/target_portfolio.csv` |
| current_weight_pct, target_weight_pct | 기존 보유/타겟 |
| roe, pbr, dividend_yield, payout_ratio(있으면) | `data/fundamentals.csv` |
| valuation_score, momentum_score | 기존 스코어링 출력 (`alpha_shortlist_diagnostics.csv` 등 이미 있는 산출물) |
| recent_buyback_disclosure | 기존 DART 소각공시 스캔 결과 매핑 (`outputs/research_checklist.json` / hakedaka DART 스캔) — **신규 스크래핑 아님, 이미 도는 스캔 결과 재사용** |
| has_existing_target | `kr_alpha_exit_targets.yaml`에 이미 목표가 있는지 여부 |
| target_roe_min, target_pbr_max, target_payout_min, target_buyback_done | **빈 칸** — 사람이 직접 입력하는 자리. 시스템이 숫자를 채우지 않음 |

### C. 출력 위치

`outputs/kr_alpha_exit_target_worksheet.csv` (+선택적으로 `.md` 요약). 매일 파이프라인 실행 시 갱신(참고용, 실행 게이트와 무관).

## 3. 절대 금지

- `data/kr_alpha_exit_targets.yaml` 자동 기입 — 이 워크시트는 그 파일을 쓰지 않음, 읽기만
- 목표값 칸에 업종평균·과거평균 등으로 **숫자를 미리 채워 넣는 것** — 빈 칸으로 남길 것 (이건 `EXIT_TAKEPROFIT_THESIS_SPEC.md`에서 이미 보류하기로 한 "목표 자동산정"과 같은 문제이므로 이번 범위에서 재도입 금지)
- 네이버·FASTJUSIK 등 신규 스크래핑 — 기존 PyKRX/DART/스코어링 산출물만 재사용
- `target_portfolio.csv`, 실행 게이트, policy_cap, execution_scope 등 어떤 실행 관련 로직도 변경 금지

## 4. 검증 요청

1. 출력 CSV에 kr_alpha 7종목 전부 포함, 각 컬럼 값이 실제 `fundamentals.csv`/스코어링 산출물과 일치하는지
2. `target_roe_min` 등 목표값 관련 컬럼이 전부 빈 값인지 (숫자 자동 채움 없음 확인)
3. `kr_alpha_exit_targets.yaml`이 이번 실행 전후로 변경되지 않았는지 (mtime/내용 diff)
4. 신규 네트워크 호출(스크래핑) 없이 기존 산출물만 읽었는지 소스 확인
