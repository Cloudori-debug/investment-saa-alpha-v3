# KRX 섹터 매핑 갱신 절차

> 소스: **KRX 공식 업종** (PyKRX) · GICS 미사용  
> 유니버스 B안 확정 (2026-07-16)

---

## 파일 구조

```
data/
  krx_sector_mapping.csv          # 자동 갱신 (PyKRX)
  krx_sector_mapping_manual.csv   # 수동 override (선택, 없으면 생성)
  krx_sector_taxonomy.yaml        # KRX 업종명 → sector_group
  sector_coverage_gate_pass.json  # gate_pass 커버리지 스냅샷 (리포트용)
```

**우선순위:** `manual` > `krx_official` > `name_infer` > `unknown`  
(`src/alpha/sector_mapping.py` `SOURCE_PRIORITY`)

---

## 정기 갱신 (권장: 월 1회 또는 KRX 업종 개편 시)

### 1. KRX 자격

- `data/user_secrets.yaml` 또는 환경변수 `KRX_ID` / `KRX_PW`
- FASTJUSIK 스크래핑 금지 — PyKRX만

### 2. 매핑 테이블 갱신

```powershell
cd C:\Cursor\investment-saa-alpha
python scripts/refresh_krx_sector_mapping.py
```

- 출력: `data/krx_sector_mapping.csv` (KOSPI+KOSDAQ 전 종목)
- **manual 파일은 덮어쓰지 않음**

### 3. (선택) screening / universe 반영

```powershell
python scripts/refresh_krx_sector_mapping.py --apply-screening --apply-universe
```

- `alpha_portfolio/data/input/screening_universe.csv` sector 컬럼 갱신
- `data/universe.csv` sector·industry 갱신

### 4. alpha_portfolio 파이프라인

파이프라인 실행 시 `sector_enrich.enrich_sectors()`가 **자동** 조인 — 별도 수동 병합 불필요.

```powershell
cd alpha_portfolio
python -m src.main --kr-alpha-weight 31
```

---

## 수동 override

신규 상장·매핑 누락·업종 재분류 이슈:

1. `data/krx_sector_mapping_manual.csv`에 1행 추가:

```csv
ticker,name,market,krx_sector,internal_sector,sector_group,source,asof,is_manual,notes
012510,더존비즈온,KOSPI,IT 서비스,IT 서비스,it_services,manual,2026-07-16,true,상장 직후 KRX 미반영
```

2. `internal_sector` = `krx_sector` (스코어링 peer 키)
3. `sector_group`은 `krx_sector_taxonomy.yaml`의 `krx_to_sector_group` 참고

---

## 커버리지 확인

```powershell
python scripts/refresh_krx_sector_mapping.py --apply-screening
# 마지막 줄 coverage: { gate_pass, unknown_pct, target_met, ... }
```

목표: **gate_pass unknown < 5%**

또는:

```powershell
cd alpha_portfolio
pytest tests/test_sector_enrich.py -q
```

---

## 스코어링 연동 규칙

| 필드 | 용도 |
|------|------|
| `sector` (= `krx_sector`) | Q/V percentile peer group |
| `sector_group` | 리포트·캡 (percentile 축 아님) |
| 표본 < 5 | `factors._sector_series` → 시장 fallback |

---

*관련 RESULT: [`ALPHA_UNIVERSE_B_SECTOR_META_RESULT.md`](ALPHA_UNIVERSE_B_SECTOR_META_RESULT.md)*
