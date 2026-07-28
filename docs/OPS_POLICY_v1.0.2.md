# v1.0.2 운영 방침 (90일)

> **역할:** 매매 승인 관제탑 + 노출 레이더. 12칸 SAA·자동매매 확장은 90일 밖.  
> **성공 기준:** 기능 수가 아니라 **데이터 신선도 · RED 원인 분류 · dry-run 누적 · 수동 개입 빈도**.

---

## Core / Satellite / Shadow — 권한 경계 (필독)

v1.0.2의 최대 리스크는 **코드 부족이 아니라 권한 혼선**이다.  
아래 원칙은 **90일 shadow 기간 동안 변경하지 않는다** (`target_portfolio.csv`, `saa_profiles.yaml` 동결).

### 역할 정의

| 레이어 | 정의 | authority | 산출물 예 |
|--------|------|-----------|-----------|
| **Core** | 사용자 **장기 ETF-only SAA** (기존 13종). 시스템 **밖** 또는 **별도 계좌**의 기준 포트 | **none** (사용자) | 실제 보유 ETF, 장기 리밸런싱 규칙 |
| **Satellite** | 현재 **v1.0.2 운용 엔진** — 게이트·trade_actions·execution_scope가 관할 | **`v1.0.2`** | `target_portfolio.csv`, `trade_actions.csv`, `final_execution_decision.json` |
| **Shadow** | 진단·비교·관측 전용. **실행 권한 없음** | **none** | `shadow_diagnostic.json`, `alpha_v0_2_shadow.json`, `duration` 진단, `core_saa_reference.yaml` |

### Satellite (v1.0.2 execution authority)

- **공식 target:** `data/target_portfolio.csv` + 나침반 TAA → `generated_target_portfolio.csv`
- **공식 SAA:** `data/saa_profiles.yaml` — 프로필 `defensive_balanced` (7자산군)
- **실제 매수·매도:** `trade_actions.csv`의 **executable** action 및 `final_execution_decision.json`의 `allowed_actions` **만** 따른다
- **자동매매 없음** — 사람 승인 전제

### Core reference (기존 13 ETF SAA)

- `data/core_saa_reference.yaml` — **status: shadow_reference_only**, **authority: none**
- 사용자 장기 ETF-only SAA의 **참조 목록**이며, **공식 target이 아님**
- `target_portfolio.csv` · `saa_profiles.yaml` · `trade_actions` · `execution_scope` · `allowed_actions`에 **영향을 주지 않음**
- look-through **진단·비교**용 (`outputs/core_saa_reference_diagnostic.json`)
- **즉시 편입 금지** — 90일 shadow 누적 후 v1.1b에서 검토

### Shadow 산출물 (참고만)

| 산출물 | 용도 | 실행 연동 |
|--------|------|-----------|
| `shadow_diagnostic.json` | blocked_by, signal vs execution | 없음 |
| `alpha_v0_2_shadow.json` | v0.2 분류·예산 (shadow) | 없음 |
| duration sleeve 진단 | cash / kr_duration / global_duration 분해 | 없음 |
| `core_saa_reference_diagnostic.json` | Core ETF vs Satellite 보유 **비교** | 없음 |

### kr_alpha 비중 — 두 기준 (혼동 금지)

| 기준 | 필드 | 분모 | 사용처 |
|------|------|------|--------|
| **v1.0.2 (hard stop)** | `kr_alpha_v1_portfolio_pct` | **total portfolio NAV** | execution_scope, hard stop 35%, Trim |
| **alpha v0.2 shadow** | `current_alpha_weight_pct` | **investable assets ex-cash** | shadow 리스크 진단만 |

리포트·`daily_brief.json`에는 **두 값을 반드시 병기**한다. hard stop 판단은 **항상 total NAV** 기준.

### GREEN의 의미

**GREEN = 매수 명령이 아니다.** 게이트 차단이 해소된 **기술·운용 상태**를 뜻한다.

| GREEN 후보 조건 | 기준 |
|-----------------|------|
| dry-run | **10/10** |
| data_gate | **GREEN** |
| health fail | **0** 유지 |
| Tier2 stale | pmi_us 등 **해소** |
| USD/KRW | 외부 spot과 **재확인** |
| kr_alpha (NAV) | **≤35%** 또는 hard stop 해소 |
| trade vs theoretical | executable / theoretical **분리 유지** |

GREEN이어도 **신규매수는 `allowed_actions`·executable trade_actions만** 따른다.

### Trigger / Theoretical / Executable 분리

| 개념 | 의미 | 실행 |
|------|------|------|
| **Trigger active** | 매수 **후보 조건** 충족 (관찰) | ❌ |
| **Theoretical** | 게이트 없을 때의 **이론적** Replace/Trim/Buy | ❌ (Review-only) |
| **Executable** | data_gate · dry-run · scope · hard stop **통과** | ✅ (사람 승인 후) |

**Trigger active ≠ Executable Buy.**

### 90일 shadow 전 변경 금지

| 작업 | 판단 |
|------|------|
| 기존 13 ETF를 `target_portfolio.csv`에 **즉시 추가** | **금지** |
| `saa_profiles.yaml`을 13 ETF·8칸으로 **즉시 변경** | **금지** |
| kr_alpha 33% 유지 + Core ETF **단순 합산** | **금지** |
| B급 알파로 포트 **강제 채우기** | **금지** |
| GREEN 전 ETF/TAA **대량 매수 허용** | **금지** |

**Phase 로드맵:**

| Phase | 상태 | 범위 |
|-------|------|------|
| 1 OPS_POLICY | **완료** | Core/Satellite/Shadow 경계 |
| 2b Core SAA v0.2 weights | **완료·통과** | reference-only, gap shadow, 실행 미연결 |
| **2c Duration tag audit** | **대기 (v1.1b 전)** | `duration_sleeve_tags.yaml` — e.g. `308620` US treasury exposure vs `kr_duration_bond` 태깅. **shadow diagnostic만**, target/trade/scope 변경 금지 |
| **3a SAA-relative Alpha Dashboard** | **진행 중** | `alpha_performance_dashboard.*` — Core SAA vs Actual vs gate cost. **shadow only**, 매수/execution 변경 없음 |
| **3b Benchmark & NAV data quality** | **진행 중** | `prices_history+prices.csv` Core MTD, `portfolio_nav_log.csv`, gate forward enrich |
| **4a Hakedaka Re-rating Screener** | **진행 중** | 독립 shadow 트랙 — QVM 미변경, preliminary/verified hunt |
| **4b Hakedaka Data Quality** | **진행 중** | Tier H 갱신, DART 재스캔, hakedaka_fundamentals, quality gate |
| 3 90일 shadow 로그 | **진행 중** | `ops_shadow_log.csv`, Core gap, alpha excess 누적 |
| v1.1b | D+90 후 | 8칸·duration 공식 편입 검토 |

**Phase 2b 핵심 검증 (통과):** Core gap -73.81%p여도 **trade action 미전환** — 설계 의도대로.

**Phase 3a 성공 기준 (90일):** **Core SAA 대비 초과수익** — `alpha_performance_dashboard.csv` 누적. 안전 정지만으로는 성공 아님.

**미국달러단기채:** `ticker: null`, `unresolved` 유지 — 임의 매핑·실행 연결 금지.

---

## 0~2주 — 데이터 정상화

| 체크 | 기준 |
|------|------|
| `core_price_gate` | **pass** (실패 시 stale 종목·영업일 수 기록) |
| Tier A 시세 | 전체 분석 또는 `daily_pipeline`으로 갱신 |
| 매매 | **RED / NO_TRADE → 0건** |
| dry-run | 누적 일수 기록 |

**통과:** stale 없이 `core_price_gate` pass가 연속으로 나올 것.

---

## 3~6주 — 원인 분류 루틴

RED/YELLOW마다 **원인 1개**만 분류:

| 코드 | 의미 |
|------|------|
| `DATA_STALE` | 시세·재무 freshness (core/alpha price gate) |
| `POLICY_CAP` | FSR·수동 레짐·YELLOW_STABLE 상한 |
| `MARKET_RISK` | VIX·드로다운·트리거·hard stop |
| `DRY_RUN` | dry-run 미충족 |
| `OTHER` | 위에 해당 없음 — 메모 필수 |

**통과:** 같은 RED가 나와도 **원인 분류가 매번 동일**하게 재현됨.

---

## 7~12주 — 조건부 업그레이드만

| 반복 문제 | 업그레이드 |
|-----------|------------|
| PyKRX stale 주 2회+ | **B** 데이터 fallback |
| 편중 진단 부족 | **C** look-through 태그 |
| 알파 후보 과다·기준 흔들림 | **D** selector (실행 분리) |
| 12칸 SAA·자동매매 | **E 보류** (90일 내) |

**지금 허용:** v1.1a **shadow mode** · **alpha_v0.2 shadow** (실거래·trade_actions 변경 없음).  
**상세:** `docs/MVP_v1.1a_SHADOW_MODE.md` · `docs/ALPHA_v0.2_CONCEPT.md`

---

## dry-run 2단계

| 단계 | 영업일 | 의미 |
|------|--------|------|
| **최소** | 10일 | 파이프라인·게이트 정상성 |
| **신뢰** | 20~30일 | 레짐 변화 속 **판정 일관성** |

- **10일 후:** ETF_ONLY **소액 1종** 검토 가능 (정책·게이트 허용 시).
- **kr_alpha 신규·교체 실전:** dry-run 20~30일 + 별도 승인까지 **보수적 유지**.

---

## 알파 리서치 (실행과 분리)

워치리스트 5종 선정 시 **고정 기록:**

| 항목 | 목적 |
|------|------|
| Q | 품질 |
| V | 밸류 |
| M | 모멘텀 |
| 유동성 pass | 실행 가능성 |
| 제외/탈락 사유 | value trap·일관성 |

수익률보다 **탈락 사유의 반복 일관성**을 먼저 본다.

---

## 30 / 60 / 90일 게이트

| 시점 | 질문 |
|------|------|
| **D+30** | 데이터가 매일 정상 갱신되는가? RED 원인 분류 가능한가? |
| **D+60** | dry-run 10일 통과 · ETF 소액 검토 여부 문서화 · stale 주 ≤1회 |
| **D+90** | **v1.0.2 동결** vs **v1.1** (B/C/D 중 하나만) |

---

## 주간 기록 (12주)

파일: `data/ops_weekly_log.md` (아래 표 복사·추가)

```markdown
### YYYY-Www (기준일 YYYY-MM-DD)
- core_price_gate: pass | fail — (stale N종 / …)
- operational_scope: NO_TRADE | ETF_ONLY | …
- RED/YELLOW 원인: DATA_STALE | POLICY_CAP | MARKET_RISK | DRY_RUN | OTHER — 한 줄
- PyKRX 수동 개입: 없음 | 있음 (사유)
- 이번 주 실제 매매: 없음 | ETF n종 소액 | …
```

---

## 한 줄

**지금은 시스템 개발자가 아니라 운용 감사관 모드.** v1.0.2는 키우지 않고 90일 반복 사용으로 신뢰도를 검증한다.
