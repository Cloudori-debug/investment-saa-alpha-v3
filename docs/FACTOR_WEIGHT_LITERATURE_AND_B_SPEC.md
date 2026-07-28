# 팩터 가중 문헌 조사 · B안(SR 흡수) 스펙

> **일자:** 2026-07-29  
> **목적:** 현재 Core 가중(Q35/V30/SR25/R10)이 문헌 근거인지·임의인지 판정하고, CECS `execution`을 `score_sr`에 흡수하는 **B안**을 고정한다.  
> **구현:** 이 문서는 스펙·조사. 코드 반영은 별도 승인 후.

---

## 1. 현재 시스템 (사실)

| 축 | 코드 | Core 가중 | 실질 내용 |
|----|------|-----------|-----------|
| Quality | `score_q` | **35%** | ROE·OPM·부채·이익안정 |
| Value | `score_v` | **30%** | PER/PBR/EV·FCF |
| Shareholder Return | `score_sr` | **25%** | 배당수익률·성향·자사주 불리언 |
| Risk (저위험) | `score_r` | **10%** | 변동성·52주 위치·베타 (**리레이팅 아님**) |
| Momentum | `score_m` | **0%** | Review-only |
| CECS | `cecs` | **0%** (Ops A) | execution/pension/purpose — 순위 미반영 |

- 산출: `alpha_portfolio` · 롤업: `alpha_system/config/scoring.yaml`
- **데이터로 IR/백테스트 최적화한 가중 흔적 없음** (YAML 휴리스틱 + 설계 가설)
- 문서도 blend 0.70/0.30 등은 「확정 근거 미문서화」로 남아 있음

---

## 2. 문헌 판정 — 「테마」vs「가중 숫자」

### 2.1 테마 자체 — 문헌과 정합 (임의 아님)

| 우리 축 | 대표 문헌 | 요지 |
|---------|-----------|------|
| **Q** | Asness–Frazzini–Pedersen *Quality Minus Junk* (RAofS 2019; SSRN 2013) | 수익성·성장·안전·경영품질 → 위험조정 수익 |
| **Q (수익성)** | Novy-Marx (2013) gross profitability; Fama–French (2015) RMW | 수익성 팩터 |
| **V** | Fama–French (1993) HML; FF (2015) | 밸류 프리미엄 |
| **SR / payout** | Boudoukh et al. (JF 2007) *payout yield*; Straehl–Ibbotson total payout | 배당만보다 **배당+환매(total payout)** 가 설명력↑ |
| **저위험 R** | Betting-against-beta / low-vol 계열 (Frazzini–Pedersen 등) | 저베타·저볼 프리미엄 (논쟁 있으나 실무 스타일로 널리 사용) |
| **M 제외** | Jegadeesh–Titman (1993) 등 — 우리 선택 | 모멘텀은 **별 팩터**; Core에서 빼는 것은 설계 선택(차터와 일치) |
| **한국** | Kang–Kang–Kim (AJFS; FF5 Korea); Kang–Jang (2016) | 한국에서 FF5 설명력 **제한·분기 수익성 조정 필요** 가능 → 미·글로벌 가중을 그대로 신봉하면 안 됨 |

**결론 A:** “퀄리티·밸류·주주환원(페이아웃)·방어(저위험)로 순위를 짠다”는 **문헌 테마와 맞다.**  
모멘텀을 Core에서 뺀 것도 문헌상 ‘틀린’ 게 아니라 **역할 분리(순위 vs 집행 참고)** 다.

### 2.2 가중 숫자 35/30/25/10 — 문헌 최적값이 아님 (휴리스틱)

논문·실무가 **공통으로 말하지 않는 것:**

- “Q 35% + V 30% + SR 25% + R 10%가 최적” 같은 **단일 정답 가중표는 없다.**
- 학계 팩터 모델은 보통 **롱숏 팩터 포트**를 만들고, 스타일 블렌드는  
  - **등가중(equal-risk / equal-weight styles)** 이거나  
  - **리스크 타깃·IR 최적화** (AQR 등)  
  이지, 0~100 스코어 가중합 35/30/25/10을 도출하지 않는다.
- AQR 등: multi-style은 **점수 통합(integrate)** 후 포트 구성이 mix보다 낫다 — 우리 `weighted sum of scores`와 **방향은 유사**, 그러나 그 가중치 자체는 제품 선택.

**결론 B:**  
- **무엇을 넣었는가** → 문헌 지지.  
- **몇 %씩 섞었는가** → **임의(설계 휴리스틱)** 에 가깝다. 캘리브레이션·한국 표본 검증 전제 없음.  
→ “논리적으로 맞다”고 말할 수 있는 층은 **팩터 선택·모멘텀 제외**까지이고, **퍼센트는 잠정값**으로 문서화하는 게 정직하다.

### 2.3 SR 세부 vs 문헌

| 현재 SR | 문헌 시사 |
|---------|-----------|
| 배당 yield 50% + payout 25% + buyback **불리언** 25% | Total **payout yield**(배당+순환매 **연속량**)이 배당만보다 우월 (Boudoukh 2007 등) |
| buyback을 80/30 이산 | 약함 — **순환매수익률**이 표준에 더 가깝다 |
| CECS `execution` = 4분기 이벤트 연속성 | 문헌의 “reputation / persistence of payout”과 맞음 — **SR에 흡수할 논리적 후보** |
| 한국: 배당 평판·자사주 기회주의 문헌 | 연속성·순증 검증 없으면 환원 시그널 오염 가능 → **execution 흡수가 의미 있음** |

---

## 3. B안 스펙 (승인용) — **구현됨 2026-07-29**

### 3.1 목표
- 정량 스크리닝 시 **환원 연속성(execution)** 을 `score_sr`에 반영한다.
- **순위 가중은 CECS가 아니라 `score_sr` 내부**로만 (Ops A·「CECS 재혼합」금지 유지).
- pension / purpose 는 CECS 참고·게이트용 유지 (순위 0).

### 3.2 `score_sr` 재구성 (**적용**)

| 서브 | 내용 | 가중 | 비고 |
|------|------|------|------|
| SR1 | dividend yield | 0.30 | |
| SR2 | payout ratio | 0.15 | |
| SR3 | buyback_3y 불리언 | 0.25 | 추후 net buyback yield 권장 |
| **SR4** | **execution continuity** (0/25/50/75/100) | **0.30** | `execution_continuity.py` |

코드: `alpha_portfolio/src/execution_continuity.py` · `factors.score_shareholder`  
출력 진단: `alpha_scores.csv` 의 `sr_execution`, `sr_execution_provenance`

### 3.2b Provenance
| 태그 | 의미 |
|------|------|
| `quarters` | `execution_quarters_hit` / `payout_event_quarters` 명시 |
| `unit01` / `score100` | 기존 CECS 스케일 입력 |
| `proxy_snapshot` | **임시** — 배당·자사주·성향 스냅샷으로 4분기 근사 (DART 이벤트 테이블 전) |
| `neutral` | 신호 없음 → 50 |

### 3.3 CECS 측
- `total_score_blend.cecs` = **0.0** 유지 (순위 미반영).
- CECS 수동 execution과 SR4가  alike할 수 있으나 **순위에는 SR만** 들어가 이중 가중이 아님.

### 3.4 Core 롤업
**B0+B1 적용:** Q/V/SR/R = **35/30/25/10 유지** · 문서에 휴리스틱 명시.

### 3.5 데이터·파이프라인
- 소스: DART 배당·자사주·소각 공시 (FASTJUSIK 금지 유지).
- 산출 시점: 정량 전체 갱신 / alpha_scores 재생성과 동일 배치.
- provenance: `execution_as_of`, 분기 카운트, 출처 ID를 runtime/json에 남김.
- 실패 시: SR4=50(중립) + YELLOW 게이트 — 순위 폭주 방지.

### 3.6 비범위
- pension·purpose 순위 편입  
- CECS blend 복원  
- score_m Core 복원  
- 가중 자동 최적화 UI  

### 3.7 수용 기준 (구현 후)
1. 동일 유니버스에서 SR4 분포·결측률 리포트  
2. SR4↔기존 SR3 상관 (이중계산 과도하면 SR3 축소)  
3. proposal top-N churn이 급변하지 않을 것(운영자 스모크)  
4. 차터 문구: “execution은 SR 하위 · CECS 순위 가중 0”

---

## 4. 한 줄 답 (운영자 질문)

> 순위가중 기준 점수가 논리적으로 맞나, 임의인가?

- **축 선택(Q/V/SR/저위험, M 제외):** 문헌과 **논리적 정합**.  
- **35/30/25/10 및 서브가중·linear 구간:** **임의(휴리스틱)** — 논문이 그 숫자를 주지 않음.  
- **B안:** 문헌이 강하게 지지하는 것은 “배당만”이 아니라 **total payout + 환원 지속성** → execution을 **SR에 넣는 것**이 CECS에 순위를 주는 것보다 맞다.

---

## 5. 참고 링크

- QMJ: https://doi.org/10.1007/s11142-018-9470-2  
- FF 2015: https://doi.org/10.1016/j.jfineco.2014.10.010  
- Boudoukh et al. payout yield: https://doi.org/10.1111/j.1540-6261.2007.01226.x  
- Korea FF5 비교: https://doi.org/10.1111/ajfs.12274  
- 내부: `docs/archive/20260729_hygiene/V2_LITERATURE.md`, `alpha_portfolio/docs/02_스코어링_설계.md`
