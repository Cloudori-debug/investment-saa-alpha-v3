# Alpha Portfolio (CECS) — nested under investment-saa-alpha

규칙 기반 KOSPI 알파 스크리너 + 퇴출 검토

이 패키지는 monorepo `investment-saa-alpha/alpha_portfolio` 에 포함됩니다.
상위 프로젝트(나침반·게이트·승인)와 `target_draft.csv` 로 연결됩니다.

## 빠른 시작

```powershell
cd alpha_portfolio
pip install -e ".[data,dev]"

python -m src.collect_main --scope holdings
python -m src.main --kr-alpha-weight 31
python -m src.main --kr-alpha-weight 31 --collect
```

## KRX 로그인

- 환경변수 `KRX_ID`, `KRX_PW`
- 또는 상위 `../data/local/user_secrets.json`

## 출력

- `data/output/target_draft.csv` ← 상위 UI「알파 Target 승인」에서 가져옴
- `data/output/alpha_scores.csv`, `alpha_candidates.csv`, …
