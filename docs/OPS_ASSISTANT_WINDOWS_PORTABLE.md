# 코스피 알파 스크리너 — Windows 이식 (포맷·다른 PC)

> **제품 포지션:** 규칙 기반 **스크리너** (자동매매·증권사 API 아님)  
> **목표:** 포맷하거나 다른 Windows PC에서도 같은 장부·승인 상태로 다시 켠다.  
> **코드 루트:** `C:\Cursor\investment\investment-alpha-screener`  
> **설치형 패키징:** [`V3_WINDOWS_PACKAGING.md`](V3_WINDOWS_PACKAGING.md)

---

## 한 줄

이사할 때 **공구함(프로그램) + 장부(data 백업) + 열쇠(API 키)** 를 챙기면 됩니다.

---

## 포맷 전 (백업)

### UI
1. `투자나침반.bat` → **[1] UI**
2. **설정 › 이식·백업**
3. **백업 zip 생성** → USB/클라우드에 저장  
   - API 키 포함 시: USB 암호화, 공유 금지

### 또는 bat
- `투자나침반.bat` → **[4] Backup zip**  
- 결과: `data\local\backups\saa_ops_assistant_backup_*.zip`

### 또는 CLI
```text
python scripts/make_ops_backup.py
python scripts/make_ops_backup.py --with-secrets
```

zip에 들어가는 핵심: 보유·목표가·승인·게이트 JSON, 스코어 컷 설정, 가격 캐시(선택), API 키(선택).

---

## 포맷 후 / 다른 PC (복원)

**가장 쉬움:** `PC이사.bat` → 안내 파일대로 폴더 복사.

1. 새 PC에 **Python 3.11+** 설치 (PATH 추가)
2. 프로그램 폴더 복사 또는 Git clone
3. `투자나침반.bat` — `.venv`가 없거나 깨져 있으면 자동 수리
4. 장부가 비어 있으면 **설정 › 이식·백업** 또는 `장부_가져오기.bat`
5. **설정 › API 키** 확인 (secrets를 zip에 안 넣었다면 다시 입력)
6. 확인 › ① **정량 전체 갱신** (캐시를 안 넣었거나 오래됐을 때)

---

## 상품화 범위 (이번 MVP)

| 포함 | 미포함 |
|------|--------|
| 스크리너 브랜드·첫 실행 안내 | 앱스토어·Mac·클라우드 SaaS |
| 백업/복원 zip | 증권사 자동매매 |
| Windows bat 이식 | “누구나 클릭만” 제로설정 |

판매 관점에서는 **개인/소수 운용자용 워크플로 도구**입니다. 만능 투자앱이 아닙니다.

---

## 불변 (복원해도 유지)

- `proposal_mode: pure_qvm`
- `target_portfolio.csv`는 사람 승인만 (백업 복원은 본인 장부 복구)
- CECS·하케다카·수급 = Review-only
- FASTJUSIK 스크래핑 금지
