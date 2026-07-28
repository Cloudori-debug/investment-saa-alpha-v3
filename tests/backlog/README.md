# Tests Backlog Index

P4b legacy failed tests는 **`docs/TEST_BACKLOG.md`** 에 분류·우선순위와 함께 기록합니다.

## 카테고리 디렉터리 (분류용)

| 디렉터리 | 카테고리 | 설명 |
|----------|----------|------|
| `profile_fixture_mismatch/` | profile_fixture_mismatch | SAA 프로필명·fixture 불일치 |
| `alpha_policy_fixture_stale/` | alpha_policy_fixture_stale | alpha pipeline expected·universe drift |
| `compass_expected_output_stale/` | compass_expected_output_stale | compass allocation expected 구식 |
| `pipeline_cache_output_changed/` | pipeline_cache_output_changed | run_mode/cache/authoritative 산출물 변화 |
| `external_data_dependency/` | external_data_dependency | live price·network·sample data 의존 |

각 디렉터리는 **향후** 해당 카테고리 테스트를 `@pytest.mark` 또는 skip 사유 파일로 옮길 때 사용합니다.  
현재는 문서 backlog만 운영하며, 테스트 로직·운용 정책은 변경하지 않습니다.

## 원칙

- P3 cache 최적화 PR과 **섞지 않음**
- 억지 pass 금지 — fixture/expected 분리 또는 갱신
- `Actual Buy Allowed`, gate threshold, policy cap, target_write **변경 금지**

See: `docs/TEST_BACKLOG.md`
