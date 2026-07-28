# SAA 알파 v3 — 차터

> **코드 루트:** `C:\Cursor\investment-saa-alpha-v3`  
> **베이스:** v2 `investment-saa-alpha-v2` (2026-07-28 스냅샷 + 월 리밸 홈 보드)  
> **작성일:** 2026-07-28 · **Hygiene:** 2026-07-29  
> **채팅:** 공식 제목 `SAA 알파 투자` — **이후 기능 작업은 v3에서만.**

---

## 버전 역할

| | v1 | v2 | **v3 (이 폴더)** |
|--|----|----|------------------|
| 경로 | `investment-saa-alpha` | `investment-saa-alpha-v2` | **`investment-saa-alpha-v3`** |
| 역할 | 유지·동결 | 보관·참조 | **활성 개발·운영** |

v1/v2에 신규 기능을 넣지 말 것.

---

## 불변 (v1→v2→v3 계승)

- `proposal_mode: pure_qvm`
- `target_portfolio.csv` — 사람 승인만
- Executable = ETF·현금·채권 / kr_alpha·하케다카·수급 = Review-only
- FASTJUSIK 금지 — PyKRX/DART만
- Core 순위에서 **`score_m` 제외**
- Ops A: `total_score` = 정량 100% · CECS 가중 0
- 정성 필수 = T2 · 논지 · 목표가(E)

---

## v3에서 올리는 것

1. **홈「월 리밸 · 오늘 할 일」** — 밴드 / 익절·게이트 / CRISIS 예외 / SCALE_IN 제외 (Review-only)
2. 정량 freeze **기본 off** (`proposal_freeze_policy.json`)
3. `positions.csv` git 비추적 · 고스트 보유 방지
4. **모멘텀 Review-only 집행 판정** — [`MOMENTUM_REVIEW_ONLY_SPEC.md`](MOMENTUM_REVIEW_ONLY_SPEC.md)
5. **Hygiene** — 문서 archive · 짧은 에이전트 핸드오프 · journal 축약 ([`V3_HYGIENE.md`](V3_HYGIENE.md))

---

## 명시적 비범위

- 차트/모멘텀으로 proposal 순위 자동 변경
- 월 리밸 보드의 **자동 주문·target 자동 기입**
- CECS를 total_score에 재혼합

---

## 시작

1. 이 파일 + [`V3_AGENT_START.md`](V3_AGENT_START.md)  
   (레거시 장문 핸드오프는 archive — 기본 금지)
2. UI: `Start-Ops-Assistant.vbs` 또는 `run_ui_direct.bat` / `투자나침반.bat`
3. 작업 cwd = **이 폴더만**
