# investment-alpha-screener — Agent 안내

## 버전

- **이 저장소 = v3 활성 개발·운영.** 표시 이름: **알파 스크리너** (코스피·코스닥 장부 분리)
- 코드 루트: `C:\Cursor\investment\investment-alpha-screener`
- 형제 프로그램(합치지 않음): `C:\Cursor\investment\investment-fund-screener` (수급 브리핑)
- v2: `C:\Cursor\investment-saa-alpha-v2` (보관)
- v1: `C:\Cursor\investment-saa-alpha` (유지·동결)

## 단일 채팅방

- **공식 채팅 제목:** `SAA 알파 투자` (제품 표시명과 별개 — 바꾸지 않음)
- 작업은 그 채팅 하나에서 이어간다.
- 새 채팅 시: [`docs/V3_CHARTER.md`](docs/V3_CHARTER.md) + [`docs/V3_AGENT_START.md`](docs/V3_AGENT_START.md)
- 문서 고스트 방지: [`docs/V3_HYGIENE.md`](docs/V3_HYGIENE.md) — `docs/archive/` 는 명시 요청 시에만

## 불변 요약

- `proposal_mode: pure_qvm`
- `target_portfolio.csv` 자동 변경 금지
- ETF Executable / kr_alpha·하케다카·수급 Review-only
- FASTJUSIK 금지 — KRX/PyKRX·DART 직접
- Core에서 `score_m` 제외
- 코스피·코스닥 장부 분리 (한 번에 한 시장만 정량 · `market=ALL` 금지)
