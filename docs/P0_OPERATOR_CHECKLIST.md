# P0 운영자 체크리스트 (코드로 대체 불가)

> 2026-07-19 · v2 — 개발은 도구·게이트까지, **판단·날짜 기입은 사람**

---

## 1. dry-run / Actual Buy

- [ ] `scripts/run_kr_alpha_screen_dry.py` (또는 UI dry) 실행 — 리포트에 **SCALE_IN 3회 스케줄** 섹션 확인
- [ ] 분할매수: 1회차에 종목 배분 전액 넣지 않음 (`SCALE_IN_OPS_RULE` 승인)
- [ ] dry-run 일수·체크리스트 충족 후에만 `go_live_date` 기입 (자동 go-live 금지)
- [ ] Actual Buy는 Review-only 범위·scope 확인 후 사람 승인

## 2. 레짐 · 나침반 (순수 자동)

- [x] `tier2_sources.yaml` `regime_sync_mode: pure_auto` — 산출=적용 (2026-07-20)
- [ ] 홈 「레짐 순수 자동 — 유의」 expander로 완화·노이즈·Tier-2 우려 확인
- [ ] 긴급 수동 고정 시에만 `respect_override` + CSV regime 기입
- [ ] Turbulence: history **26/60행** → **WAIT** — 구현·임계값 변경 금지
- [ ] Method B 결과: excess DSR 비유의 → 나침반 임계값 **유지**

## 3. 주간 정성 · 목표가

- [ ] 금: 요청서 생성 (A~E + **F_QUANT_EVENTS**)
- [ ] 주말: 작성 · 월: 영역별 출처확인·승인
- [ ] B/E = 현재 proposal만
- [ ] 목표가 대기 → 결재함 탭3 E-only 보충 후 승인
- [ ] F에 실적·등급 하향이 있으면 홈 「재채점 검토」만 뜨는지 확인 (점수 불변)

## 4. 익절 스텝 (표시)

- [x] Review-only: `EXIT_STEP_OPS_RULE` — 도달 절반 / 탈락·타임캡 전량
- [ ] **자동 집행(2차)** — 미승인 · 착수 금지
