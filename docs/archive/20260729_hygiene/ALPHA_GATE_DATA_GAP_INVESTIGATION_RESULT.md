# alpha_gate PIT 데이터 갭 조사 결과

> as_of 데이터 기준: `2026-07-10` · 조사일: 2026-07-11  
> 명세: `docs/ALPHA_GATE_DATA_GAP_INVESTIGATION_SPEC.md`  
> 정책 캡 / dry-run / throttle / auto_trading 가드: **미변경**

## 1. 티커 특정 · 분류

| 티커 | 종목명 | 분류 | 원인 | 조치 | 재검증 결과 |
|---|---|---|---|---|---|
| 900140 | 엘브이엠씨홀딩스 | **FIXABLE** | 정상 거래 종목인데 `prices.csv` 시세 누락 → `missing_price` | PyKRX로 시세 재수집·merge | `missing_price` **0건** |
| 950210 | 프레스티지바이오파마 | **FIXABLE** | 동일 (시세 누락) | PyKRX로 시세 재수집·merge | `missing_price` **0건** |
| 999004 | (유니버스 없음) | **FIXABLE** (데이터 오염) | `fundamentals.csv` 고아 행. 유니버스 미존재 + `report_date` stale → `stale_data` 카운트만 올림 | `fundamentals.csv`에서 해당 행 삭제 | `stale_data` **0건** |
| 415640 | KB발해인프라 | **EXPECTED** | 인프라 집합투자기구. 시세는 있으나 일반 기업 재무 스키마(`fundamentals.csv`) 미수록 → `missing_fundamentals` | 코드/정책 변경 없음. 정당한 스크리닝 제외로 문서화 | 제외 유지 (2건 중 1) |
| 088980 | 맥쿼리인프라 | **EXPECTED** | 동일 (인프라펀드/MKIF). `is_reit=false`로 유니버스는 통과하나 재무 미수록 | 동일 | 제외 유지 (2건 중 1) |

### 요약 카운트

| 규칙 | 조사 전 | 조치 후 |
|---|---|---|
| `missing_price` | 2 | **0** |
| `stale_data` | 1 | **0** |
| `missing_fundamentals` | 2 | **2** (EXPECTED) |

`apply_data_gate` 단독 판정: **GREEN** (limitations 없음).  
EXPECTED 2건은 유니버스 통과 후 재무 없음으로만 제외되며, 게이트 YELLOW 임계(`excluded > usable*0.5`)를 넘기지 않음.

## 2. `input_validation_gate` 근거

`src/validators.validate_inputs` → 현재 **YELLOW**.

- 원인: 보유/목표 비중 `target outside min/max band` 경고 다수 (예: 030200, 021240, 005830 …).
- **policy_cap과 무관한 독립 입력 검증**.
- `portfolio_gate`는 여기에 `regime=YELLOW_STABLE` 파생이 더해져 YELLOW가 되는 구조 (`gate_detail_builders.build_portfolio_gate_detail`).
- 명세대로 policy_cap 로직은 수정하지 않음.

## 3. 수정 후 alpha_gate / data_gate 예상

| 레이어 | 예상 | 비고 |
|---|---|---|
| PIT/`apply_data_gate` | GREEN 유지 가능 | FIXABLE 해소 후 |
| `alpha_gate` | 개선 가능 (YELLOW→GREEN 후보) | 전체 파이프라인 재실행 시 확정 |
| `portfolio_gate` | **YELLOW 유지 가능** | `policy_cap_active` + `YELLOW_STABLE` (재평가 ~2026-09-24) |
| `data_gate` | **YELLOW 유지 가능** | portfolio∧alpha 합성 — 명세대로 예상된 결과 |
| Actual Buy Allowed | **0 유지** | 실행 게이트 미완화 |

전체 STANDARD 재실행은 이 조사에서 강제하지 않음. 로컬 필터 재현으로 FIXABLE 해소는 확인됨.

## 4. 하지 않은 것 (명세 금지 항목)

- `policy_cap_*`, BOK FSR 연동
- `execution_scope.py` 임계/권한 완화
- `core_deployment_throttle.py` 한도
- `execution_guards.py` auto_trading 우회

## 5. 선택 후속 (비긴급)

- 인프라펀드(415640, 088980)를 universe에서 `is_reit`/전용 유형으로 표시해 `reit` 제외 규칙에 태우면, `missing_fundamentals` 카운트도 0으로 정리 가능 (스크리닝 의도 명확화).
- `input_validation_gate` YELLOW의 min/max band 경고는 별도 목표비중 정리 이슈.
