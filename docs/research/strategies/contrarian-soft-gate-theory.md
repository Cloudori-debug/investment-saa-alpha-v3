# 역발상 Soft 게이트 이론 — Fear≠매수 · 관찰·분할

> **상태:** active · **운영 Soft** (매수 엔진 아님)  
> **프로그램:** 일반계좌 Soft · 유니버스 게이트 · Fear Soft · 기업해부  
> **갱신:** 2026-11-12  
> **SoT:** [`ACCOUNT_SPLIT_OPS_SPEC.md`](../../ACCOUNT_SPLIT_OPS_SPEC.md) · [`FEAR_GREED_SOFT_SPEC.md`](../../FEAR_GREED_SOFT_SPEC.md)

## 1. 한 줄

우리 역발상은 **「공포니까 산다」가 아니라, 「싸 보이는 것을 공시·현금으로 검증한 뒤 나눠 산다」**이다. Fear는 **허가증이 아니라 사이즈 브레이크**다.

## 2. 두 종류의 역발상 (구분)

| 유형 | 뜻 | 우리 프로그램 |
|------|-----|----------------|
| **A. 심리·타이밍 역발상** | 극단 공포·MDD만으로 매수 | **채택 안 함** · Fear→매수 FAIL |
| **B. 가치·본질 역발상 Soft** | 할인·저P·논리·해부 후 분할 | **채택** · 일반 Soft 게이트 |

정발상(단기 Soft·듀얼)과 **장부가 다름**. 합산 주문·한 점수로 섞지 않음.

## 3. 이론 명제

### P1 — Fear는 충분조건이 아니다
- 문헌·영상 Soft: 공포 구간 매수가 **아무 날 매수보다 낫지 않을 수 있음  
  ([`youtube-2026-fear-vs-rate-path.md`](youtube-2026-fear-vs-rate-path.md)).
- 반등의 **지속**은 금리·물가 **경로**가 가름 · 지수 레벨만으로 우위 단정 금지.
- **정리:** `Fear_hot ⇏ Soft_buy`. Fear만으로 게이트 **통과 불가**.

### P2 — Fear는 필요조건도 아니다
- Soft∩논리·해부 PASS여도 Fear=ok일 수 있음.
- Fear는 **매수를 켜는 스위치가 아니라**, hot일 때 **사이즈↓·보류**를 거는 브레이크.
- **정리:** Soft 매수 Review의 **허가**는 논리·해부·분할·계좌에서 오고, Fear는 **거부·축소**만 한다.

### P3 — 역발상 Soft = AND 게이트 (약한 역발상)
일반계좌 Soft 매수 Review:

```text
Buy_Review ⇔
  저P티어후보(≠매수단정)
  ∧ Soft∩(논리∨본질)
  ∧ 해부≠FAIL  (PASS 권고 · HOLD=보류)
  ∧ ¬Fear를_매수트리거로_씀
  ∧ 오늘매수% ≤ 33
  ∧ Soft자금 ⊂ 일반계좌
```

하나라도 FAIL → **대기·파킹** (매수 배지 없음).  
HOLD 다수 → **보류** (아직 사라는 뜻이 아님).

### P4 — 파킹은 포지션이다
- Soft 공집합·게이트 실패 시 단기채 파킹 = **공중 대기 금지** (알파북 운영).
- “못 샀다”가 아니라 **현금·시간 확보** (마지막 매수자·고금리 Soft와 정합).

### P5 — System 1 vs System 2
- System 1: 공포·반등 가용성 → “지금 안 사면 놓친다”.
- System 2: 배지·33%·해부·계좌 이분 ([`youtube-2026-kahneman-fast-slow.md`](youtube-2026-kahneman-fast-slow.md)).
- **정리:** 게이트는 System 2 매뉴얼 · Fear hot은 System 1 경보.

## 4. Fear 게이트 상태표

| 입력 | 게이트 | 행동 Soft |
|------|--------|-----------|
| `fear_as_buy_signal=True` | **FAIL** | 매수 금지 · 대기·파킹 |
| tone=`hot` · 트리거 아님 | **HOLD** | 사이즈↓ · 신규 보수 |
| tone=`ok`/`watch` | **PASS** (자세만) | 다른 게이트가 허가할 때만 Review |
| 미수집 | **HOLD** | 매수 트리거로 쓰지 않음 |

코드: `build_contrarian_gate_steps` · `fear` 스텝  
([`account_ops_checklist.py`](../../../alpha_system/ui/services/account_ops_checklist.py))

## 5. 정발상과의 직교

| | 정발상 | 역발상 Soft (우리) |
|--|--------|-------------------|
| 신호 | 모멘텀·듀얼 | 논리·해부·분할 |
| Fear | 시그널 비가산 | 브레이크만 |
| 계좌 Soft | 듀얼→연금·ISA | Soft→일반 |
| 실패 | 픽 없음→파킹 | 게이트 FAIL→파킹 |

## 6. 보조지표 (한계를 숫자로 드러냄)

코드: [`contrarian_soft_aux.py`](../../../alpha_system/ui/services/contrarian_soft_aux.py) · UI 유니버스 게이트 아래.

| 지표 | 정의 | 읽는 법 |
|------|------|---------|
| **게이트 역할** | 허가 / 보류 / 금지 | **≠수익·≠자동매수** 문구 고정 |
| **게이트 채워짐 %** | AND 스텝 중 PASS 비율 | 체크리스트 완성도 · 알파 아님 |
| **Fear 가용률 %** | 가용다리/(가용+미수집) | CNN 원본 신뢰도와 분리 · 낮으면 근사만 |
| **증빙 품질 Soft** | 해부·논리·U/blocker Soft | 사람 의존을 점수화 · QVM 비가산 |
| **사람위험 플래그** | 허가인데 증빙 얇음·HOLD·Fear 희소 | 재확인 권고 |

**정리:** 한계를 숨기지 않고 **보조미터로 표시**한다. Soft 순위·target에 넣지 않는다.

## 7. 금지 (이론 → 운영)

- Fear Soft → QVM·target·듀얼 Executable 가산  
- “극단 공포 = 자동 매수1”  
- 저P 관찰 풀 = Soft 장부  
- 원금메우기·하루 100%로 게이트 우회  
- 연금 예산으로 Soft 채워 역발상 “완성” 위장  
- 보조지표를 Soft 점수·매수 트리거로 오용  

## 8. 한계 (남기는 것)

- 학술 contrarian premium 한국 Soft **미증명** — 보조지표도 증명 대체 아님.  
- 증빙 Soft는 해부 JSON·U 입력 품질에 좌우.  
- Review-only · 사람 HTS.
