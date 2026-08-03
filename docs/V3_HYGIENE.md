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
| `LAUNCHERS.md` | bat/vbs 일상 진입 · 죽은 런처 격리 위치 |
| `REAL_INVEST_SCOPE_CHECKLIST.md` | 실투 범위 (채택) |
| `V3_WINDOWS_PACKAGING.md` | Setup·포터블·업데이트 |
| `V3_CARRY_KIT.md` | USB 앱+장부 2덩어리 |
| `FACTOR_WEIGHT_LITERATURE_AND_B_SPEC.md` | 팩터 가중 문헌 · SR 흡수 B안 |
| `VALUE_PER_PBR_PROFILE_SPEC.md` | Value 프로필 PER/PBR · 문헌=방향 · 비율=휴리스틱 |
| `MOMENTUM_HOLDING_MONITOR_SPEC.md` | 모멘텀 보유 상방/하방 측정 초안 |
| `ALPHA_BOOK_OPS_SPEC.md` | 알파북 9:1 · 밴드 · 신호 우선 (Review-only) |
| `BASEL3_SECTOR_TIMELINE_SUBRULE.md` | 바젤·건전성 테마 시계열 |
| `USER_GUIDE.md` | 운영자 사용설명 |
| `OPS_ASSISTANT_WINDOWS_PORTABLE.md` | 이식·백업 |
| `SCALE_IN_OPS_RULE.md` / `EXIT_STEP_OPS_RULE.md` | 승인된 운영 규칙 |
| `MOMENTUM_REVIEW_ONLY_SPEC.md` | 모멘텀 Review-only |
| `WEEKLY_QUAL_CDE_PROMPT.md` / `WEEKLY_QUAL_REPORT_SPEC.md` | 주간 정성 |
| `EXIT_TARGET_ANCHOR_POLICY.md` | 익절 YAML 실측 앵커 · CECS 원장 경계 |
| `QUAL_PUBLIC_OVERLAY_SPEC.md` | 공적 정성 화이트리스트 · 증권사 SoT 금지 |
| `REAL_INVEST_SCOPE_CHECKLIST.md` | 실투 남김/접음 · 주간 최소 루틴 |
| `CONSENSUS_DATA_FEASIBILITY.md` | 컨센서스 한계 (코드 안내) |
| `ALPHA_SYSTEM_FIVE_FACTOR_REWEIGHT.md` | 팩터 가중 SoT |
| `RUN_MODE_POLICY.md` / `P0_OPERATOR_CHECKLIST.md` / `OPERATIONS_REFRESH_GUIDE.md` | 운영 정책 |
| `ACCEPTANCE_CRITERIA.md` / `MVP_SPEC.md` | 승인·동결 스펙 |
| `UI_COPY.md` / `ALPHA_DASHBOARD_UI_GUIDE.md` / `TEST_BACKLOG.md` | UI·테스트 |

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
