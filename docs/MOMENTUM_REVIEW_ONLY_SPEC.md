# 모멘텀 Review-only 집행 판정 — SPEC

> **상태: 승인·구현** · 승인일: 2026-07-28 · 채팅: SAA 알파 투자 · v3  
> **범위:** 홈 UI 표시 + 사람 실행/보류 저널 · **비범위:** QVM/`score_m` Core 혼합, target 자동기입, 자동주문

---

## 1. 목적

이미 QVM으로 선정·승인된(또는 SCALE_IN 중인) 종목에 대해  
**살지 / 얼마나(회차 속도)** 를 모멘텀·변동성으로 **정량 등급**을 붙여 사람이 집행한다.

---

## 2. 주기

| 주기 | 행위 |
|------|------|
| 신호 기준 | `data/prices.csv` **전일(최신) 종가 스냅샷** — 장중 재등급 없음 |
| 매일 | 레짐·CRISIS·등급 변화 **확인만** |
| 매주 / SCALE_IN 회차일 | GO·SLOW면 그날 몫 **실행** 또는 **보류** 기록 |

---

## 3. 신호 (문헌 출발값)

| 필드 | SoT | 근거 |
|------|-----|------|
| `ret_12_1` | `return_12m_ex_1m` | Jegadeesh–Titman · 실무 12-1 |
| `ret_6` / `ret_3` | `return_6m` / `return_3m` | 보조 확인 |
| `cross_pct` | 유니버스 교차 퍼센타일(`ret_12_1`) | 교차 모멘텀 |
| `absolute` | `ret_12_1 > 0` → UP else DOWN | Moskowitz TSMOM 방향 |
| `vol_high` | `volatility_60d` ≥ 유니버스 80%ile | Barroso–Santa-Clara 노출 축소 |

임계값(교차 60/40, vol 80%ile)은 **초기값** — 한국 표본 dry-run 후 조정 가능.

---

## 4. 등급 → 권고 집행

| 등급 | 조건(우선순위↑) | 권고 |
|------|-----------------|------|
| **WAIT** | 절대 DOWN 또는 교차 &lt;40 | 이번 회차 0% · 실행 버튼 잠금 |
| **CUT_PACE** | CRISIS 또는 vol_high (WAIT 아닌 경우) | 잔여 SCALE_IN 중지 |
| **GO** | 교차≥60 · UP · vol 정상 · 보조 비모순 | 3회 균등 1/3 |
| **SLOW** | 그 외 (교차 40~60 또는 보조 불일치) | 2회 1/2 또는 1회차만 |

모멘텀은 종목 캡을 **올리지 않음**. SCALE_IN 규칙·섹터캡 유지.

---

## 5. UI

- 위치: 홈 · 「월 리밸」 아래 **「모멘텀 집행 판정」**
- **표(시안과 동일):** 종목 · 12-1 · 교차% · 절대 · 변동성 · 등급 · 권고 · 내 판단
- 종목 radio 선택 → **실행 / 보류** 만 (부가 설명·expander·보유 링크 없음)
- 자동주문·`target_portfolio.csv` 쓰기 **금지**

---

## 6. 불변

- `proposal_mode: pure_qvm` · Core에서 `score_m` 제외
- Review-only (kr_alpha)
- FASTJUSIK 금지 — 가격은 PyKRX 스냅샷만
