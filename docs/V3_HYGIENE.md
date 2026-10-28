# v3 Hygiene — 실사용 baseline 정리

> **일자:** 2026-07-29  
> **목적:** 개발 부채·문서 고스트·런타임 잡음을 줄여 **실사용 안정판**을 고정한다.  
> **삭제 아님:** 옛 문서는 `docs/archive/20260729_hygiene/` 로 격리.

---

## 원칙

| 구분 | 규칙 |
|------|------|
| **진실 원천** | `docs/V3_CHARTER.md` + `docs/V3_AGENT_START.md` 만 에이전트 필수 |
| **문서** | `docs/` 루트 = 운영·불변·현재 스펙만. 조사/RESULT/주간리포트 = archive |
| **코드** | 이 저장소(`v3`)만 수정. v1/v2 금지 |
| **장부** | `positions.csv` · freeze JSON · journal = 로컬 운영 상태 (git 비추적 또는 축약) |
| **재생성** | `prices_history.csv` · `data/cache/` · `outputs/` = 지워도 파이프라인으로 복구 |

---

## 활성 문서 (`docs/` 루트)

| 파일 | 역할 |
|------|------|
| `V3_CHARTER.md` | 불변·범위 |
| `V3_AGENT_START.md` | 새 채팅/에이전트 시작 (짧은 핸드오프) |
| `V3_HYGIENE.md` | 이 정책 |
| `V3_DEPLOY.md` / `V3_GO_LIVE.md` | 배포·선택 Go-Live |
| `DESK_PORTAL.md` | 수급 브리핑과 **프로세스만** 나란히 (시스템 혼합 금지) |
| `V3_WINDOWS_PACKAGING.md` | Setup·포터블·업데이트 |
| `V3_CARRY_KIT.md` | USB 앱+장부 2덩어리 |
| `FACTOR_WEIGHT_LITERATURE_AND_B_SPEC.md` | 팩터 가중 문헌 · SR 흡수 B안 |
| `MOMENTUM_HOLDING_MONITOR_SPEC.md` | 모멘텀 보유 상방/하방 측정 초안 |
| `USER_GUIDE.md` | 운영자 사용설명 |
| `OPS_ASSISTANT_WINDOWS_PORTABLE.md` | 이식·백업 |
| `SCALE_IN_OPS_RULE.md` / `EXIT_STEP_OPS_RULE.md` | 승인된 운영 규칙 |
| `BUY_SELL_MAP.md` | 매수·매도·오늘 비중 슬라이드 운영 SoT (한 장) |
| `NEXT_BUY_QUEUE_SPEC.md` | 중기 다음 순매수 Review 대기열 (제안 N 유지) |
| `ROTATION_A_TO_B_RULE.md` | A매도→B순매수 금액·한줄 Review 규칙 |
| `KOSPI_VALUATION_BAND_REVIEW_SPEC.md` | 코스피 CAPE/PBR 밴드 Review (국면식 불변) |
| `HOLD_STATE_PCT_RESEARCH.md` | 보유=단계별 % 평가 (포트 비중 맞추기≠매매단계) |
| `TODAY_WEIGHT_SLIDE_MAP.md` | → BUY_SELL_MAP §3 병합 (리다이렉트) |
| `ROTATION_FIND_PROBABILITY_LIT.md` | 순환매「찾을 확률」문헌 · P1/P2/P3 계산 |
| `TRAIL_EXIT_REVIEW_SPEC.md` | L1 고점 트레일 익절 Review (L0 목표가와 병합 · 채택 대기) |
| `MOMENTUM_REVIEW_ONLY_SPEC.md` | 모멘텀 Review-only |
| `SHORT_BOOK_SPEC.md` | 단기(위성) 북 · Core QVM과 분리 |
| `VALUE_HOLD_EXIT_UPGRADE_PLAN.md` | 보유·매도·히스테리시스 Review 업그레이드 계획 (13F는 비범위) |
| `SHADOW_MID_PROFIT_MACHINE.md` | 중기 shadow 수익 증명 · Go-live 게이트(자동주문·target 기입 금지) |
| `HOLD_EXIT_REVIEW_EDITION.md` | 병렬 에디션 실행·범위 (`8502`) |
| `WEEKLY_QUAL_CDE_PROMPT.md` / `WEEKLY_QUAL_REPORT_SPEC.md` | 주간 정성 |
| `CONSENSUS_DATA_FEASIBILITY.md` | 컨센서스 한계 (코드 안내) |
| `ALPHA_SYSTEM_FIVE_FACTOR_REWEIGHT.md` | 팩터 가중 SoT |
| `RUN_MODE_POLICY.md` / `P0_OPERATOR_CHECKLIST.md` / `OPERATIONS_REFRESH_GUIDE.md` | 운영 정책 |
| `V3_LOGIC_POLICY_VERIFY.md` | 작동 로직·정책 검증 체크리스트 (코드/YAML 대조) |
| `V3_STRATEGY_VERIFY_PLAN.md` | 전략 성과 A/B/C/D 검증 계획 (C=현행 v3 동결) |
| `OPENDART_EVIDENCE_LAYER.md` | DART 증거 층(점수 비혼합 · Review) |
| `ACCEPTANCE_CRITERIA.md` / `MVP_SPEC.md` | 승인·동결 스펙 |
| `UI_COPY.md` / `UI_UX_MAP.md` / `V3_UI_UX_VERIFY.md` | UI 카피·지도·교차검증(U1–U16) |
| `ALPHA_DASHBOARD_UI_GUIDE.md` / `TEST_BACKLOG.md` | UI 가이드·테스트 |

그 외 md는 **`docs/archive/20260729_hygiene/`**.

---

## 런타임 정리

```powershell
python scripts/hygiene_prune.py          # journal 축약 + 안내
python scripts/hygiene_prune.py --apply  # 실제 적용
```

| 대상 | 기본 동작 |
|------|-----------|
| `data/alpha_system_journal.jsonl` | 최근 200행 유지, 나머지는 `data/local/journal_archive/` |
| `data/local/backups/*.zip` | 최근 3개만 (gitignore) |
| `data/cache/` | 선택 `--cache` 시 비움 (재수집) |
| `data/prices_history.csv` | 기본 유지 · `--prices-history` 시 삭제(재생성) |
| `outputs/` | gitignore · 필요 시 수동 삭제 |

**건드리지 않음:** `target_portfolio.csv`, `kr_alpha_exit_targets.yaml`, universe/fundamentals, 설정 yaml.

---

## 에이전트 고스트 방지

1. 새 작업: **`V3_CHARTER` + `V3_AGENT_START`만** 읽기 (레거시 핸드오프 전체 금지)
2. archive 문서는 **사용자가 명시할 때만** 참조
3. UI 세션 이상 → Streamlit 완전 종료 후 `투자나침반.bat` 재실행
4. 사이드바 라벨: **포트폴리오** (내부 키는 그대로)

---

## 완료 체크

- [x] docs 루트 축소 · archive 격리
- [x] `V3_AGENT_START`로 핸드오프 교체
- [x] `hygiene_prune.py`
- [x] journal 축약 적용 + git 비추적
- [ ] 운영자: UI 재시작 후 포트폴리오「내 보유종목 선택」확인
- [ ] (선택) `python scripts/hygiene_prune.py --apply --cache` 캐시 비움
