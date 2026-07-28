# 코드베이스 정리 0~2단계 — 죽은 코드·shadow 서브시스템 격리 (명세서)

> 배경: "근본적 재검토" 논의 결과, 314개 파일·73,856줄 중 상당 부분이 review-only shadow 실험이거나 아예 호출되지 않는 죽은 코드로 확인됨. git 커밋이 3개뿐이라 뭔가 잘못됐을 때 되돌리기 어려운 상태 — 이번 정리로 롤백 가능한 체크포인트를 만드는 것도 목적.
> 원칙: **삭제 아니고 격리(archive/).** 전략(kr_alpha 존속 여부)은 이번 범위 밖 — `src/alpha/`(kr_alpha 코어, 39개), 오늘 만든 `take_profit_thesis.py` 등은 **건드리지 않음**. 매 단계마다 실행 확인 + git 커밋 1개씩.

## 0. 공통 절차 (각 단계 공통 적용)

각 단계마다:
1. **이동 전**: 해당 디렉토리를 실제로 참조하는 곳 전수 grep (`grep -rl "from src.<dir>\|import src.<dir>"`) — 아래 조사 결과 기반이지만 재확인 필수
2. **이동**: `git mv src/<dir> archive/<YYYYMMDD>_<dir>` (git mv로 이력 보존), 대응 테스트도 `git mv tests/test_<관련>.py archive/<YYYYMMDD>_tests/`
3. **끊어진 참조 처리**: 이동 후 남은 참조(아래 "잔여 참조 처리" 항목)를 개별적으로 안전하게 제거/우회 — 삭제가 아니라 "shadow 비활성화" 방식 선호(예: try/except ImportError로 감싸서 없으면 조용히 스킵)
4. **검증**: `python -m src.main`(또는 `scripts/daily_pipeline.py`) 정상 종료(exit 0) 확인, `pytest` 전체 재실행해 이동 안 한 나머지 테스트 전부 pass 확인
5. **커밋**: `git commit -m "cleanup: archive <dir> (phase N)"` — 단계별로 별도 커밋, 한꺼번에 묶지 않음

## 1. 0단계 — `src/alpha_v0_2/` 격리 (12개 파일)

- **조사 결과**: 파이프라인 어디서도 실제 호출 안 됨. `src/alpha_shadow_policy.py`와 `src/alpha_v0_2/pipeline.py`(자기 자신) 정도만 참조.
- **잔여 참조 처리**: `src/alpha_shadow_policy.py`는 `full_pipeline.py`/`report/export_daily_brief.py`/`validation/ai_export.py`에서 **실제로 쓰이므로 archive 대상 아님** — 이 파일 내부에서 `alpha_v0_2`를 import하는 라인만 찾아서 없어도 안전하게 동작하도록 처리(예: try/except 또는 조건부 스킵). `alpha_shadow_policy.py` 자체의 공개 함수 시그니처·반환값은 유지 — 호출부(`full_pipeline.py` 등)가 깨지지 않게.
- **가장 안전한 단계** — 리스크 거의 없음.

## 2. 1단계 — `src/value_list/`(하케다카 딥리서치) 격리 (35개 파일)

- **조사 결과**: `alpha/alpha_pipeline.py`, `alpha/portfolio_selector.py`, `data_refresh/tier_h.py`, `full_pipeline.py`, `report/export_daily_brief.py`, `report_writer.py`, `runtime/post_decision_artifacts.py`에서 실제로 호출됨(매일 파이프라인에서 돎). `scripts/run_hakedaka_*.py` 6개 스크립트도 이 모듈 사용.
- **영향**: 이걸 격리하면 daily_report.md의 "Hakedaka Coverage/Catalyst/NAV/Manual Verification/Forward Return" 등 10여 개 섹션이 통째로 사라짐 — 전부 review-only였으므로 게이트·매매 로직 영향 없음.
- **처리 방법**: 위 7개 호출부 파일에서 `value_list` import·호출 부분을 **주석 처리 또는 feature flag(`ENABLE_HAKEDAKA=False`)로 감싸서 비활성화** — 코드 완전 삭제보다 안전(나중에 다시 켜고 싶으면 flag만 바꾸면 됨). `scripts/run_hakedaka_*.py` 6개는 archive로 함께 이동(독립 실행 스크립트라 파이프라인 필수 경로 아님).
- **검증 포인트**: daily_pipeline 정상 종료 + 남은 리포트에 "하케다카" 관련 섹션이 자연스럽게 빠져 있는지(에러로 죽지 않고 그냥 안 보이는지) 확인.

## 3. 2단계 — `src/alpha_v2/` + `src/alpha_flow/` 격리 (26개 파일)

- **조사 결과**: `alpha/alpha_pipeline.py`, `alpha_flow/flow_service.py`(자기 자신), `alpha_shadow_policy.py`, `full_pipeline.py`, `report_writer.py`, `runtime/pipeline_runner.py`, `runtime/run_mode_contract.py`, `validation/ai_export.py`에서 호출.
- **영향**: daily_report.md의 "Alpha v2 Shadow" 섹션(KOSDAQ 커버리지, Trim Watch, flow 신호 등) 전체가 사라짐 — 역시 게이트 미관여 확인됨(`target write: False` 고정, `Actual Buy Allowed=0` 무관).
- **처리 방법**: 1단계와 동일 패턴 — feature flag(`ENABLE_ALPHA_V2=False`)로 감싸서 비활성화, 호출부 시그니처는 유지.
- **`alpha_shadow_policy.py`와의 관계**: 이 파일이 v0.2뿐 아니라 v2 게이팅도 겸하고 있다면, 0단계에서 손댄 부분과 이번 처리가 충돌하지 않는지 반드시 재확인.

## 4. 절대 금지 (전 단계 공통)

- `src/alpha/`(kr_alpha 코어), `src/compass/`, `src/validation/`(acceptance/policy_cap 등), `src/exposure/`, `src/execution_scope.py`, `data/target_portfolio.csv` 관련 로직 — **이번 범위 절대 아님**
- 오늘 만든 `take_profit_thesis.py`, `exit_target_worksheet.py` 및 관련 UI — 이번 범위 아님 (전략 결정 이후 별도 처리)
- 실제 파일 **삭제 금지** — 전부 `git mv`로 archive 이동만. 되돌릴 수 있어야 함
- 각 단계 검증 실패 시 다음 단계로 넘어가지 말고 그 단계에서 멈추고 보고

## 5. 검증 요청 (단계별)

각 단계 완료 후:
1. `python -m src.main` 또는 daily_pipeline exit code 0
2. 이동 안 한 나머지 `pytest` 전부 pass (몇 개 pass/fail인지 카운트 보고)
3. `git log --oneline`에 해당 단계 커밋 1개 생성 확인
4. archive로 옮긴 파일 목록 전체 나열 (몇 개 옮겼는지)
5. 잔여 참조(끊어진 import) 없는지 `python -c "import src.main"` 등으로 재확인
