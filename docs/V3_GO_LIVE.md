# SAA 알파 v3 — 개인 운용 상용 (Go-Live) 체크리스트

> **범위:** 본인 PC · Review-only 실투자 보조 (**A단계**)  
> **비범위:** 다수 사용자 SaaS · 자동매매 · 앱스토어  
> **실행:** [`V3_DEPLOY.md`](V3_DEPLOY.md) · **장부 이식:** [`OPS_ASSISTANT_WINDOWS_PORTABLE.md`](OPS_ASSISTANT_WINDOWS_PORTABLE.md)  
> **운용 태그:** `v3.0.0-ops` (이 태그로만 “상용 운용” 고정 권장)

---

## 0. 불변 (매번 확인)

- [ ] `proposal_mode: pure_qvm`
- [ ] `target_portfolio.csv` — UI/갱신이 **자동 기입하지 않음** (사람만)
- [ ] ETF Executable / kr_alpha·하케다카·수급 = **Review-only** (주문 API 없음)
- [ ] FASTJUSIK 금지 — PyKRX·DART만
- [ ] Core에서 `score_m` 제외
- [ ] 홈「월 리밸」= Review-only

자동화 점검:

```powershell
cd C:\Cursor\investment-saa-alpha-v3
python scripts/go_live_check.py
```

---

## 1. 주간 운용 루틴 (권장: 주말 또는 월 리밸 전)

| # | 할 일 | 어디서 |
|---|--------|--------|
| 1 | 장부 백업 zip | 아래 §2 또는 설정›이식·백업 |
| 2 | 운용 데이터 갱신 (시세·펀더) | 홈 / 결재함 |
| 3 | 후보·모멘텀 보드 확인 | 홈 |
| 4 | 실보유 ↔ 후보 대조 | 보유 › 실보유 입력 |
| 5 | 목표가 재검증 경고 처리 | 보유 / `kr_alpha_exit_targets.yaml` |
| 6 | 종목별 안내(S0/S1/S2a/S근접) — **사람 집행** | 보유 |
| 7 | 월 리밸 보드 (해당 주면) | 홈 (접힌 섹션) |

### 신호 해석 (오해 방지)

| 신호 | 의미 | 주의 |
|------|------|------|
| 순위만 ↓ | **유지** | 교체 아님 |
| S2a 제안 탈락 | 전량 **권고** | 사람만 집행 |
| S1 목표가 도달 | 절반 환금 권고 | |
| S2c | **도달일**(`target_hit_as_of`) 후 N주 | 승인일만으로는 전량 안 됨 |
| qty=0 등록 | 코드만 장부 | 비중·`load_positions`에서는 제외 |

목표가에 **처음 도달**한 날 yaml에 `target_hit_as_of: YYYY-MM-DD`를 적어 두면 S2c 시계가 올바르게 돌아갑니다.

---

## 2. 백업 (필수)

### 원클릭

```powershell
cd C:\Cursor\investment-saa-alpha-v3
.\go_live_backup.bat
```

또는:

```powershell
python scripts/make_ops_backup.py
```

결과: `data\local\backups\saa_ops_assistant_backup_*.zip`  
→ USB / 암호화 클라우드에 복사.

API 키 포함 시(비권장·USB 암호화):

```powershell
python scripts/make_ops_backup.py --with-secrets
```

### 반드시 포함되는 핵심 장부

| 파일 | 비고 |
|------|------|
| `data/positions.csv` | git 비추적 · 로컬만 |
| `data/target_portfolio.csv` | 사람 승인 목표 |
| `data/kr_alpha_exit_targets.yaml` | 익절 SoT |
| `data/alpha_dashboard_runtime.json` | 런타임 |
| CECS / 주간 정성 JSON 등 | 팩에 포함 |

복원: `python scripts/restore_ops_backup.py path\to\backup.zip`

---

## 3. 배포 전 스모크 (태그/업데이트 직전)

```powershell
cd C:\Cursor\investment-saa-alpha-v3
python scripts/go_live_check.py --pytest
.\투자나침반.bat
```

- [ ] UI가 `http://localhost:8501` 기동
- [ ] 홈에 오늘 할 일 · 후보 표시
- [ ] 보유 › 저장된 알파 / 종목별 안내 표시
- [ ] 자동매매·target 자동기입 버튼 없음 재확인

---

## 4. 버전 고정

```powershell
git fetch origin
git checkout v3.0.0-ops
# 또는 main을 쓰되, 문제 시 태그로 롤백
```

새 기능을 main에 넣은 뒤 안정화되면 `v3.0.1-ops` 등으로 재태깅.

---

## 5. Go-Live 완료 조건 (A단계 Done)

- [ ] §0 불변 통과 (`go_live_check.py` OK)
- [ ] §2 백업 zip 1회 이상 생성·외부 보관 확인
- [ ] §3 스모크 + UI 기동 OK
- [ ] 주간 루틴을 한 번 이상 실제 수행
- [ ] `target_portfolio.csv` / exit YAML 변경은 **사람 승인**만 했다는 인식

이후 **B단계**(설치형·신선도 게이트·감사 UX)는 별도 작업. SaaS(C)는 헌장 밖.
