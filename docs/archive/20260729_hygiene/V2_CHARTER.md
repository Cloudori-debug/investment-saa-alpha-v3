# SAA 알파 v2 — 차터

> **코드 루트:** `C:\Cursor\investment-saa-alpha-v2`  
> **베이스:** v1 `investment-saa-alpha` @ `5157cec` (`stable-20260718-final-selection` 계열 + 목표가 E-only)  
> **작성일:** 2026-07-19  
> **채팅:** 공식 제목은 계속 `SAA 알파 투자` — v2 작업은 이 폴더에서만.

---

## 왜 폴더를 나눴나

| | v1 (`investment-saa-alpha`) | v2 (이 저장소) |
|--|------------------------------|----------------|
| 역할 | **만족·유지** — 운영·실전 기준판 | **등급업 개발** — 보완 레이어 |
| 변경 | 버그·운영만 (의도적 기능 동결 권장) | 신규 기능·실험 |
| 선정 철학 | 그대로 | **계승** (깨지 않음) |

v1을 덮어쓰지 않고, v2에서만 다음 단계를 올린다.

---

## v1에서 그대로 가져오는 것 (불변)

- `proposal_mode: pure_qvm` — 하케다카·수급으로 제안 순위 자동 변경 금지
- `target_portfolio.csv` — 사람 승인만
- Executable = ETF·현금·채권 / kr_alpha·하케다카·수급 = Review-only
- FASTJUSIK 스크래핑 금지 — PyKRX/DART만
- 스코어 축 = Q/V/SR/R + CECS 입력 가능, **`score_m` 제외**
- **Ops A (2026-07-25):** `total_score` = 정량(factor) **100%** · CECS 가중 **0** — CECS는 순위 미반영·선택 검토
- 정성 필수 게이트 = T2 · 논지 · 목표가(E) (편입·판단)
- 차트·수급으로 proposal 순위 변경 **금지**
- CECS 점수 **자동 조정 금지**

---

## v2에서 새로 올리는 것 (우선순위)

### P0 — 운영 완성

1. dry-run / Actual Buy — [`SCALE_IN_OPS_RULE.md`](SCALE_IN_OPS_RULE.md) (**승인 2026-07-19**) + dry 리포트 SCALE_IN 섹션·집행 1회차 캡 (**코드 반영**) · 운영 판단은 [`P0_OPERATOR_CHECKLIST.md`](P0_OPERATOR_CHECKLIST.md)
2. CAUTION · 경제 나침반 — **운영자 체크리스트** (Turbulence 26/60 WAIT · 임계값 미변경)
3. 주간 정성(B/E) · 목표가 — 파이프라인 기구현 + **F_QUANT_EVENTS** 수동 섹션 추가
4. **판매형 1차 IA** — 사이드바 메인 메뉴 · 홈=할 일→판정→제안 · 결재함 필수/선택 분리 (**2026-07-25**)
5. **제안 스냅샷 고정** — 주간 요청서 생성 시 pin · 정량 재실행 차단 · 필수 게이트 승인 시 해제 (**2026-07-25**)

### P1 — 정량 이벤트 감시 레이어

- 선행 조사: [`CONSENSUS_DATA_FEASIBILITY.md`](CONSENSUS_DATA_FEASIBILITY.md) — PyKRX/DART **불가** → 수동 F
- 공시형 `rescore_triggers` → `RESCORE_TRIGGER_FIRED` + 홈 액션 큐 `panel_kind=rescore` (**점수 자동변경 없음**)
- 컨센서스 3종: 수동 신호만 · 임계 TODO

### 명시적 비범위 (하지 말 것)

- 차트/기술 신호로 편입·제외
- 수급으로 `pure_qvm` 순위 변경
- 컨센서스 이벤트로 CECS·total_score 자동 변경
- CECS를 다시 total_score에 섞어 순위 변경 (Ops A 철회 시 별도 승인)
- Turbulence 게이트 우회 / 익절 2차 미승인 착수

---

## 문헌 인덱스

짧은 서지: 대화에서 정리한 목록 → `docs/V2_LITERATURE.md`

---

## 브랜치·원격

- 로컬 브랜치: `v2/main`
- `v1-upstream` → `C:\Cursor\investment-saa-alpha` (읽기용·필요 시 cherry-pick)
- GitHub 신규 remote는 사용자가 만들 때 추가 (v1 `origin`에 실수로 push하지 말 것)
