# v3 에이전트 시작 (짧은 핸드오프)

> **코드 루트:** `C:\Cursor\investment-saa-alpha-v3` only  
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

---

## UI 지도 (현재)

| 사이드바 표시 | 내부 키 | 하는 일 |
|---------------|---------|---------|
| 오늘 | 홈 | **① 비중(보유+제안) → ② 보유 분석 → ③ 제안 분석** · 월리밸·레짐은 접힘 |
| 확인 | 결재함 | 주간/월간 정성 승인 |
| **포트폴리오** | 포트폴리오 | **내 보유종목 선택**(항상 표시) · 종목별 안내 · 제안 북 |
| 더보기 | 저널·레짐·설정 | 감사·시장·API/백업 |

실보유: 수량 없이 후보 슬라이더로 등록 가능 (`positions.csv` kr_alpha, gitignore).

---

## 최근 고정 (2026-07-28~29)

- v3 활성 · 홈 월 리밸 보드 · 모멘텀 Review-only
- 종목별 교체 안내 · 전체 나침반 UI 제거
- 사이드바「보유」→「포트폴리오」· 보유 선택 창 상시 표시
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
