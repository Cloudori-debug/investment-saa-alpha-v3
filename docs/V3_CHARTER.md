# SAA 알파 v3 — 차터

> **표시 이름:** 알파 스크리너 (코스피·코스닥 **장부 분리**)  
> **코드 루트:** `C:\Cursor\investment\investment-alpha-screener`  
> **형제(합치지 않음):** `C:\Cursor\investment\investment-fund-screener`  
> **베이스:** v2 `investment-saa-alpha-v2` (2026-07-28 스냅샷 + 월 리밸 홈 보드)  
> **작성일:** 2026-07-28 · **Hygiene:** 2026-07-29  
> **채팅:** 공식 제목 `SAA 알파 투자` — **이후 기능 작업은 v3에서만.**

---

## 버전 역할

| | v1 | v2 | **v3 (이 폴더)** |
|--|----|----|------------------|
| 경로 | `investment-saa-alpha` | `investment-saa-alpha-v2` | **`investment\investment-alpha-screener`** |
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
- 정성 필수 = **종목 게이트(컷 확정 시 OpenDART 자동) · 목표가(정당 60%+섹터 40% 자동 · 순환주는 중기 ROE · 현재가≥혼합 목표가면 제안에서 제외)**. 제도·논지는 **공식 RSS 후보**(기입·승인 칸 없음 · 주간 채점·클로드 요청서 아님). 30종 CECS 0–100 채점 없음
- 신평·공공 정성 = **게이트**(OpenDART 경영참여·연기금 → 제안에서 자동 제외). 사람 기입·자리 교체 UI 없음. 점수 가중합 아님
- 자본 T1~T4 봉투 폐기 — 종목 가격 사다리(매수2/익절3)가 대체

---

## v3에서 올리는 것

1. 운영 IA는 **확인 → 포트폴리오**. 월 리밸은 포트폴리오에서 Review-only (자동 주문·target 자동기입 없음). 국면·레짐 나침반은 운영 경로에서 제외
2. 정량 freeze **기본 off** (`proposal_freeze_policy.json`)
3. `positions.csv` git 비추적 · 고스트 보유 방지
4. **모멘텀 Review-only 집행 판정** — [`MOMENTUM_REVIEW_ONLY_SPEC.md`](MOMENTUM_REVIEW_ONLY_SPEC.md)
5. **Hygiene** — 문서 archive · 짧은 에이전트 핸드오프 · journal 축약 ([`V3_HYGIENE.md`](V3_HYGIENE.md))
5b. **SR4 (B안)** — CECS execution 연속성을 `score_sr`에 흡수 · CECS 순위 가중 0 유지 ([`FACTOR_WEIGHT_LITERATURE_AND_B_SPEC.md`](FACTOR_WEIGHT_LITERATURE_AND_B_SPEC.md))
6. **코스피·코스닥 장부 분리** — 본문 위 `코스피 | 코스닥` 탭. 코스피=`data/` · 코스닥=`data/books/kosdaq/`. 정량은 시장당 한 버튼, 한 번도 섞지 않음. 코스닥은 관찰 10 · 제안 3 · 업종 1

---

## 명시적 비범위

- 차트/모멘텀으로 proposal 순위 자동 변경
- 월 리밸 보드의 **자동 주문·target 자동 기입**
- CECS를 total_score에 재혼합 (정량 70/정성 30 포함)
- 국면·레짐 나침반으로 알파 비중·순위를 바꾸기 (현금 햇지는 알파북 단기채 10% 고정)

---

## 시작

1. 이 파일 + [`V3_AGENT_START.md`](V3_AGENT_START.md)  
   (레거시 장문 핸드오프는 archive — 기본 금지)
2. UI: `Start-Ops-Assistant.vbs` 또는 `run_ui_direct.bat` / `투자나침반.bat`
3. 작업 cwd = **이 폴더만**
