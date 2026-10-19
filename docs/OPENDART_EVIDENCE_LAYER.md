# OpenDART 증거 층 (Review-only)

> **상태:** 스펙 완결 · 2026-10-18 · 채팅 `SAA 알파 투자`  
> **불변:** `pure_qvm` · CECS 순위 가중 0 · `target_portfolio` 사람만 · 증거 ≠ 점수  
> **한도:** 일일 API 상한(키별·보통 수천~2만) — **중간 자동 리로드 금지**

## 목적

자동화는 **AI 점수**가 아니라 **공시에서 확인 가능한 증거**를 추출·규칙 분류하고, 사람이 확인할 칸을 드러낸다.

| 출력 | 의미 | 점수 혼합 |
|------|------|-----------|
| 투자매력 | 기존 Q/V/SR/R | SoT |
| 가치실현 증거 | 배당·자사주·자산양도 상태·rcpNo·금액 | **금지** |
| 데이터 상태 | 키없음 / 실패 / 없음·미탐지 / 수집됨 | fail-open 보존 |

## DART 한도 보호 (필수)

| 규칙 | 동작 |
|------|------|
| 자동 재호출 | **없음** — 페이지 진입 시 네트워크 금지 |
| 기본 표시 | 기존 `opendart_proposal_watch.json` + 디스크 캐시 |
| 증분 갱신 | 만료·신규 종목만 호출 |
| 전체 재탐색 | 버튼 명시 · 위험 · soft limit에서 중단 |
| 일일 soft limit | `data/local/dart_api_quota.json` 기본 **8000** |
| 원문 document.xml | 배당·금액 폴백 · 증분 시에만 · **최대 12건/회** · rcept 영구 캐시 |

캐시 위치: `data/local/dart_evidence_cache/` (tickers · amounts_by_rcept · documents).

## 수집 inventory

| 원천 | 파일·모듈 | 쓰는 곳 |
|------|-----------|---------|
| 재무·스냅샷 | quant snapshot | Q/V/SR/R |
| `list.json` | payout events · SR4 | 증거 층 |
| `majorstock.json` | watch flags | 경영참여·연기금 게이트 |
| `hyslrSttus.json` | owner % | 하케다카 |
| `tsstkAqDecsn.json` | 자사주 예정금액 | 금액 보강(캐시 미스만) |
| `tgastTrfDecsn.json` | 유형자산 양도금액 | 금액 · **환원 가정 금지** |
| `document.xml` | 배당결정·금액 폴백 원문 | 배당금총액·1주당 (쿼터 캡) |
| overlay | `qual_rank_overlay.json` | 제안 제외 |

배당 결정공시는 OpenDART에 자사주형 JSON이 없어 **document.xml**에서 배당금총액·1주당을 파싱한다(전 종목 `alotMatter` 금지·연간 DPS≠해당 결의).

## 상태·체인

`dart_evidence.py` — 검토/결의/진행/완료/철회 · 정정 체인 · 헤드라인 `결의→철회`.

## 증거 게이트 A/B

`data/evidence_gate_policy.json` — 기본 `enabled: false`.  
ON 시 자사주 체인 **최종 철회**만 overlay 제외 · fail-open.

## Shadow A/B (오프라인)

`alpha_system/shadow/evidence_ab.py` — 제안 집합 A vs 철회제외 B · **DART 0회** · 초과수익 증명 아님.

## UI 버튼

| 버튼 | mode |
|------|------|
| 증분 갱신 | `incremental` (+ document ≤12) |
| 전체 재탐색(위험) | `force` |
| 캐시만 다시 그리기 | `cache_only` |

## 스크린 심층 검증 (PH-CVS식 · 관찰·제안 풀)

`alpha_system/review/screen_deep_verify.py` · `data/.../screen_deep_verify.json`

| 자동 (캐시·대리) | 한계(노트) |
|------------------|-----------|
| 하케다카 hit | 측정 부족만 U |
| OpenDART 공시 · 없음=탐색완료 PASS | watch 미수집만 U |
| 자사주 철회 체인 | — |
| 경영참여·지배 (metrics/flags) | — |
| 자본사용후잔여 (FCF 또는 OCF−CAPEX) | 지분·대여 미차감 |
| 현금 귀속 (지주명·할인프록시) | 모자 분리 재무 아님 |
| 담보·제한 (단기금융자산/현금) | 담보 주석 원문 아님 |
| NAV 이중계산 (지주·할인프록시) | 완전 NAV 아님 |

PDF 7종 리포트 추적과 **대상이 다름** — 심층은 **스크리너 관찰·제안 종목**.  
DART 0회 · 점수·target 불변 · UI「심층 다시 그리기」 · 결측은 U(0 추정 금지).

### Review 판정 (투자 반영 · 자동매매 아님)

| 판정 | 조건 | 사람 행동 |
|------|------|-----------|
| 통과 | 제안 + 심층 FAIL/U 없음 | target·주문 검토 |
| 보류 | 제안 + 연질 FAIL 또는 U | 보강·재확인 후 결정 |
| 제외검토 | 제안 + 철회·지배 FAIL | 편입 전 제외 검토 |
| 대기/관찰 | 장부 상태 | 비중 없음 |

순위 재가중·`target` 자동기입 **금지**.

## 금지

- 증거를 `total_score` / CECS에 가산  
- 증거로 `target` 기입·주문  
- 추출 실패 → 하케다카 hit=0  
- 전 유니버스 원문 크롤 · 세션마다 자동 재탐색  
- 사람 U를 0·평균으로 채움  

## 모듈

| 파일 | 역할 |
|------|------|
| `dart_evidence.py` | 규칙·체인·게이트 후보 |
| `dart_evidence_cache.py` | 디스크 캐시 |
| `dart_quota.py` | 일일 soft limit |
| `cecs_opendart_pack.py` | 수집·refresh(mode) |
| `shadow/evidence_ab.py` | 오프라인 A/B |
