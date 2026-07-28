# kr_alpha min/max 밴드 불일치 — 조사 결과

> 명세: `docs/TARGET_MINMAX_BAND_MISMATCH_INVESTIGATION_SPEC.md`  
> 범위: **원인 규명 + 수정 방안 제안만** (코드/데이터 미수정)  
> 금지 준수: policy_cap·execution_scope·throttle·validators 완화·밴드 임의 확대 없음

---

## 1. 한 줄 결론

위반 6종목은 **의도된 8종목 과도기(INTENTIONAL_TRANSITION)가 아니라**,  
**(A) draft에서 가져온 min/max가 이후 `target_weight`만 예산 스케일될 때 같이 안 움직인 드리프트**와  
**(B) 071050 추가 시 `resolve_add_candidate` 기본 밴드(1.0/4.0)가 `compute_bands`로 재계산되지 않은 드리프트**다.  
→ **6종목 전부 `CONFIG_DRIFT_BUG`**.

---

## 2. min/max가 실제로 어디서 계산되는가

| 단계 | 파일·함수 | 동작 |
|------|-----------|------|
| **원천 산출** | `alpha_portfolio/src/target_matrix.py` → `compute_bands()` | `target ×` `config/target_matrix.yaml`의 tier별 `min_weight_ratio` / `max_weight_ratio`, Satellite는 `portfolio_max`·sleeve 캡 적용 |
| **정규화 시 동반 스케일** | 같은 파일 `build_target_draft()` normalize 블록 | `target`과 함께 **`min_weight`/`max_weight`도 동일 scale** |
| **draft → 운영 제안** | `src/alpha/target_draft_bridge.py` → `draft_row_to_target()` / `merge_target_draft()` | draft의 min/max를 **그대로 복사** |
| **알파 신규 추가** | `src/alpha/target_bridge.py` → `resolve_add_candidate()` / `propose_target_changes()` | 후보에 min/max 없으면 **기본 1.0 / 4.0** (`role`만 proposal에서 옴). `default_add_candidates()`는 `proposed_weight_pct`만 넣고 밴드는 안 넣음 |
| **예산 맞춤 (버그 지점)** | `propose_target_changes()` **및** `merge_target_draft()` 의 `kr_alpha_budget` 스케일 | **`target_weight`만 ×factor**, **min/max 미갱신** (동일 결함 2곳) |
| **나침반 분해 (정상 경로)** | `src/compass/target_decomposer.py` → `decompose_target_portfolio()` | 그룹 `final_target`/`min`/`max`에 맞춰 템플릿의 target·**min·max를 함께** 스케일 → `generated_target_portfolio.csv` |

검증용 대조 (아카이브 2026-07-11):

- `outputs/proposals/target_portfolio_proposed.csv` (approval_bridge): 071050 `5.55, 1.0, 4.0` → **상한 위반**
- `outputs/proposals/target_portfolio_proposal.csv` (compass): 같은 비중인데 071050 `5.55, 0.69, 4.58` → **밴드 내**
- live `data/target_portfolio.csv` / `user_target_portfolio.csv`: draft와 **동일 min 클러스터(5.36 / 1.38)** + 071050 기본밴드

즉 validator 경고는 “나침반이 틀려서”가 아니라 **승인된 user/operational target에 얼어 있는 밴드** 때문이다.

---

## 3. 071050(한국금융지주) — 언제·왜 8번째로 들어왔는가

### 확인된 사실

1. **연구/제안 쪽에서는 오래전부터 상위권**  
   - `alpha_portfolio_proposal` / candidates: satellite · B · WATCH · `proposed_weight_pct`≈8.0  
   - 섹터 매핑 수동 시드에 2026-07-02 포함 (`krx_sector_mapping_manual.csv`)
2. **CECS/draft 경로의 8번째와는 다름**  
   - `alpha_portfolio/data/output/target_draft.csv` (mtime 2026-07-09): 8행이지만 **036530 SNT홀딩스**, **071050 없음**  
   - live target: **071050 있음**, **036530 없음** → “draft 8종목을 그대로 승인”이 아님
3. **승인 브리지로 유지·미세조정**  
   - `target_write_audit.jsonl`(아카이브): 2026-07-03~11 `approval_bridge` / `alpha_proposal_approved_by=human` 다수  
   - 2026-07-11 02:11 UTC 최종 승인 해시가 `target_portfolio_write_guard.json`의 `operational_target_hash`와 일치  
   - 그날 `target_proposal_diff.csv`: 071050은 **add가 아니라** `5.59→5.55` **adjust** (`kr_alpha 예산 21.8% 맞춤 스케일`) → **이미 이전에 target에 존재**
4. **추가 시 밴드 지문**  
   - live min/max = **1.0 / 4.0** = `resolve_add_candidate` 기본값  
   - satellite yaml `compute_bands`나 compass 분해 결과(≈0.69/4.58)와 불일치  
5. **첫 git 스냅샷(`a5d44cb`)에도 이미 동일 행 존재** → 레포 초기화 이전에 운영 CSV에 들어간 상태.  
   - 로컬 `decision_log`/`target` 백업 중간본이 없어 **최초 add의 시·분 단위 시각은 복원 불가**  
   - 하한: 아카이브 `outputs/target_portfolio_proposed.csv`(2026-07-02)에는 **071050 없음**(036530·030190 구성)  
   - 상한: 2026-07-11 이전 승인 사이클 중 한 번의 human approval로 편입된 뒤, 이후에는 예산 스케일만 반복

### 해석 (왜)

- UI/브리지 기본 추가 후보는 `default_add_candidates()`가 **portfolio proposal 상위 행**을 쓰며, **WATCH를 걸러내지 않음** (NO_NEW·Reject만 제외).  
- 가중치는 proposal의 **~8%**, 밴드는 **미지정 → 1.0/4.0**.  
- 이후 `kr_alpha_budget`(~21.8%)에 맞추며 비중만 줄어 **5.5x%**가 되어도 max=4.0은 그대로 → **상한 초과**.  
- 운영자가 “8종목 유지”를 승인한 정황은 있으나, **CECS 7종 설계를 8종으로 재설계했다고 문서화된 전환은 없음**. draft는 여전히 036530 기준.

---

## 4. 종목별 분류

공통 메커니즘 (아래 5종):  
draft `compute_bands` 결과(min 5.36 / 1.38)가 live에 남고, `propose_target_changes` 예산 스케일이 **target만** ~0.58배로 줄임  
(예: draft KT 7.0 → live 4.07, min은 5.36 고정 → below_min).

| 티커 | 위반 | 밴드 출처 | 분류 | 근거 |
|------|------|-----------|------|------|
| 030200 KT | below min | draft Core 밴드 동결 | **CONFIG_DRIFT_BUG** | target만 축소, min 미재계산 |
| 021240 코웨이 | below min | 동일 | **CONFIG_DRIFT_BUG** | 동일 |
| 005830 DB손보 | below min | 동일 (+ draft trim floor=min) | **CONFIG_DRIFT_BUG** | 동일 |
| 006040 동원산업 | below min | draft Core 소형 밴드 | **CONFIG_DRIFT_BUG** | 동일 |
| 271560 오리온 | below min | 동일 | **CONFIG_DRIFT_BUG** | 동일 |
| 071050 한국금융지주 | **above max** | add 기본 1.0/4.0 | **CONFIG_DRIFT_BUG** | 편입은 승인 경로로 보이나, 밴드·티어 재계산 없이 WATCH/8% 후보가 operational target에 남아 위반. “의도된 과도기”로 밴드를 방치했다는 증거 없음 |

정상(참고): 000660 · 005440 — 현재 밴드 안.

**7종 설계 vs 8종 실배분:**  
설계/draft는 “8행이지만 036530 구성”, live는 “071050이 큰 satellite 비중”.  
문제는 종목 수 자체보다 **승인 브리지가 비중만 맞추고 밴드를 원천 공식과 재동기화하지 않는 것**.

---

## 5. 수정 방안 제안 (구현은 운영자 승인 후)

금지: min/max를 경고 끄려고만 넓히기 · validators 완화 · policy_cap/게이트 손대기 · 071050 임의 삭제.

### A. 근본 수정 (권장) — 스케일 시 밴드 동반 갱신

`propose_target_changes()`의 `kr_alpha_budget` 스케일에서 `target_weight`와 동일 factor로 **`min_weight`/`max_weight`도 스케일**하거나, 스케일 후 tier를 알 수 있으면 `compute_bands(target, tier, cfg, budget)`로 **재계산**.  
→ 030200류 below_min과, 예산만 줄인 경우의 드리프트를 막음.

### B. 신규 add 경로 — 기본 1/4 폐기, 공식 밴드 부여

`default_add_candidates` / `resolve_add_candidate`에서:

- proposal `role`/tier에 맞춰 `target_matrix.compute_bands` 적용  
- 또는 satellite yaml 비율·`portfolio_max` 사용  
- **WATCH / BLOCK_NEW_BUY 상태는 기본 add 후보에서 제외** (지금은 WATCH도 통과)

→ 071050형 “8% + max 4.0” 구조적 모순 방지.

### C. 데이터 정리 (승인 1회, 구성은 운영자 선택)

운영자가 확정한 **구성(8종·071050 유지 여부)** 을 고른 뒤:

1. **유지 시:** live 비중에 대해 `compute_bands` 또는 compass `decompose`와 동일한 규칙으로 min/max **재생성** 후 `apply_proposed_target` (감사 로그 남김).  
   - 참고 수치: 현재 비중에서 compass는 이미 `071050 → min≈0.69 max≈4.58` 등 **밴드 내** 안을 산출함 (`generated`/`target_portfolio_proposal`).  
2. **draft(036530)로 되돌릴 시:** draft 재승인 — 별도 구성 결정.  
3. **어느 쪽이든** “경고만 사라지게 max만 올리기”는 금지 목록과 동일하게 거절.

### D. 가시성 (선택)

승인 UI에 “제안 CSV(compass) vs proposed(approval)” 밴드 불일치 경고, 또는 apply 전 `validate_inputs` band 위반이면 **차단/확인 체크**.

---

## 6. `input_validation_gate` 전·후 예상

| 시점 | 예상 |
|------|------|
| **현재** | `validate_inputs` → 6건 `target outside min/max band` → input_validation 쪽 **YELLOW** (portfolio_gate의 policy_cap YELLOW와 **독립**) |
| **A+B+C 적용 후 (구성 유지·밴드 재동기화)** | 해당 6건 경고 **소멸** 예상 → input_validation_gate **GREEN 가능** |
| **portfolio / data_gate / 매수** | **즉시 GREEN 아님** — policy_cap(~2026-09-24 재평가) 등 다른 병목 유지. 이번 건은 캡 해제 후 다음 병목 제거용 |

---

## 7. 증거 인덱스

- Live: `data/target_portfolio.csv`, `data/user_target_portfolio.csv`, `data/target_portfolio_write_guard.json`  
- Draft: `alpha_portfolio/data/output/target_draft.csv`  
- 원천식: `alpha_portfolio/src/target_matrix.py`, `alpha_portfolio/config/target_matrix.yaml`  
- 드리프트: `src/alpha/target_bridge.py` (`propose_target_changes` budget scale, `resolve_add_candidate`, `default_add_candidates`)  
- 정상 스케일: `src/compass/target_decomposer.py`  
- 감사: `C:\Cursor\_archive\multi_asset_trigger_portfolio\outputs\target_write_audit.jsonl`  
- 대조 CSV: 동 아카이브 `outputs/proposals/target_portfolio_proposed.csv` vs `target_portfolio_proposal.csv` (2026-07-11)

---

## 8. 다음 액션 (승인 대기)

1. 운영자: **8종목·071050 유지 vs draft(036530) 복귀** 선택  
2. 승인 시: **A(+B)** 코드 수정과 **C** 1회 밴드 재동기화 PR/적용  
3. 재실행: `python scripts/diagnose_kr_alpha_minmax_bands.py` + `validate_inputs`로 경고 0건 확인  
4. policy_cap / execution_scope는 **그대로**
