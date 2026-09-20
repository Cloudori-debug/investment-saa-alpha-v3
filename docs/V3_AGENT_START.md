# v3 에이전트 시작 (짧은 핸드오프)

> **코드 루트:** `C:\Cursor\investment\investment-alpha-screener` only  
> **표시 이름:** 알파 스크리너 (본문 위 코스피 | 코스닥 탭 · 장부·정량 분리)  
> **채팅 제목:** `SAA 알파 투자`  
> **필수 선행:** [`V3_CHARTER.md`](V3_CHARTER.md) · 정리 정책: [`V3_HYGIENE.md`](V3_HYGIENE.md)  
> **레거시 장문 핸드오프:** [`archive/20260729_hygiene/CHAT_HANDOFF_LEGACY_MULTI_ASSET.md`](archive/20260729_hygiene/CHAT_HANDOFF_LEGACY_MULTI_ASSET.md) (명시 요청 시에만)

---

## 불변 (위반 금지)

- `proposal_mode: pure_qvm`
- `target_portfolio.csv` — **사람만** (자동 기입·자동 주문 없음)
- ETF·현금 = Executable / **kr_alpha·하케다카·수급 = Review-only**
- FASTJUSIK 금지 — PyKRX·DART
- Core에서 `score_m` 제외 · Ops A `total_score` = 정량 100% (CECS 순위 미반영)
- 신평·공공 = OpenDART 게이트 자동 (점수 혼합 아님) · `data/qual_rank_overlay.json`
- 자본 T1~T4 봉투 폐기 — 스케일인은 포트폴리오 가격 사다리. 종목 게이트는 컷 확정 시 OpenDART 자동. 목표가는 정당 60%+섹터 40% 자동(**순환주는 중기 ROE**). **현재가≥혼합 목표가면 제안에서 제외**(다음 적격 채움 · 보유는 환금). 제도·논지는 공식 RSS 후보(기입 칸 없음). 30종 CECS 채점 없음

---

## UI 지도 (현재)

| 사이드바 표시 | 내부 키 | 하는 일 |
|---------------|---------|---------|
| 확인 | 결재함 | 본문 위 **코스피 \| 코스닥** · ① 숫자(해당 시장만 정량) · ② 공식 RSS · ③ 가동 |
| **포트폴리오** | 포트폴리오 | 같은 시장 탭 · 코스피 관찰 30/제안 6 · 코스닥 관찰 10/제안 3 |
| 경제 시그널 | 경제시그널 | 더보기 · 개별주/단기채 5단계 제안만 (순위·target 미변경) |

장부: 코스피=`data/` · 코스닥=`data/books/kosdaq/` (섞지 않음).

실보유: 후보 30 표 맨 앞칸 체크로 등록 (`positions.csv` kr_alpha, gitignore).

---

## 최근 고정 (2026-07-28~29)

- v3 활성 · 확인→포트폴리오 IA · 모멘텀 Review-only
- 종목별 교체 안내 · 전체 나침반 UI 제거
- 사이드바「보유」→「포트폴리오」· 후보 30 표 체크가 실보유
- `positions.csv` git 비추적 (고스트 보유 방지)
- 정량 freeze 기본 off
- Hygiene: 문서 archive · journal 축약 스크립트
- Windows 패키징: 포터블 `.venv` · `업데이트.bat`(data 보존) · Inno Setup (`V3_WINDOWS_PACKAGING`)
- **SR4(B안):** 환원 연속성 → `score_sr` · CECS 순위 가중 0 (`FACTOR_WEIGHT_LITERATURE_AND_B_SPEC`)
- **모멘텀 보유 모니터(MHM):** 상방/하방·EXIT_REVIEW 연속일 (`MOMENTUM_HOLDING_MONITOR_SPEC`)

---

## 열림 (운영자 / 후순위)

1. dry-run · Actual Buy — 운영자 판단 (`P0_OPERATOR_CHECKLIST`)
2. 익절 **자동 집행 2차** — **미승인** (표시만)
3. Alpha BT 장기 재무 히스토리 — 후순위

---

## 시작 체크

1. cwd = 이 폴더  
2. `투자나침반.bat` 또는 `streamlit run alpha_dashboard.py`  
3. 문서 추가는 `docs/archive/` 또는 사용자 명시 SPEC만  
4. 커밋은 사용자 요청 시에만
