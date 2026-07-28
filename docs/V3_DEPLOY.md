# SAA 알파 v3 — 배포·일상 실행

**이 저장소 = 활성 v3.** 자동매매·증권사 API 없음. Review-only 실투자 보조.

## 일상 실행 (제품 진입)

| 진입 | 동작 |
|------|------|
| `투자나침반.bat` | `Start-Ops-Assistant.vbs` → UI |
| `Start-Ops-Assistant.vbs` | Streamlit 직접 |
| `run_ui_direct.bat` | `http://localhost:8501` |

```powershell
cd C:\Cursor\investment-saa-alpha-v3
.\투자나침반.bat
```

첫 화면에서 **실보유 입력**만 하면 바로 쓸 수 있습니다.  
DART 키·이식 zip·Go-Live 점검은 **나중에도 됩니다.**

첫 설치 시 `run_ui_direct.bat`가 `pip install -e ".[dev,ui,data]"`를 시도합니다.

## 불변 (배포 후에도 유지)

- `proposal_mode: pure_qvm`
- `target_portfolio.csv` — **사람만** 변경 (UI 자동기입 없음)
- ETF Executable / kr_alpha·하케다카·수급 = **Review-only**
- FASTJUSIK 금지 — KRX/PyKRX·DART
- Core 스코어에서 `score_m` 제외
- 홈「월 리밸」= Review-only

## 장부 파일 (백업 권장)

| 파일 | 비고 |
|------|------|
| `data/positions.csv` | gitignore — 로컬만 |
| `data/target_portfolio.csv` | 사람 승인 목표 |
| `data/kr_alpha_exit_targets.yaml` | 익절 목표가 SoT |
| `data/alpha_dashboard_runtime.json` | 런타임 플래그 |

이식: [`OPS_ASSISTANT_WINDOWS_PORTABLE.md`](OPS_ASSISTANT_WINDOWS_PORTABLE.md)

### (선택) 백업·업데이트 전 점검

필수 기능이 아닙니다. 포맷/이사·버전 올리기 전에만 쓰면 됩니다.

- [`V3_GO_LIVE.md`](V3_GO_LIVE.md)
- `go_live_backup.bat` / `python scripts/go_live_check.py`

## 원격

```text
https://github.com/Cloudori-debug/investment-saa-alpha-v3
```
