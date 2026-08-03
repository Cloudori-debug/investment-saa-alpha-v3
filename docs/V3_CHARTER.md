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
- Ops A: `total_score` = 정량 100% · CECS 가중 0 (CECS=선택 원장 · 환원 순위는 `score_sr` SR4)
- 정성 = **선택 공적 브레이크** ([`QUAL_PUBLIC_OVERLAY_SPEC.md`](QUAL_PUBLIC_OVERLAY_SPEC.md)) · 주간 T2/논지/E **필수 게이트 아님**
- 익절 YAML = 승인 누적 장부 · **실측 앵커만 신규 채택** · 증권사 목표가 SoT 금지 ([`EXIT_TARGET_ANCHOR_POLICY.md`](EXIT_TARGET_ANCHOR_POLICY.md))

---

## v3에서 올리는 것

1. **홈 ①비중 → ②보유 분석 → ③제안 분석** — 월 리밸·바젤은 접힘 (Review-only · 자동주문·target 기입 없음)
2. 정량 freeze **기본 off** (`proposal_freeze_policy.json`)
3. `positions.csv` git 비추적 · 고스트 보유 방지
4. **모멘텀 Review-only 집행 판정** — [`MOMENTUM_REVIEW_ONLY_SPEC.md`](MOMENTUM_REVIEW_ONLY_SPEC.md)
5. **Hygiene** — 문서 archive · 짧은 에이전트 핸드오프 · journal 축약 ([`V3_HYGIENE.md`](V3_HYGIENE.md))
5b. **SR4 (B안)** — CECS execution 연속성을 `score_sr`에 흡수 · CECS 순위 가중 0 유지 ([`FACTOR_WEIGHT_LITERATURE_AND_B_SPEC.md`](FACTOR_WEIGHT_LITERATURE_AND_B_SPEC.md))
5c. **익절 실측 앵커 · CECS 원장 고정 (2026-08-03)** — 증권사 목표가 맹신 금지 · 월간 CECS는 execution만·순위 무관
5d. **실투 범위 채택** — [`REAL_INVEST_SCOPE_CHECKLIST.md`](REAL_INVEST_SCOPE_CHECKLIST.md) · CECS 홈/체크리스트 제거 · 결재함 CECS 접힘
5e. **공적 정성 오버레이 (2026-08-04)** — 증권사 SoT 금지 · KCIF·신평·정부 = 선택 브레이크 · 주간 C/D/E 비필수 ([`QUAL_PUBLIC_OVERLAY_SPEC.md`](QUAL_PUBLIC_OVERLAY_SPEC.md))

---

## 명시적 비범위

- 차트/모멘텀으로 proposal 순위 자동 변경
- 월 리밸 보드의 **자동 주문·target 자동 기입**
- CECS를 total_score에 재혼합
- 익절 YAML 일괄 자동 재계산
- 주간 필수 루틴에 CECS·증권사 목표가 포함
- 증권사 목표가·투자의견을 익절 SoT로 신규 채택
---

## 시작

1. 이 파일 + [`V3_AGENT_START.md`](V3_AGENT_START.md)  
   (레거시 장문 핸드오프는 archive — 기본 금지)
2. UI: `Start-Ops-Assistant.vbs` 또는 `run_ui_direct.bat` / `투자나침반.bat`
3. 작업 cwd = **이 폴더만**
