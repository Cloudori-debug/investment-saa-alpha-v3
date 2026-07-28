# 익절(A/B) · 테제 훼손 편출 — 명세서 (초안)

> 근거: [`EXIT_WEIGHT_GAP_AUDIT_RESULT.md`](EXIT_WEIGHT_GAP_AUDIT_RESULT.md) P0 확정 (2026-07-15)  
> 의도: **이겼을 때 언제 줄이는가**(익절 A/B)와 **테제가 틀렸을 때 어떻게 나오는가**(THESIS/POLICY)를 분리  
> 범위: **Review-only 평가·표시** — `data/target_portfolio.csv` 자동 변경 금지, 실행 자동화 없음  
> 개정(2026-07-15): §2.C 추가 — 전량 온오프 대신 **신호강도 계단식 부분 조정**(고정 35% 폐기). "확률" 표기 금지 원칙 명시.  
> 개정(2026-07-15, 2차): §2.D 추가 — **모멘텀 카운터체크** (밸류 익절이 모멘텀 지속성과 충돌 시 밴드 하향). 근거: 모멘텀·처분효과 학술 문헌.

## 0. 불변

- `proposal_mode: pure_qvm` — 하케다카·수급으로 제안 순위 바꾸지 않음
- kr_alpha = Review-only; ETF·현금·채권만 Executable (scope 허용 시)
- `target_portfolio.csv`는 **사람 승인 UI만** 변경
- Soft/Hard 악화 퇴출(`03_퇴출_규칙`, `exit_engine`)과 **섞지 말 것** — 익절 ≠ Soft S03(value_trap)
- FASTJUSIK 스크래핑 금지 — 재무·가격은 기존 PyKRX/DART·수동 목표 입력

## 1. 문제

현재 퇴출은 저스코어·게이트·수동 hard flag 중심이다.  
ROE/배당/자사주·PBR 목표는 스코어·보드 **표시**만 하고, “목표 도달 → 부분 익절”과 “정책/테제 훼손 → 편출·강등”은 **없다**.

## 2. 승인 범위 (이번 SPEC)

### A. 익절 트리거 A/B 분리 + OR 부분익절

| ID | 조건 | 의미 |
|----|------|------|
| **TP-A** (펀더멘털 목표) | 종목별 목표: ROE 하한, 배당성향 하한, 자사주 소각/집행 완료 플래그 등 **내재·정책 촉매 도달** | “펀더멘털로 이겼다” |
| **TP-B** (밸류/센티먼트) | 종목별 PBR(또는 fair) 상한, 목표가 대비 괴리, 시장/섹터 과열 플래그 등 **가격 기준 도달** | “가격으로 이겼다” |

**결합:** `TP-A OR TP-B` → 권고 기본 `Trim` (부분 익절). 전량 `Exit`/`Replace`는 **기본 금지**(둘 다 충족 + 한도·사람 승인 시에만 `Exit-review`).

**부분익절 비율은 고정값이 아니라 §2.C 신호강도 계단식 매핑을 따른다** (기존 `exit_partial_frac: 0.35` 단일 고정값 폐기).

**경계 매트릭스 (A-4)**

| 펀더멘털 | 시장/밸류 | 권고 |
|----------|-----------|------|
| 도달 | 미과열 | **Trim** (`exit_leg=FUND`) — 전량 Exit 금지 |
| 미달 | 과열/목표가 도달 | **Trim** (`exit_leg=VAL`) — thesis intact면 Replace 금지 |
| 도달 | 과열 | **Trim** 가속 또는 `Exit-review` (`exit_leg=BOTH`) — 사람 승인 |
| 미달 | 미과열 | Hold (익절 경로 무관) |

### B. 테제 훼손 편출 (익절과 별 경로)

| ID | 조건 | 권고 |
|----|------|------|
| **TB-01** `THESIS_BREAK` | 투자 논리 핵심 깨짐(수동 확정 또는 명시 플래그) | `Exit` / `Exit-review` (Hard 급). Park 금지 |
| **TB-02** `POLICY_THESIS` | 상법·IFRS·정책 촉매 **지연/후퇴**로 테제 손상 (수동 또는 policy 플래그) | Core→Satellite **강등 검토** 또는 Trim/Replace-review. CECS `policy_dependency` 페널티만으로 대체하지 말 것 |
| **TB-03** (선택·P1) | 경영권 분쟁·회계 이슈 등 tail — 기존 H02/H07·보드 `accounting_issue`와 **매핑만** (중복 엔진 금지) | Hard Replace와 동일 취급 |

우선순위(동시): `THESIS_BREAK` / Hard > Soft 악화 > **익절 Trim** > Hold.

### C. 신호강도 기반 계단식 부분익절 비율 (동준님 제안 반영, 2026-07-15)

전량 익절/손절이 아니라, **신호강도에 비례해 비중만 일부 조정**한다. 이진 온오프 대신 계단식 완충 구간을 둬서 whipsaw(경계선 왕복 매매)를 줄인다.

**용어 원칙 — 반드시 "신호강도"라 부르고 "확률"·"승률"·"성공확률"이라 부르지 않는다.** 이 값은 기존에 이미 계산 중인 `factor_scoring.py`의 유니버스 내 퍼센타일 순위(0~100)를 재사용한 것이지, 과거 실현 성과로 보정(calibration)된 통계적 확률이 아니다. 오늘 확인한 대로 알파 백테스트 유효표본이 아직 10일 수준이라 calibration 자체가 불가능한 상태 — "72% 확률" 같은 표현은 검증되지 않은 숫자에 과도한 정밀도 착시를 준다. 계단식(구간) 표시도 이 착시를 줄이기 위한 장치다.

**신호강도 산정 (개념 · 정확한 가중치는 구현 시 결정)**

- TP-B(밸류): 기존 `valuation_score`/`v_rank` 퍼센타일을 그대로 강도로 사용
- TP-A(펀더멘털): 하위 조건 중 충족 개수 비율(예: 3개 중 2개 충족 → 66.7)로 환산
- 둘 다 충족 시 강도는 더 높은 쪽 채택(단순 평균으로 희석하지 않음) — 근거를 `rationale`에 컴포넌트별로 남길 것(예: "TP-B 88(밸류) / TP-A 66.7(펀더멘털 2/3)")

**계단식 매핑 (기본값 — 조정 가능)**

| 신호강도 구간 | 부분 Trim 비율 |
|---|---|
| 70 ~ 80 | 10% |
| 80 ~ 90 | 20% |
| 90 이상 | 30% |
| 70 미만 | Hold (Trim 트리거 아님) |

- `THESIS_BREAK`(TB-01/02)는 이 표와 무관 — 여전히 Hard급 전량 `Exit`/`Exit-review` 우선.
- 구간·비율 숫자 자체는 미검증 초기값이다(다른 파라미터들과 동일 원칙) — 백테스트 가능해지면 재조정 대상.

### E. 숫자 잠금 — 목표가 도달·잔여 보유 (2026-07-19)

**단일 SoT:** [`EXIT_NUMERIC_LOCK.md`](EXIT_NUMERIC_LOCK.md). 아래는 요약.

| 상황 | Trim | 잔여 보유 |
|------|------|-----------|
| 근접 &lt;70 | 0% | 100% |
| 근접 70–80 | 10% | ~90% |
| 근접 80–90 | 20% | ~80% |
| **목표가 도달** (hit / 근접≥90 / 현재가≥목표가) | **30%** | **70%** |
| 위 + 모멘텀≥70 (VAL/BOTH) | **20%** | **80%** |
| 테제·하드·교체 확정 | (표 무시) | **0% 검토** |

- 도달 후 **추가 자동 Trim 없음** (목표가 상향 재승인 전).
- “항상 70%만 보유”가 아니라 **도달 시 1회 30% 익절 권고 후의 잔여**.

### D. 모멘텀 카운터체크 (밸류 익절 × 모멘텀 지속성, 2026-07-15 추가)

**근거**: 학술 문헌상 (1) 모멘텀 효과 — 최근 3~12개월 상승 종목은 이후에도 계속 이기는 경향(Jegadeesh & Titman 1993), (2) 밸류·모멘텀 상관관계 약 -0.60 — 밸류 신호와 모멘텀 신호가 자주 반대로 움직임(Asness·Moskowitz·Pedersen 2013), (3) 처분효과 — "올랐으니 판다"는 행동이 실증적으로 손해였음(Odean 1998, 판 승자가 보유 패자 대비 12개월간 평균 -3.4%p). 즉 **TP-B(밸류 도달) 단독 신호로 파는 건 모멘텀이 아직 살아있는 종목을 조기에 잘라낼 위험**이 있다.

**규칙**:

- 적용 대상: `exit_leg ∈ {VAL, BOTH}`인 경우만 (TP-A 단독=`FUND`에는 미적용 — 펀더멘털 촉매 달성은 모멘텀 지속성과 별개 논리이므로)
- 조건: 종목의 기존 `momentum_score`(퍼센타일, `factor_scoring.py` 계산값 재사용)가 `momentum_override_threshold`(기본 70) 이상이면 **§2.C 매핑 결과에서 한 단계 낮은 밴드로 하향** (예: 30%→20%, 20%→10%, 10%→0%/Hold)
- `rationale`에 하향 근거를 반드시 병기 (예: "TP-B 88(밸류) but momentum 82(지속성 강함) → 카운터체크로 20%→10% 하향")
- 이 체크도 다른 파라미터와 동일하게 **미검증 초기값** — `momentum_override_threshold=70`은 조정 가능하며, 사람이 보드에서 최종 승인 시 이 하향 결과 자체도 오버라이드 가능해야 함(체크가 하향을 "강제"하는 게 아니라 "권고"임을 유지)

## 3. 데이터·API (구현 시)

### 3.1 종목 목표 (수동 YAML/CSV · 사람 유지)

예시 스키마 (`data/kr_alpha_exit_targets.yaml` 가칭):

```yaml
version: "0.1"
defaults:
  # 고정 exit_partial_frac 폐기 — §2.C 계단식 신호강도 매핑 사용
  exit_partial_frac_bands:
    - {min_strength: 70, max_strength: 80, partial_frac: 0.10}
    - {min_strength: 80, max_strength: 90, partial_frac: 0.20}
    - {min_strength: 90, max_strength: 100, partial_frac: 0.30}
tickers:
  "021240":
    thesis_id: coway_quality_dividend
    fundamental:
      roe_min: 15.0
      payout_min: null
      buyback_done: false
    valuation:
      pbr_max: 2.5
      premium_to_fair_pct: null
```

과열(`overheat`)은 종목 파일 또는 상위 센티먼트/레짐 훅 — **자동 매매 금지**, 평가 입력만.

### 3.1b 데이터 유지 부담 (운영 병목 — 설계보다 우선 명시)

TP-A/B는 **종목별 목표가 파일이 채워져 있을 때만** 의미가 있다. 로직만 완성되고 YAML이 비면 아무 일도 안 일어난다.

| 규칙 | 내용 |
|------|------|
| 소유 | **사람(원장/운용)** 이 `kr_alpha_exit_targets.yaml`을 채우고 갱신. 파이프라인·Cursor가 목표치를 추정·자동 기입하지 않음 |
| MVP 범위 | **현재 보유 kr_alpha**(+ Park 후보)만. 유니버스 전체 선제 채움 금지 |
| 빈 목표 | 해당 ticker에 `fundamental`/`valuation` 목표가 없으면 `assess_take_profit` → `Hold` / `exit_leg=NONE` (에러·강제 Trim 없음). 보드에 `targets_missing` 표시 권장 |
| 갱신 주기 | 편입·테제 변경 시 즉시; 그 외 **분기 1회** 재확인(권고). 시스템 강제 스케줄 없음 |
| 구현 착수 | 코드 1차(가시성)는 **스키마+평가+미기입 표시**까지. “전 종목 목표 채움”은 승인 조건이 **아님** — 운영자가 점진 기입 |

### 3.1c 다른 “언제 줄이나” 경로와의 관계 (4트랙 정합)

이미 공존하는 축:

| 경로 | 성격 | “줄이는” 근거 |
|------|------|----------------|
| `exit_engine` Soft/Hard/Tier | 연구 퇴출 | 나쁨(점수·게이트·모멘텀 붕괴) |
| `holdings_review` | 라이브 점수 | 저스코어 TRIM/REPLACE_CANDIDATE |
| `alpha_v2` shadow `trim_watch` | Review-only 수급·가격 | `profit≥15%` + 수급(flow) 약화 등 ([`trigger_engine._trim_watch_eligible`](../src/alpha_v2/trigger_engine.py)) |
| **TP-A/B (본 SPEC)** | Review-only 테제 목표 | 펀더멘털·밸류 **목표가 도달** |

**결정 (본 SPEC):** TP-A/B는 alpha_v2 shadow `trim_watch`를 **흡수·대체하지 않는다. 공존한다.**

- 이유: shadow는 **가격 수익+수급 전술** 신호이고, TP는 **종목 테제 목표가** 신호다. satellite_cap 삼중 정의와 달리 축이 다르다.
- 표시: 보드/리포트에서 출처 태그를 분리 (`trim:TP-*` vs `trim:v2_shadow` vs `trim:score` vs `trim:exit_engine`). 한 카드에 합쳐 “한 줄 Trim”으로만 보여 출처를 지우지 말 것.
- **금지:** 1차 구현에서 v2 shadow 규칙을 TP-B로 재작성하거나, shadow 엔진을 끄거나, 두 신호를 OR로 한 실행 액션에 합치는 것.
- **후속(P1+):** UI상 “Trim 사유 통합 뷰”만 검토. 엔진 병합은 별도 승인. 이중 `exit_engine`↔`holdings_review` 통합도 본 SPEC 밖(기존 P1).

### 3.2 함수 시그니처

```python
@dataclass(frozen=True)
class TakeProfitAssessment:
    fund_hit: bool
    val_hit: bool
    signal_strength: float        # 0~100, 퍼센타일 기반 — "확률"/"승률" 아님
    strength_components: str      # 예: "TP-B 88(밸류) / TP-A 66.7(펀더멘털 2/3)"
    momentum_score: float | None  # 참고용 — VAL/BOTH 카운터체크 입력
    momentum_override_applied: bool  # §2.D 하향 적용 여부
    suggested_action: Literal["Hold", "Trim", "Exit-review"]
    exit_leg: Literal["NONE", "FUND", "VAL", "BOTH"]
    partial_frac: float           # signal_strength를 §2.C 표에 매핑 후 §2.D 카운터체크 반영 — 고정값 아님
    rationale: str

def assess_take_profit(
    ticker: str,
    *,
    fundamentals: dict,
    prices: dict,
    targets: dict,
    momentum_score: float | None = None,
    overheat: bool | None = None,
) -> TakeProfitAssessment: ...

def resolve_partial_frac_from_strength(
    signal_strength: float,
    bands: list[dict],  # exit_partial_frac_bands
) -> float:
    """계단식 매핑. 구간 밖(강도<최소 구간)이면 0.0(Hold)."""
    ...

def apply_momentum_counter_check(
    partial_frac: float,
    *,
    exit_leg: str,
    momentum_score: float | None,
    bands: list[dict],
    momentum_override_threshold: float = 70.0,
) -> tuple[float, bool]:
    """exit_leg in {VAL,BOTH} and momentum_score>=threshold면 한 단계 하향.
    반환: (조정된 partial_frac, momentum_override_applied)"""
    ...

@dataclass(frozen=True)
class ThesisBreakAssessment:
    active: bool
    rule_id: Literal["TB-01", "TB-02", "TB-03", "NONE"]
    suggested_action: Literal["Hold", "Trim", "Exit", "Exit-review", "Demote-review"]
    rationale: str

def assess_thesis_break(
    ticker: str,
    *,
    flags: dict,          # thesis_damage, policy_retreat, accounting_issue, ...
    catalyst: dict | None = None,
) -> ThesisBreakAssessment: ...
```

### 3.3 연동 위치 (구현 단계 · 이번엔 명세만)

1. `assess_*` 순수 함수 + 단위 테스트  
2. `alpha_signal_board`에 `trim_trigger` / `exit_trigger` 문구·`exit_leg` 컬럼 (표시)  
3. (선택) `exit_engine`에 `take_profit` / `thesis_break` 블록 — Soft/Hard와 ID 충돌 없게 `TP-*` / `TB-*`  
4. **하지 않음:** `propose_target_changes` 자동 반영, executable trim 강제

## 4. 절대 금지

- `target_portfolio.csv` / 승인 포트 **자동** 감액·편출
- Soft S01–S07·Hard H01–H08 의미 변경으로 익절을 우회 구현
- CECS `allocate_weights`를 live target에 연결
- policy_cap / execution_scope / Actual Buy 로직 변경
- 네이버·FASTJUSIK 신규 스크래핑
- `signal_strength`를 "확률"·"승률"·"성공확률"·"적중률" 등 통계적 확률을 뜻하는 표현으로 라벨링 — 보드·리포트·rationale 어디서도 금지. "신호강도"/"스코어"로만 표기
- `exit_partial_frac_bands` 구간·비율을 실제 과거 성과 데이터로 calibration했다고 표시 — 검증 전까지는 "미검증 초기값"임을 항상 병기

## 5. 이번 SPEC 밖 (후속)

| 항목 | 처리 |
|------|------|
| C-8 히스테리시스 · C-9 상대 25–30% 밴드 | **연기** — 고정비중 전환 결정과 동일 명세 |
| P1 이중 트랙 통합 (`exit_engine`↔`holdings_review`) | 별도 |
| yaml `soft_to_replace_days` / streak 실제화 | 별도 |
| 종목별 목표가 대량 채움 | 사람이 YAML 유지; 자동화는 P1+ |

## 6. 검증 요청 (구현 시)

1. TP-A only → `Trim`, `exit_leg=FUND`; Replace/Exit 아님  
2. TP-B only → `Trim`, `exit_leg=VAL`  
3. 둘 다 → `Trim` 또는 `Exit-review`, `BOTH`  
4. `THESIS_BREAK` + overweight → **Exit** 우선 (익절 Trim보다 앞) — 기존 보드 테스트 정합  
5. `assess_*` 결과가 target CSV를 쓰지 않음 (파일 mtime/가드)  
6. AC / scope / Actual Buy 회귀 없음  
7. `resolve_partial_frac_from_strength`: 강도 75→10%, 85→20%, 95→30%, 65(구간 미만)→0.0/Hold — 경계값(70/80/90 정확히) 포함 케이스  
8. 출력 문자열·필드 어디에도 "확률"·"승률"·"성공확률" 문자열이 없는지 정적 검사(assert)  
9. `apply_momentum_counter_check`: exit_leg=VAL·momentum_score=82(≥70) → 밴드 한 단계 하향, `momentum_override_applied=True`; exit_leg=FUND(TP-A only)면 momentum 무관하게 하향 없음; momentum_score=None이면 하향 없음(안전한 기본값)  
10. 하향 적용 시 `rationale`에 근거 문자열 포함 여부 확인

## 7. 구현 착수 조건

- **실행 승인 완료 (2026-07-15, 원장)** — §2.C·§2.D 포함 최종본 승인. Cursor 코드 착수 가능.
- 1차는 순수 평가 + 보드 표시 + `targets_missing` / 출처 태그 (가시성) — 실행·target 반영은 명시 승인 후에만  
- 목표가 YAML 전량 채움·v2 shadow 폐기는 **착수 조건이 아님**
- 구현 순서: (1) `assess_take_profit`/`assess_thesis_break`/`resolve_partial_frac_from_strength`/`apply_momentum_counter_check` 순수 함수 + 단위 테스트 → (2) `alpha_signal_board` 표시(trim_trigger·exit_leg·출처 태그·targets_missing) → (3) `kr_alpha_exit_targets.yaml` 스키마 파일 생성(빈 상태로 시작)
- 완료 후 `docs/EXIT_TAKEPROFIT_THESIS_RESULT.md`로 구현 결과 보고 (기존 세션 패턴과 동일 — Claude 독립 검증 예정)
