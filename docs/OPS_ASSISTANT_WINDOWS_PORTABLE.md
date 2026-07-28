# SAA 알파 운용 비서 — Windows 이식 (포맷·다른 PC)

> **제품 포지션:** 규칙 있는 **개인 운용 비서** (자동매매·증권사 API 아님)  
> **목표:** 포맷하거나 다른 Windows PC에서도 같은 장부·승인 상태로 다시 켠다.  
> **코드 루트:** `C:\Cursor\investment-saa-alpha-v2`

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

zip에 들어가는 핵심: `target_portfolio.csv`, `kr_alpha_exit_targets.yaml`, 주간/월간 정성 JSON, CECS CSV, positions, 런타임 등.

---

## 포맷 후 / 다른 PC (복원)

1. **Python 3.11+** 설치 (PATH 추가)
2. 이 저장소 폴더 복사 또는 Git clone
3. `투자나침반.bat` → **[2] Install**
4. **설정 › 이식·백업**에서 zip 업로드·**복원 실행**  
   또는  
   `python scripts/restore_ops_backup.py path\to\backup.zip`
5. **설정 › API 키** 확인 (secrets를 zip에 안 넣었다면 다시 입력)
6. 결재함에서 **정량 전체 갱신** (캐시를 안 넣었거나 오래됐을 때)

---

## 상품화 범위 (이번 MVP)

| 포함 | 미포함 |
|------|--------|
| 운용 비서 브랜드·첫 실행 안내 | 앱스토어·Mac·클라우드 SaaS |
| 백업/복원 zip | 증권사 자동매매 |
| Windows bat 이식 | “누구나 클릭만” 제로설정 |

판매 관점에서는 **개인/소수 운용자용 워크플로 도구**입니다. 만능 투자앱이 아닙니다.

---

## 불변 (복원해도 유지)

- `proposal_mode: pure_qvm`
- `target_portfolio.csv`는 사람 승인만 (백업 복원은 본인 장부 복구)
- CECS·하케다카·수급 = Review-only
- FASTJUSIK 스크래핑 금지
