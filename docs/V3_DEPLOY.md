# SAA 알파 v3 — 배포·일상 실행

**이 저장소 = 활성 v3.** 자동매매·증권사 API 없음. Review-only 실투자 보조.

## 일상 실행 (권장)

| 진입 | 동작 |
|------|------|
| `투자나침반.bat` | `Start-Ops-Assistant.vbs` → UI |
| `Start-Ops-Assistant.vbs` | Streamlit 직접 (CMD 최소화) |
| `run_ui_direct.bat` | `streamlit run alpha_dashboard.py` → `http://localhost:8501` |

```powershell
cd C:\Cursor\investment-saa-alpha-v3
.\투자나침반.bat
```

첫 설치 시 `run_ui_direct.bat`가 `pip install -e ".[dev,ui,data]"`를 시도합니다.

## 불변 (배포 후에도 유지)

- `proposal_mode: pure_qvm`
- `target_portfolio.csv` — **사람만** 변경 (UI 자동기입 없음)
- ETF Executable / kr_alpha·하케다카·수급 = **Review-only**
- FASTJUSIK 금지 — KRX/PyKRX·DART
- Core 스코어에서 `score_m` 제외
- 홈「월 리밸」= Review-only

## 장부 파일 (백업 필수)

| 파일 | 비고 |
|------|------|
| `data/positions.csv` | gitignore — 로컬만 |
| `data/target_portfolio.csv` | 사람 승인 목표 |
| `data/kr_alpha_exit_targets.yaml` | 익절 목표가 SoT |
| `data/alpha_dashboard_runtime.json` | 런타임 플래그 |

이식: [`OPS_ASSISTANT_WINDOWS_PORTABLE.md`](OPS_ASSISTANT_WINDOWS_PORTABLE.md)  
**개인 상용(Go-Live):** [`V3_GO_LIVE.md`](V3_GO_LIVE.md)

```powershell
python scripts/go_live_check.py
python scripts/go_live_check.py --pytest
.\go_live_backup.bat
```

## 원격

```text
https://github.com/Cloudori-debug/investment-saa-alpha-v3
```
