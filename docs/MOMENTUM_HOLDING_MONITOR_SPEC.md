# 모멘텀 종목 — 상방/하방 객관 측정 (문헌 + 현 시스템 + 스펙 초안)

> **일자:** 2026-07-29  
> **질문:** 모멘텀주는 들어갈 때·나올 때가 더 명확해야 하지 않나? 보유 내내 상방/하방을 객관 측정하고 싶다.  
> **불변:** Core `score_m` 제외 · 자동매매 없음 · Review-only

---

## 1. 직관이 맞는지 (문헌)

**맞다.** 모멘텀은 밸류/퀄리티와 성격이 다르다.

| | 밸류·퀄리티 | 모멘텀 |
|--|-------------|--------|
| 근거 | 펀더멘털·상대 저평가가 **천천히** 변함 | **가격 추세 지속** (3–12M) |
| 보유 | buy-and-hold에 가깝게 버틸 여지 | **재랭크·재진입/청산이 본질** (Jegadeesh–Titman 1993) |
| 위험 | 장기 저평가 지속 | **크래시·급반전** (Barroso–Santa-Clara 2015; Daniel–Moskowitz 2016) |
| 실무 함의 | 목표가·논지·밴드 | **추세 부호·상대 순위·변동성**으로 노출 조절 |

핵심 문헌:

- **Jegadeesh & Titman (1993)** — 승자 매수/패자 매도; 형성 3–12M · 보유 3–12M; **정기 교체가 필요** (방치 buy-hold로는 모멘텀을 못 잡음).
- **Moskowitz et al. (2012) TSMOM** — 자산 **자체** 과거 수익 부호(상방/하방)로 롱/숏; vol scaling.
- **Barroso & Santa-Clara (2015)** — 모멘텀 위험은 예측 가능; **실현변동성으로 노출 축소**하면 크래시↓·Sharpe↑ (이산 “매도 버튼”보다 **스케일링**이 표준).
- **Daniel & Moskowitz (2016)** — 베어+고변동 후 반등기에 모멘텀 크래시; 조건부 헤지/스케일.

**결론:** “선별만 하고 보유 중 추세를 안 보면” 문헌상 모멘텀 전략이 아님.  
**들어갈 때(상방·상대 강세) / 나올 때 또는 줄일 때(하방·상대 약화·고변동)** 를 객관 지표로 두는 게 맞다.  
다만 우리 차터상 **자동 청산이 아니라 Review-only 측정·권고**여야 한다.

---

## 2. 지금 시스템 (사실)

이미 있는 것 (`momentum_review.py` · `MOMENTUM_REVIEW_ONLY_SPEC`):

| 측정 | 내용 | 한계 |
|------|------|------|
| 절대 방향 | 12-1 부호 → UP/DOWN | `R12−R1` 근사 (문헌 skip-month와 다름) |
| 상대 강도 | 유니버스 퍼센타일 `cross_pct` | 있음 |
| 변동성 | `vol_high` (≥80%ile) → CUT_PACE | 있음 |
| 등급 | GO/SLOW/WAIT/CUT_PACE | **분할매수 속도** 중심 |
| 주기 | 스냅샷·UI 재오픈 시 | **이력·알림·모멘텀주 전용 보드 없음** |
| 청산 | WAIT ≠ 자동 매도 | 익절/테제/S2a와 분리 |

`score_m`(6M+52주)는 Core 제외 · Review(12-1)와 **다른 축** → satellite 스크리너와 홈 모멘텀이 어긋날 수 있음.

**갭:** “모멘텀주로 들어갔으면, 보유 내내 상방인지 하방인지”를 **전용으로 로그·표시**하는 층이 약함.

---

## 3. 측정 시스템 (Review-only) — **구현 2026-07-29**

이름: **Momentum Holding Monitor (MHM)**  
코드: `alpha_system/ui/services/momentum_holding_monitor.py`  
UI: 홈「모멘텀 보유 모니터」

### 3.1 매일(또는 정량 갱신 시) 기록하는 객관 필드

| 필드 | 정의 | 상방/하방 |
|------|------|-----------|
| `ts_sign` | `return_12m_ex_1m` > 0 → **UP** else **DOWN** | 절대 |
| `xs_pct` | 유니버스 12-1 퍼센타일 | 상대 강도 |
| `xs_bucket` | ≥60 Strong / 40–60 Mid / <40 Weak | |
| `vol_flag` | `volatility_60d` ≥ 80%ile | 위험 |
| `grade` | 기존 GO/SLOW/WAIT/CUT_PACE | 집행 속도 |
| `bearing` | **ENTER_OK** / **HOLD_UP** / **TRIM_PACE** / **EXIT_REVIEW** | 보유 중 바늘 |

### 3.2 bearing 룰 (초안 · 사람 확인)

| bearing | 조건 (모두 Review) |
|---------|-------------------|
| ENTER_OK | UP · xs≥60 · not vol_high · GO | 신규/추가 분할 허용 |
| HOLD_UP | UP · xs≥40 · not CUT_PACE | 유지 |
| TRIM_PACE | SLOW 또는 vol_high 또는 CUT_PACE | 남은 SCALE_IN 중단·비중 축소 **검토** |
| EXIT_REVIEW | DOWN 또는 xs<40 (WAIT) **연속 N일**(기본 5 거래일) | 전량/교체 **검토** (자동매도 아님) |

N일 연속은 “노이즈 한 방”을 줄이려는 문헌·실무 공통 감각 (이산 청산 신호의 최소 필터).

### 3.3 상방 vs 하방 “객관” 한 줄

```
상방 = ts_sign=UP AND xs_pct≥40
하방 = ts_sign=DOWN OR xs_pct<40
위험가속 = vol_flag
```

가격 목표가 `remaining_upside`와 **이름을 섞지 말 것** (익절 여력 ≠ 모멘텀 상방).

### 3.4 UI · 로그 (**적용**)
- 홈: **모멘텀 보유 모니터** 표 (상방 Y/N · 바늘 · 전일대비 · 연속약세)
- 토글「전체 실보유」— 기본은 momentum 역할·SCALE_IN만
- `data/local/momentum_holding_log.jsonl` 일자별 기록 (gitignore `data/local/`)
- 자동매도·저널 강제 기록 없음

### 3.5 비범위
- Core 순위에 `score_m` 재혼합  
- WAIT/DOWN 시 자동 주문  
- 차트 패턴·ADX 필수화 (후순위)

### 3.6 후속 개선
1. 진짜 12-1 skip-month 수익률  
2. `score_m` vs Review 축 통일 또는 satellite만 12-1  
3. Barroso식 **노출 스케일 권고** (% 숫자)를 CUT_PACE에 연결  

---

## 4. 테스트 메모 (2026-07-29)

- `pytest` SR4·scoring·nav: **24 passed**
- `run_alpha_quant_snapshot.py --skip-collect`: scored 400 · `sr_execution` 컬럼 기록됨 · target 미기록

---

## 5. 참고

- Jegadeesh–Titman (1993) JF  
- Moskowitz–Ooi–Pedersen TSMOM (2012)  
- Barroso–Santa-Clara (2015) JFE  
- Daniel–Moskowitz (2016) JFE Momentum crashes  
- 내부: `docs/MOMENTUM_REVIEW_ONLY_SPEC.md`, `momentum_review.py`
