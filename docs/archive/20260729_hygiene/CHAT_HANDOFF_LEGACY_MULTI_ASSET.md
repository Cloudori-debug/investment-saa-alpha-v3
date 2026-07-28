# 채팅 승계 핸드오프 (레거시 multi_asset → investment-saa-alpha)

> **목적:** `C:\Cursor` 워크스페이스의 구 채팅(레거시 `multi_asset_trigger_portfolio` 개발·하케다카·FASTJUSIK 논의)에서 확정된 결정을 **SAA 알파 투자 채팅**이 그대로 이어받게 한다.  
> **코드 루트 (v2):** `C:\Cursor\investment-saa-alpha-v2`  
> **v1 유지판:** `C:\Cursor\investment-saa-alpha` — 여기에 v2 기능을 넣지 말 것  
> **v2 차터:** [`V2_CHARTER.md`](V2_CHARTER.md)  
> **원본 채팅 transcript:** `93ceb171-5386-4466-a75e-f5010b0da3b4`  
> **작성일:** 2026-07-11 · **v2 분기:** 2026-07-19

**다른 채팅에서 시작할 때:** `V2_CHARTER.md` + 이 파일을 읽고, 아래 「불변 규칙」을 어기지 말 것.

---

## 0b. 단일 채팅방 운영 (2026-07-14)

| 항목 | 내용 |
|------|------|
| **공식 채팅 제목** | `SAA 알파 투자` |
| **원칙** | 이 프로젝트 작업은 **이 채팅 하나**에서 이어간다. 주제가 갈라져도 새 채팅을 남발하지 말 것. |
| **새 채팅이 필요한 경우** | 컨텍스트가 너무 커져 응답이 불안정할 때만. 새 채팅 첫 메시지에 이 핸드오프를 읽게 하고, 아래 「최근 완료」만 한 줄로 넘긴다. |
| **다른 채팅** | 같은 주제의 옛 채팅(구 multi_asset / 단발 조사)은 핸드오프·RESULT 문서에 결정이 있으면 **삭제해도 됨**. Cursor는 채팅을 자동 병합하지 않음 — 사이드바에서 수동 삭제. |

### 최근 완료 (이 채팅에서 이어받음)

| 영역 | RESULT / 요지 |
|------|----------------|
| **종목별 교체 안내** | 보유「실투자 포트 · 종목별 안내」글 표시. 전체 나침반 제거 (2026-07-28) |
| **실보유 붙여넣기** | 보유「실보유 입력」· HTS `코드 수량 평단` → positions.kr_alpha만 upsert · 홈「실보유 입력」딥링크 (2026-07-28) |
| **모멘텀 Review-only** | 홈 위계: 오늘→교체나침반→후보·모멘텀→월리밸. `MOMENTUM_REVIEW_ONLY_SPEC` (2026-07-28) |
| **v3 분기** | C:\\Cursor\\investment-saa-alpha-v3 활성. 홈「월 리밸 · 오늘 할 일」보드(밴드/신호/CRISIS/SCALE_IN). (2026-07-28) |
| **월 리밸 홈 보드** | ①밴드±25% ②익절·게이트 ③CRISIS 예외 ④SCALE_IN 제외 — Review-only · target 자동변경 없음 (2026-07-28) |
| **정량 잠금 영구 off** | \data/proposal_freeze_policy.json\ enabled=false · 활성 freeze 해제. 설정「정량 잠금 정책」토글. (2026-07-28) |
| **positions 고스트 삭제** | \data/positions.csv\·raw에서 kr_alpha 행 전부 제거(ETF/현금만 유지). target_portfolio는 별도. (2026-07-28) |
| **정량 freeze 영구 해제** | `proposal_freeze_policy.json` enabled=false 기본. 요청서 생성해도 정량 잠금 없음. 설정「정량 잠금 정책」토글. (2026-07-28) |
| **고스트 보유 방지** | `positions.csv`에서 kr_alpha 제거·git 추적 해제(.gitignore). 재발=git checkout/복원 차단. (2026-07-28) |
| **목표가 YAML 보호** | 요청서 생성≠YAML 삭제. E=이미승인 `TARGET_REF` / 대기만 `TARGET`. 보충·승인 시 기존 pbr/목표가 덮어쓰기 방지 (2026-07-28) |
| **비서 UI (B안)** | 사이드바 표시=오늘/확인/보유+더보기(내부 키 홈/결재함/포트 유지). 확인 센터 탭=①숫자·②이번 주·③이번 달·④가동. 홈=오늘 할 일·후보·시작하기 3분. (2026-07-28) |
| **바로 UI 실행 (A안)** | `Start-Ops-Assistant.vbs` → CMD 최소화·브라우저 전면. `run_ui_direct.bat` · `START_OPS_ASSISTANT.bat` [5]. `투자나침반.bat`=VBS 래퍼. (2026-07-28 복원) |
| **운용 비서 이식 MVP** | `ops_assistant_pack` · 설정「이식·백업」·`scripts/make_ops_backup.py` · `docs/OPS_ASSISTANT_WINDOWS_PORTABLE.md`. (2026-07-28 복원) |
| **주간/월간 정성 분리** | `weekly_qual_suggestions.json`(C/D/E) ↔ `monthly_cecs_suggestions.json`(CECS). 월간 업로드가 주간을 덮지 않음. (2026-07-28 복원) |
| **Ops A CECS** | `total_score` = 정량 100%(cecs 가중 0). 정성 필수=T2·논지·목표가 게이트. CECS는 선택·순위 미반영. 결재함 UI 필수/선택 분리. cutoff/go-live CECS 차단 해제 (2026-07-25) |
| **판매형 1차 IA** | 메인 메뉴=사이드바 큰 버튼+힌트(홈→결재함→포트폴리오→저널→레짐→설정). 상단 ops 스트립·이중 브랜드 제거. 홈=할 일→판정3칸→제안, 나머지 접힘. (2026-07-25) |
| **제안 스냅샷 고정** | 주간 요청서 생성 시 `weekly_qual_proposal_freeze.json` · 정량 재실행 차단 · UI proposal pin · 필수 게이트(T2·논지·목표가) 승인 시 해제. target 자동변경 없음 (2026-07-25) |
| kr_alpha min/max 밴드 | `TARGET_MINMAX_BAND_FIX_RESULT` — 예산 스케일 시 min/max 동반 |
| 위성 캡 | `SATELLITE_CAP_ALIGNMENT_RESULT` — sleeve×budget 동적 캡, 071050 정렬 |
| 레짐 격차 경고 | `REGIME_OVERRIDE_DIVERGENCE_ALERT_RESULT` — AC-05b |
| 격차 지속 에스컬레이션 | `REGIME_DIVERGENCE_ESCALATION_RESULT` — 로그 3일째 재촉 (소급 없음) |
| Alpha BT 표본 라벨 | `ALPHA_BACKTEST_SAMPLE_QUALITY_FIX_RESULT` — scored_days_used 기준 품질 |
| 실행.bat 「멈춤」 | 실제 hang 아님(5~10분). CLI 진행 메시지 추가 |
| 레짐 만료·재검토 | `REGIME_OVERRIDE_EXPIRY_REVIEW_FIX_RESULT` — 만료 시 policy_cap↔computed 정합, AC-05c/AC-05 승격 |
| 레짐 재분류 CAUTION | `REGIME_CAUTION_RECLASSIFICATION_RESULT` — YELLOW→CAUTION(수동) 원장 검증 완료(2026-07-14). fsr perms 정합, gap 3→2·escalation 리셋. scope 불변·ops target 자동 미반영. 다음 판단: AC-05b/05c 또는 ≤8/14 |
| 익절·테제·비중 갭 점검 | `EXIT_WEIGHT_GAP_AUDIT_RESULT` — P0 확정 |
| CECS AI 배치 승인 | 고정 Markdown 요청서·업로드 파서·`ai_suggested` 저장·종목별 출처 확인 게이트·개별/배치 승인·감사 저널 구현 |
| 익절·테제 1차(가시성) | `EXIT_TAKEPROFIT_THESIS_RESULT` — assess_*+보드+빈 YAML. target 자동변경 없음. 목표가 기입·2차는 별도 승인 |
| 목표가 워크시트 | `KR_ALPHA_EXIT_TARGET_WORKSHEET_RESULT` — 원장 검증 완료. yaml 목표치는 아래 「exit targets 기입」 |
| exit targets 기입 | `kr_alpha_exit_targets.yaml` 7종(KT·코웨이·DB손보·동원·오리온·SNT·현대GF) 기계적 초안 반영(2026-07-15). 000660 의도적 미설정. assess_take_profit: 7종 targets_missing=False·전부 Hold/NONE. 보드 CSV는 **전체 분석 재실행** 후 UI 반영 |
| target write 03:53 조사 | `TARGET_WRITE_AUDIT_20260715_INVESTIGATION_RESULT` — 원장 본인 승인 확인·종결 |
| 익절 보드 대시보드 | `ALPHA_SIGNAL_BOARD_DASHBOARD_EXPOSURE_RESULT` — 알파→보유 리뷰만 (⑥·Target 승인 노출 되돌림) |
| Gap 표 익절 참고 | `GAP_TABLE_EXIT_SIGNAL_REFERENCE_RESULT` — Gap에 익절상태(+근접도 접미사) |
| 익절 목표 근접도 | `EXIT_TARGET_PROXIMITY_RESULT` — 미도달 시 VAL/FUND % 근접 표시(확률 아님). 보드 재생성 완료 |
| 익절 표 범례 | `EXIT_SIGNAL_TABLE_LEGEND_RESULT` — 보유 리뷰 범례+Gap 한 줄 안내(표시만) |
| 익절 목표 제안규칙 | `EXIT_TARGET_SUGGESTION_RULE_RESULT` — 워크시트 suggested_* (role+ROE). target_*/yaml 자동기입 없음 |
| cleanup phase 0 | `CODEBASE_CLEANUP_PHASE_0_RESULT` — `alpha_v0_2` archive 완료·원장 검증 종결 (2026-07-15) |
| cleanup phase 1 | `CODEBASE_CLEANUP_PHASE_1_RESULT` — value_list archive · 원장 라이브 검증 종결(2026-07-15 20:34 log / daily_report disabled 문구). **종결** |
| cleanup phase 2 | `CODEBASE_CLEANUP_PHASE_2_RESULT` — alpha_v2·alpha_flow archive 원장 검증 종결(2026-07-15). 커밋 `548effa`. **종결** |
| 경제 나침반 0·1 | `ECONOMIC_COMPASS_PHASE_0_1_RESULT` — 원장 검증 종결(2026-07-16). tilt×0.4 실증·히스테리시스는 override 없는 날 관찰 지속. **종결** |
| target write 추적성 | `TARGET_WRITE_AUDIT_TRACEABILITY_FIX_RESULT` — 원장 검증 완료(2026-07-15). material=21·승인자 필수·writer_module·toast. 건 종결 |
| 익절 목표상태 마커 | `EXIT_TARGET_STATUS_MARKER_RESULT` — 원장 검증 완료(2026-07-15). name 다음 ⚠️/✅·배너·target_* 공란. 건 종결 |
| 정량+주간정성 재설계 | scoreboard=`alpha_scores`·proposal/ops 북 분리·CECS final 보호·`run_alpha_quant_snapshot`·주간 A~E 요청서/영역별 게이트·`WEEKLY_QUAL_REPORT_SPEC` (2026-07-17) |
| 홈·수집·승인 단순화 | 홈=`자동 준비 2칸 + 지금 할 일 1건 + 제안 결과 + 접힌 운용`; 정량 전체 갱신 1클릭; 정성 1파일·승인판 1화면 (2026-07-17) |
| 결재함 전용 UI | 메뉴=`홈·결재함·포트폴리오·저널`. CECS/T2/논지/저널 직접기입 제거. 수집→출처확인→영역별승인만 (`approval.py`, 2026-07-17) |
| 편입 수·컷오프 연동 | 철학 정합 복원: **절대 cutoff 먼저 → 편입 수 5~8(기본 6)**. 6~30 상대순위 슬라이더는 설계 충돌로 철회. target 자동 변경 없음 (2026-07-18) |
| 최종선정 갭보완 | 절대 cutoff → 섹터당≤2(`sector_group`) → 5~8. 목표가 없으면 대기후보·편입 차단(다음 주 E). B/E는 proposal만(CECS fallback 제거) (2026-07-18) |
| 안정판 저장 | 커밋 `614a87c` + 태그 `stable-20260718-final-selection`. 검증 문서 `ALPHA_FINAL_SELECTION_HARDENING_RESULT`(Claude 재검증용). focused 37 passed (2026-07-18) |
| cleanup A+C | 상대순위 슬라이더 제거(포트폴리오 절대컷만). 죽은 페이지·디버그 스크립트 → `archive/20260718_*`. `CODEBASE_CLEANUP_AC_20260718_RESULT` (2026-07-18) |
| cleanup B+D | 대체 API(AI검증·CECS writer·save_cecs_score) + 일회성 스크립트 8개 archive. `CODEBASE_CLEANUP_BD_20260718_RESULT` (2026-07-18) |
| Claude 검수 브리프 | `docs/CLAUDE_REVIEW_BRIEF_20260718.md` — P0 하드닝·P1 cleanup 잔재·불변규칙. 외부 Claude 붙여넣기용 (2026-07-18) |
| 검수 채택 3건 반영 | provisional 배지(빈점수→50) · deep_tickers fail-closed · entry 목표가 게이트 SoT 일원화 (`missing_entry_target_tickers`) (2026-07-18) |
| 목표가 대기 보충 | E-only 요청서·업로드 병합·결재함 탭3. 섹터 캡(≤2)·스타일 인원캡 없음 — **변경 없음** (2026-07-18) |
| **보유 점검 UI** | 제안 북 익절 스텝만 · 실보유 탈락「전량」목록 제거 · positions에서 미보유 5종 삭제 (2026-07-20) |
| **분할매수 운영 승인** | `SCALE_IN_OPS_RULE.md` **승인(2026-07-19)**. 종목 집행 3회 균등·≥3거래일. 목표가 틸트·차트·수급 순위변경 비범위 |
| **P0/P1 코드 일괄** | SCALE_IN dry·집행캡 · F_QUANT_EVENTS · rescore 큐/저널 · 컨센서스 불가 문서 · P0 운영 체크리스트 (2026-07-19). Turbulence/Actual Buy/CAUTION 판단은 운영자 |
| **레짐 순수 자동** | `regime_sync_mode: pure_auto` — 산출=적용·수동 CAUTION 해제. 동기화 결과 **CRISIS**. 홈 expander에 완화·노이즈·Tier-2 우려. QVM 불변 (2026-07-20) |
| **ABC 평가 패치** | 가격결측→데이터없음(유지 금지) · 보험→금융 테마캡 · 섹터비중 경고 UI · DB손보 revalidate_required (2026-07-20) |
| **홈 시스템 판정** | 메인「검증」메뉴 없이 홈 단원(레짐·T3·다음 판정) · ops 카드 유지 · 결재함 T3/설정 딥링크 (2026-07-20) |
| **적격 순위 감시** | 포트폴리오「적격 순위 감시」보드(≤30, 표시만) · 보유 순위·제안밴드 밖 표시 · target_names 5~8 불변 (2026-07-24) |
| **레짐 메뉴** | 메인「레짐」+ UI **나침반·레짐 분석 실행**(런처 [3]과 동일, target 미승인) (2026-07-24) |
| **섹터 합산 35%** | 동일 섹터 2종+ 시 sleeve 합산 ≤35% (`sector_weight_cap`) · 인원캡 ≤2 유지. 1종=과비중 아님; 2종은 테마 허용·합>35%만 과비중 (2026-07-20) |

### Alpha BT 라벨 — 검증 완료 (2026-07-14, 옵션 a 종료)

- 독립 검증: 코드/csv/report/테스트 일치. `scored_days_used=10`, `price_history_days=270`, `sample_quality=insufficient`.
- 수익률·quintile 수치(excess -8.26% / net -8.79% 등)는 **재계산 없음·재생성만** — 계산 로직 불변 확인.
- `insufficient` = 시스템 스스로 「예측력 판단 불가」. 넷초과·quintile 역전은 **스코어링 버그 증거가 아니라 표본 부족으로 무의미**.
- **옵션 (b)** (과거 분기별 발표시점 재무 히스토리 구축)는 **후순위** — dry-run 완료 · policy_cap · 레짐 divergence 해소가 먼저.

### 열린 항목 (짧게 · 우선순위)

1. dry-run / policy_cap / Actual Buy — **운영자** (`P0_OPERATOR_CHECKLIST`). 코드: SCALE_IN dry·1회차 캡 완료
2. ~~CAUTION 재검토~~ — **순수 자동 전환**(2026-07-20). 적용=산출(동기화 시 CRISIS). 우려는 홈 레짐 expander. 긴급 고정 시 `regime_sync_mode: respect_override`
3. **경제 나침반** — Turbulence **26/60 WAIT**; 임계값 미변경
4. **익절 스텝 규칙** — Review-only 표시 승인 (`EXIT_STEP_OPS_RULE`). **자동 집행(2차)는 미승인**
5. 주간 정성 운영 — F_QUANT_EVENTS 추가됨. 작성·승인은 운영자
6. ~~객관 고점수·섹터분산~~ — 완료
7. (후순위) Alpha BT 옵션 b
8. ~~목표가 대기 보충~~ — E-only 완료
9. ~~P1 컨센서스 조사·재채점 신호 MVP~~ — 완료 (자동 수집 불가·수동 F·큐만)
10. ~~모멘텀 Review-only 표시(A안)~~ — 완료 (2026-07-28) `MOMENTUM_REVIEW_ONLY_SPEC`
11. ~~월 리밸 홈 보드~~ — 완료 (2026-07-28)
---

| 구분 | 의미 | 현재 기본 |
|------|------|-----------|
| **Executable** | 계좌에서 실제로 해도 시스템과 맞는 액션 | ETF·현금·채권 (scope 허용 시) |
| **Research / Review-only** | 참고·사람 승인만 | kr_alpha, 하케다카, 수급(FASTJUSIK류) |
| **제안 포트** | `alpha_portfolio_proposal` 순위 | `proposal_mode: pure_qvm` |
| **승인 포트** | `data/target_portfolio.csv` | **사람만** 변경 (자동 금지) |

실투자: **ETF executable**, **개별주/하케다카/수급은 Review-only** 유지.

---

## 1. 불변 규칙 (AC-HK + 실행 분리)

상세: [`HAKEDAKA_ACCEPTANCE.md`](HAKEDAKA_ACCEPTANCE.md), [`HAKEDAKA_KR_ALPHA_POLICY.md`](HAKEDAKA_KR_ALPHA_POLICY.md)

| ID | 규칙 |
|----|------|
| AC-HK-01 | `liquidity_pass=false` → 제안 포트 편입 불가 |
| AC-HK-02 | `hard_slot_enabled=false` — 하케다카만으로 편입 불가 |
| AC-HK-05 | `shadow_slot_candidate`는 표시용 — target 자동 변경 없음 |
| AC-HK-06 | sector / single-name / kr_alpha cap 항상 우선 |
| 실행 | `ETF_ONLY` 등일 때 kr_alpha는 **Review-only** (`execution_scope.py`) |
| 유동성 | `liquidity_bypass_for_proposal: false` — 우회 금지 |
| tie-breaker | 기본 OFF. shadow 2~4주 관찰 후에만 `qvm_with_tiebreaker` 검토 |

`data/hakedaka_integration.yaml` 핵심 기본값:

```yaml
proposal_mode: pure_qvm
hakedaka_tiebreaker_enabled: false
liquidity_bypass_for_proposal: false
hard_slot_enabled: false
shadow_slot_candidate_enabled: true
```

---

## 2. 프로젝트·경로 맵

| 이름 | 경로 | 역할 |
|------|------|------|
| **현재 본체** | `C:\Cursor\investment-saa-alpha` | 나침반 + SAA/TAA + 알파 + UI |
| CECS 스크리너 | `investment-saa-alpha/alpha_portfolio` | QVM 하위 패키지 |
| 구 폴더 | `C:\Cursor\multi_asset_trigger_portfolio` | 레거시(있으면 참고만, 작업은 saa-alpha에서) |
| UI 진입 | `투자나침반.bat` / `streamlit run app.py` | |

파이프라인 대략 순서: **나침반 → 하케다카 DART → 알파 → 리서치/오버레이 → acceptance**

---

## 3. 하케다카 연동 (이미 구현된 것)

| 영역 | 파일 / 산출물 |
|------|----------------|
| DART 공시 | `src/value_list/dart_disclosure.py` |
| DART 검증 | `outputs/hakedaka_dart_verification.csv` |
| overlap 진단 | `outputs/hakedaka_overlap_diagnostics.csv` |
| 우선 검토 | `outputs/hakedaka_priority_review.csv` |
| 알파 브릿지 | `src/value_list/alpha_bridge.py` |
| SAA/TAA 오버레이 | `src/value_list/compass_overlay.py` |
| 수용 테스트 | `tests/test_hakedaka_acceptance.py` |

**정책 합의:** 최종 제안 포트에 하케다카 **강제 편입 비추**. soft preference / shadow만.  
overlap이 적을 수 있음 → 버그 아님 (유동성·시총·pillar 탈락이 대부분).

---

## 4. FASTJUSIK (`fastjusik.com/pension`) — 레퍼런스만

| 할 것 | 하지 말 것 |
|-------|------------|
| KRX / PyKRX로 동일 지표 직접 계산 | 사이트 스크래핑 |
| 수급은 **shadow / Signal Board / 승인 탭** | 수급만으로 proposal 편입 |
| `institution_*` = 기관 proxy (연기금 100% 아님 명시) | HTS「기관계」=「연기금」동일시 |

### FASTJUSIK → 프로그램 매핑

| FASTJUSIK | 프로그램 | 상태 |
|-----------|----------|------|
| 당일 순매수/매도 | `investor_flows` / institutional flow | 부분 구현 |
| 연속 수급 | streak | `alpha_v2`/`alpha_flow`는 `archive/20260715_*`로 격리(2026-07-15). v1 `investor_flows`·신호보드 경로는 유지 |
| 외국인 동반 | foreign+institution 부호 일치 | 확장/표시 |
| 방향 전환 | 연속 후 반전 | 확장/표시 |
| NPS 5% 보유 | DART 대량보유 | 선택 확장 |
| 경제지표 | compass / market_indicators | 이미 있음 |

**원칙:** FASTJUSIK는 「누가 사고 있나」 참고, 시스템은 「사도 되나」(QVM·유동성·Scope).

---

## 5. Executable vs Research (실투자 기준)

**해도 됨 (조건 충족 시)**  
- Executable 섹션 ETF/현금/채권  
- 데이터 최신 + 트리거 + 본인 승인  

**하면 안 됨 (시스템과 불일치)**  
- kr_alpha 신규·Replace를 Executable처럼 실행  
- 하케다카·수급 단독으로 target 자동 변경  
- dry-run 미충족인데 실운용 자동 승인으로 간주  

리포트는 **Executable** / **Review-only** 섹션을 섞지 말 것.

---

## 6. UI·운용 합의

- 사용법 탭, 상태 배너, 대시보드에 executable 요약  
- Target 승인 UI만 `target_portfolio` 변경  
- 하케다카 탭: diagnostics + shadow 후보 (강제 슬롯 아님)  
- 수급: Target 승인 / 하케다카에 「기관 수급」 우선 노출 (표시만)

---

## 7. 미완료 / 다음 작업 (레거시 채팅 기준)

당시 합의된 다음 스텝 (saa-alpha에서 이미 일부 구현됐을 수 있음 — **코드 대조 후** 진행):

1. `investor_flows_history` append + streak/동반/전환  
2. diagnostics·signal board에 shadow 플래그만 병합 (`flow_role: shadow_only`)  
3. Target 승인 「수급 우선 검토」 UI  
4. (선택) DART NPS 5%  
5. shadow 2~4주 후 tie-breaker A/B — yaml만, AC-HK 유지  

구현 시 **proposal_mode=pure_qvm** 기본 유지.

---

## 8. 관련 문서 (우선 읽기 순서)

1. 이 파일 (`CHAT_HANDOFF_LEGACY_MULTI_ASSET.md`)  
2. [`HAKEDAKA_ACCEPTANCE.md`](HAKEDAKA_ACCEPTANCE.md)  
3. [`HAKEDAKA_KR_ALPHA_POLICY.md`](HAKEDAKA_KR_ALPHA_POLICY.md)  
4. [`RUN_MODE_POLICY.md`](RUN_MODE_POLICY.md)  
5. [`USER_GUIDE.md`](USER_GUIDE.md)  
6. [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md)  

검증 스크립트(경로가 구 폴더를 가리키면 saa-alpha로 바꿔 실행):

```powershell
cd C:\Cursor\investment-saa-alpha
pytest tests/test_hakedaka_acceptance.py -q
```

---

## 9. 구 채팅 삭제 여부

- **코드·이 문서가 saa-alpha에 있으면** 구 `C:\Cursor` / multi_asset / 단발 조사 채팅은 삭제해도 됨.  
- 삭제 시 잃는 것: 대화 원문만. 결정은 이 핸드오프 + `docs/*_RESULT.md`로 승계됨.
- **남길 채팅:** 제목 `SAA 알파 투자` 하나. (위 §0b)
