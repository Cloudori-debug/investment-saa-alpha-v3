# 운용 승인 기준 (Acceptance Criteria) v1.0 FROZEN

> **역할:** **실거래·운용 판단의 최종 게이트** (MVP_SPEC은 개발 스펙)  
> **현재 판정:** Overall **YELLOW** · Scope **ETF_ONLY** · Alpha **RESTRICTED**

**원칙:** 테스트 통과 ≠ 실거래 승인. **Overall Status**와 **Execution Scope**를 분리한다.

---

## 1. 두 축 판정

| 축 | 값 | 의미 |
|----|-----|------|
| **Overall Status** | GREEN / YELLOW / RED | 시스템·데이터·gate 종합 |
| **Execution Scope** | NO_TRADE / ETF_ONLY / ETF_AND_BETA / FULL_WITH_ALPHA | **실제 허용 행위 범위** |
| **Alpha Approval** | APPROVED / RESTRICTED / BLOCKED | kr_alpha 신규매수 |

현재 권장 상태:

```
Overall Status: YELLOW
Execution Scope: ETF_ONLY
Alpha Approval: RESTRICTED
kr_alpha 신규매수: 금지
자동매매: 영구 금지
```

---

## 2. 종합 판정 알고리즘

### 2.1 Critical FAIL → Overall RED · Scope NO_TRADE

- AC-01 system_health.fail ≥1  
- AC-03 portfolio_gate RED  
- AC-02 unified_data_gate RED  
- AC-05 manual override **만료 후仍 적용** 또는 reason 없음  
- AC-06 provenance **없음** 또는 stale >5영업일  

### 2.2 Alpha-only FAIL → Overall YELLOW · Alpha BLOCKED · Scope ETF_ONLY

- AC-04 alpha_gate RED  
- AC-07 Alpha coverage <50%  

→ **ETF·자산군 리밸런싱은 계속 검토 가능** (Alpha FAIL이 전체 RED가 되지 않음)

### 2.3 WARN → Overall YELLOW

- unified/portfolio YELLOW  
- AC-06 stale 3~5일  
- AC-09 dry-run 5~9일  
- AC-10 향후 FOMC 없음 (과거만)  
- AC-08 gpt_context만 존재 (bundle·run_id 없음)  
- AC-05 override 5영업일 초과 또는 만료 1~2일 전  

### 2.4 GREEN

- Critical FAIL 0, WARN 0, Alpha APPROVED, dry-run ≥10일 (GREEN 승격 시)

**GREEN이어도 자동매매는 금지.**

---

## 3. AC-xx 상세

| ID | scope | PASS | WARN | FAIL |
|----|-------|------|------|------|
| AC-01 | core | fail=0 | — | fail≥1 |
| AC-02 | core | GREEN | YELLOW | RED |
| AC-03 | core | GREEN | YELLOW | RED |
| AC-04 | alpha | GREEN | YELLOW | RED |
| AC-05 | core | 유효 override+reason | age>5d 또는 만료 1~2d 전 | 만료 후 적용 / reason 없음 |
| AC-06 | core | stale ≤2d | 3~5d | >5d 또는 provenance 없음 |
| AC-07 | alpha | coverage ≥80% | 50~79% | <50% |
| AC-08 | ops | bundle run_id = manifest | gpt_context만 | 없음 |
| AC-09 | ops | dry-run ≥10일 | 5~9일 | <5 (GREEN 전) |
| AC-10 | ops | **향후 90일 내** FOMC 1건+ | 과거만 | 비어 있음 |

---

## 4. 운용 행위 매트릭스

### Effective Data Gate

| Gate | ETF·자산군 | 국내 베타 | kr_alpha 신규 | 자동매매 |
|------|-------------|----------|---------------|----------|
| GREEN | ✅ 검토 | ✅ trigger 시 | ⚠️ 사람 승인 | ❌ |
| YELLOW | ✅ 검토 | ⚠️ Wait | ❌ | ❌ |
| RED | ❌ | ❌ | ❌ | ❌ |

### Execution Scope

| Scope | 허용 |
|-------|------|
| NO_TRADE | 점검·데이터 수정만 |
| ETF_ONLY | cash_short_bond·ETF·자산군 Gap·Hold/Trim |
| ETF_AND_BETA | + domestic/global beta (trigger 충족 시 검토) |
| FULL_WITH_ALPHA | + kr_alpha (사람 승인·checklist) |

---

## 5. Manual regime (MVP_SPEC §3.1.1과 동일)

| 컬럼 | 필수 |
|------|------|
| regime_override_reason | override 시 ✅ |
| regime_set_date | ✅ |
| regime_expires_date | ✅ 권장 |

만료 초과 → 산출 레짐 자동 적용 · AC-05 FAIL if still applied.

---

## 6. Provenance · FOMC · Dry-run

- Provenance: `data/market_data_provenance.json` — [MVP_SPEC §3.1.2](MVP_SPEC.md)  
- FOMC: **수동 YAML 캘린더** (`events.fomc_dates`) — 자동 API 아님  
- Dry-run: [DRY_RUN_LOG_SCHEMA.md](DRY_RUN_LOG_SCHEMA.md)

---

## 7. 문서 계층

```
MVP_SPEC.md v1.0 FROZEN     ← 개발·데이터·로직 (기능 추가 동결)
USER_GUIDE.md               ← 사용설명서 (운용자)
ACCEPTANCE_CRITERIA.md      ← 실운용 승인 (최종 게이트) ★
DRY_RUN_LOG_SCHEMA.md       ← paper-run 기록
```

---

## 8. GREEN 승격 조건 (체크리스트)

- [ ] dry-run ≥10 영업일  
- [ ] Critical AC FAIL = 0  
- [ ] core data stale ≤2일  
- [ ] Alpha bulk universe 검증 (coverage ≥80%)  
- [ ] unified gate GREEN 또는 ETF_ONLY 조건부 승인 문서화  
- [ ] 운용자 sign-off  

---

*변경 시 CHANGELOG + AC 재검토. MVP_SPEC 기능 추가 없이 AC/dry-run만 v1.0.x 패치.*
