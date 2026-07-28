# 외부 Claude 검수 — 트리아지 (2026-07-18)

> 외부 보고서 Critical 0 / Major 1 / Minor 2를  
> SAA 채팅 축적 규칙 + 3갈래 트리아지 + Cursor 교차 검수(`CLAUDE_REVIEW_REPORT_20260718_CURSOR.md`)와 대조.

| ID | 출처 | 판정 | 이유 |
|----|------|------|------|
| Ext-Major silent default 50 | 외부 | **채택 (Major)** | 코드 확인: `_parse_axis` 빈 점수→50.0. 불변 6조 직접 위반은 아니나 「확인 불가는 사람이」·silent default 금지 철학과 충돌. 종목·축 `provisional` 표식 권고 타당. Critical로 올리지 않은 것도 맞음(③). |
| Ext-Minor lru_cache | 외부 | **보류** | 실무 영향 낮음. P2 절제. |
| Ext-Minor `del init_cap` | 외부 | **보류** (또는 초소형 cleanup에만) | 하드 룰 무관. 스타일/죽은 계산. |
| Ext: allocate 이상 없음 | 외부 | **동의** | ① — 신규 엣지 없음. |
| Ext: action_panels SoT OK | 외부 | **동의** | ② — 라이브 로직 Critical 아님. |
| Ext: deep_tickers 거부 OK | 외부 | **부분 동의 / 보완** | 거절 분기는 있으나, Cursor M1: `allowed` 비면 fail-open + persist가 `targets`로 allowlist 확장. 외부 패킷이 fail-open을 못 봄. **별도 Major로 유지(채택)**. |
| Cursor M1 deep_tickers | Cursor | **채택 (Major)** | 외부 미검출. proposal-only 주장과 직결. |
| Cursor M2 attempt_execute 인자 | Cursor | **채택 (Major, 우선순위↓)** | UI는 이중 차단. 엔진 일원화는 개선. Critical 아님. |
| 보험≠financial | Cursor m1 | **보류** | 정책 선택. |
| getattr or 2 / 30종 / E | 양쪽 | **보류** | P2. |

## 실행 우선순위 (승인 시)

1. **Ext silent-50 + provisional 배지** (승인 UX · 철학)
2. **Cursor M1** deep_tickers fail-closed + proposal-only allowlist
3. **Cursor M2** attempt_execute / UI 게이트 일원화 (여유 시)

## Critical 합계
**0** — 설계–구현 정합은 탄탄. Major는 “표시·게이트 약화” 층.
