# 트레일 익절 Review (L1) — 운영 스펙

> **상태:** 채택 · Phase B 구현 · **일자:** 2026-10-21 · **채팅:** SAA 알파 투자  
> **임계 고정:** T1=12% / T2=20% / T3=28% (진입가 +% 익절 안 함)  
> **불변:** `proposal_mode: pure_qvm` · `target_portfolio.csv` 사람만 · 자동주문 없음 · Core `score_m` 제외 · 코스피·코스닥 · 중기·단기 장부 분리  
> **연계:** [`EXIT_STEP_OPS_RULE.md`](EXIT_STEP_OPS_RULE.md) (L0 목표가) · [`MOMENTUM_HOLDING_MONITOR_SPEC.md`](MOMENTUM_HOLDING_MONITOR_SPEC.md) · [`SHORT_BOOK_SPEC.md`](SHORT_BOOK_SPEC.md) · [`VALUE_HOLD_EXIT_UPGRADE_PLAN.md`](VALUE_HOLD_EXIT_UPGRADE_PLAN.md) · [`trail_exit_signal.py`](../alpha_system/ui/services/trail_exit_signal.py)

---

## 0. 한 줄

**목표가(L0)는 가치 상한으로 유지**하고, **고점 대비 되돌림(L1 트레일)** 과 **단기 수급·가격 약화(L2)** 를 겹쳐  
「잘 나가다 목표가 전에 크게 되돌린」 기회비용·강제 손절을 줄인다.  
전부 **Review-only 배지·권고** (주문·target 자동기입 없음).

---

## 1. 왜 필요한가

| 현상 | 원인 | L0만의 한계 |
|------|------|-------------|
| 목표가 전 급락 | 모멘텀 붕괴·수급 이탈 | 목표가 배지가 안 켜짐 |
| 목표가 도달 전 변동성 | 추세 끝·되돌림 | “버틸 근거”만 있고 “줄일 근거” 없음 |
| +N% 고정 익절 거부 | 처분효과 ([VALUE_HOLD](VALUE_HOLD_EXIT_UPGRADE_PLAN.md)) | **진입가 +10%는 쓰지 않음** · **고점 트레일**은 별개 |

문헌 요지: Daniel–Moskowitz *Momentum Crashes* · trailing stop 위험축소 · Dual Momentum 절대추세 이탈 · Turtle/ATR 청산.

---

## 2. 청산 레이어 (고정)

```
보유 중 Review
  L0  목표가·PBR 익절 스텝     ← EXIT_STEP (기존)
  L1  고점 트레일·채널 이탈    ← 이 스펙 (중기 기본)
  L2  수급·단기 가격 약화      ← 단기 장부·차트×수급 (기존 신호 재사용)
  L3  급락 방어·재진입         ← CRASH_DEFENSE_REENTRY_SPEC
```

### 2.1 장부 매핑

| 레이어 | 중기 장부 | 단기 장부 |
|--------|-----------|-----------|
| L0 | 혼합 목표가·사다리 | **적용 안 함** (중기 목표가 익절 미적용 유지) |
| L1 | **주 청산** (트레일·채널) | 보조(짧은 창) 또는 단기 전용 trail |
| L2 | 차트×수급은 **힌트만** (중기 전량 트리거 금지) | **주 청산** (수급·단기 흐름) |
| L3 | **급락 줄이기/환금 Review** + 재진입가 (전량 강제 금지) | 미적용 |

원칙: **단기 약화 ≠ 중기 전량**. 단기는 축소/관망, 중기는 L1·L0이 깨질 때 환금·전량. L3는 속도 급락 시 **일부 현금화**만.

---

## 3. L1 트레일 규칙 (중기 · 채택값)

### 3.1 정의

| 기호 | 의미 | 기본 |
|------|------|------|
| `peak` | 편입 후(또는 감시 시작 후) **조정 고가** (일봉 고가 기준) | 보유 기간 max high |
| `drawdown` | `(peak − 현재가) / peak` | 0~1 |
| `trail_trim` | 되돌림 ≥ T1 | **줄이기 25%** Review |
| `trail_half` | 되돌림 ≥ T2 | **환금 절반** Review |
| `trail_exit` | 되돌림 ≥ T3 **또는** 채널 이탈 | **전량 Review** (테제 붕괴와 병합 가능) |

### 3.2 임계 (백테스트 전 운영 초안 · 사람 승인으로 고정)

| 코드 | 조건 | 배지 문구 | trim |
|------|------|-----------|------|
| T1 | drawdown ≥ **12%** | `트레일줄이기` | 25% |
| T2 | drawdown ≥ **20%** | `트레일환금` | 50% |
| T3 | drawdown ≥ **28%** | `트레일전량` | 100% |

변동성 적응(후순위): `T* = max(표값, k · ATR14/price)` — k 초안 2.0 / 3.0 / 4.0.  
**1차 구현은 고정 %** · ATR은 Shadow 비교 후.

### 3.3 채널 보조 (중기)

| 조건 | 배지 | 비고 |
|------|------|------|
| 종가 &lt; 60일 최저 (Donchian형) | `채널이탈` → T2 이상과 **강한 쪽** | 노이즈 줄이려 **종가 기준 · 1일 확정** |
| 중기 모멘텀 DOWN 연속 N일 (MHM) | `모멘텀이탈` → T1 이상과 병합 | N 기본 **5** ([MHM](MOMENTUM_HOLDING_MONITOR_SPEC.md)) |

### 3.4 L0과 충돌 시 우선순위

강한 쪽이 이김 (기존 EXIT와 동일 계열):

1. S0 하드·테제 · L0 `exit_full`  
2. L1 `trail_exit` / `채널이탈`  
3. L0 `cash_half` · L1 `trail_half` · L3 `급락환금` → **환금** (수량 절반)  
4. L0 `trim` · L1 `trail_trim` · L3 `급락줄이기` → **줄이기**  
5. L2 단기 약화 → 배지/칩만 (중기 수량은 L1·L0·L3이 결정)  
6. `hold`  

L3 단독 `exit_full` **금지** (전량 검토 힌트만). 상세: [`CRASH_DEFENSE_REENTRY_SPEC.md`](CRASH_DEFENSE_REENTRY_SPEC.md).

같은 날 L0 환금 + L1 환금 → 한 줄로 `환금` + why에 `목표가·트레일`.

### 3.5 명시적 금지

- 진입가 대비 고정 +10% 익절 (**처분효과 · VALUE_HOLD 거부 유지**)  
- 트레일 배지로 `target_portfolio.csv` / 주문 자동 기입  
- 중기 Core에 `score_m` 혼입  
- 단기 L2만으로 중기 전량 강제

---

## 4. L2 단기 규칙 (수급·가격 약화)

기존 신호를 **청산 Review 문구로만** 묶는다 (신규 데이터 파이프 최소화).

| 입력 | 출처 | Review 문구 |
|------|------|-------------|
| 차트 약세·추가금지 | `chart_flow_merge` | `단기약화` |
| 수급 이탈·관망 | flow Review | `수급약화` |
| short vol CUT / 흡수 | `short_vol_budget` · absorb | `단기예산축소` |
| MHM short_weak | `momentum_holding_monitor` | `단기모멘텀약화` |

**행동:** 단기 장부 → 줄이기/관망 Review · 중기 장부 → **칩만** (L1 미발화 시 수량 권고 없음).

---

## 5. UI

| 위치 | 표시 |
|------|------|
| 포트폴리오 ③·④ 배지 열 | L0 문구 유지 · L1이면 `트레일줄이기`/`트레일환금`/`트레일전량` (또는 기존 줄이기/환금 + why에 `고점−xx%`) |
| 펼침 | `peak` · `drawdown%` · T1/T2/T3까지 여유% · L0 목표가 진척 |
| 홈/익절 점검 | L1 발화 종목 섹션 「트레일 Review」 |
| 단기 행 | L2 칩 · 중기 L0/L1과 섞지 않음 |

카피 키(안): `portfolio.trail_trim` / `trail_half` / `trail_exit` / `trail_caption`.

---

## 6. 데이터·구현 스케치

| 항목 | 내용 |
|------|------|
| 입력 | `prices` 일봉 고가 시계열 · 보유 편입일(있으면) · 없으면 감시 N거래일 고점 |
| 금지 | **`high_52w` 단독을 peak로 쓰지 않음** (ATH 대비 되돌림 → 전량 과다 발화) |
| 모듈 | `alpha_system/ui/services/trail_exit_signal.py` |
| 병합 | `ops_exit_signal` 결과를 L1과 merge · 우선순위 §3.4 · 시계열 없으면 L1 미발화 |
| 설정 | `trail: {t1: 0.12, t2: 0.20, t3: 0.28, lookback_days: 120}` |
| 테스트 | peak/drawdown · high_52w 미발화 · L0+L1 우선순위 · target 미기록 |

---

## 7. Shadow·검증 (Go 전)

1. Shadow 중기: **L0만** vs **L0+L1** — MDD·이익보호·매매횟수  
2. F&F·현대지에프홀딩스급 사례: 고점 대비 T1/T2가 목표가보다 먼저 켜지는지 재현  
3. 임계는 Shadow 후 T1/T2/T3만 조정 · 레이어 구조는 고정

---

## 8. 구현 순서

| Phase | 내용 | 완료 기준 |
|-------|------|-----------|
| **A** | 이 스펙 운영자 승인 (임계 숫자) | ✅ 2026-10-21 · T1/T2/T3=12/20/28 |
| **B** | `trail_exit_signal` + ops merge + 테스트 | ✅ pytest · target 미기록 |
| **C** | 포트폴리오·익절 점검 UI | 배지 why에 L1 · 후속 폴리시 |
| **D** | Shadow L0 vs L0+L1 리포트 | 문서 1장 · 임계 재고정 |
| **E** | L3 급락 방어·재진입 | ✅ 스펙+엔진 · Review-only |

---

## 9. 승인 체크 (운영자)

- [x] T1=12% / T2=20% / T3=28% 채택  
- [x] 진입가 +% 익절 **안 함** 확인  
- [x] 단기 L2 → 중기 전량 **금지** 확인  
- [x] 자동주문·target 기입 **없음** 확인  
- [x] Phase B 착수 승인

---

## 10. 하지 않는 것

- 익절 자동 집행 2차 (미승인 · [`V3_AGENT_START`](V3_AGENT_START.md))  
- FASTJUSIK · Core `score_m`  
- 미국 ETF 카나리아를 L1에 혼입 (신용 점검은 나침반)
