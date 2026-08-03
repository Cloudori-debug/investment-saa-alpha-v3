# investment-saa-alpha-v3 — Agent 안내

## 버전

- **이 저장소 = v3 활성 개발·운영** (`C:\Cursor\investment-saa-alpha-v3` only).
- v1·v2 폴더는 **삭제됨** — 경로·바로가기가 v1/v2를 가리키면 안 됨.
- 문서에 남은 v1/v2 언급은 이력·archive용이며 코드 루트가 아님.

## 단일 채팅방

- **공식 채팅 제목:** `SAA 알파 투자`
- 작업은 그 채팅 하나에서 이어간다.
- 새 채팅 시: [`docs/V3_CHARTER.md`](docs/V3_CHARTER.md) + [`docs/V3_AGENT_START.md`](docs/V3_AGENT_START.md)
- 문서 고스트 방지: [`docs/V3_HYGIENE.md`](docs/V3_HYGIENE.md) — `docs/archive/` 는 명시 요청 시에만

## 불변 요약

- `proposal_mode: pure_qvm`
- `target_portfolio.csv` 자동 변경 금지
- ETF Executable / kr_alpha·하케다카·수급 Review-only
- FASTJUSIK 금지 — KRX/PyKRX·DART 직접
- Core에서 `score_m` 제외
- Ops A: CECS 순위 가중 0 (선택 원장) · 환원 순위는 `score_sr` SR4
- 익절 YAML = 실측 앵커만 신규 · 증권사 SoT 금지 ([`docs/EXIT_TARGET_ANCHOR_POLICY.md`](docs/EXIT_TARGET_ANCHOR_POLICY.md))
- 정성 = 선택 공적 브레이크 · 주간 비필수 ([`docs/QUAL_PUBLIC_OVERLAY_SPEC.md`](docs/QUAL_PUBLIC_OVERLAY_SPEC.md))
