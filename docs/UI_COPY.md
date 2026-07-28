# UI 카피 — 알파 시스템 대시보드

코드에 사용자-facing 문구를 하드코딩하지 마세요.  
아래 YAML 블록이 단일 원본입니다 (`alpha_system.ui.services.ui_copy` 가 로드).

```yaml
version: "1.0"

system_states:
  PRE_LAUNCH:
    banner: "가동 전 — 체크리스트 {done}/{total}"
    banner_detail: "앱 실행과 시스템 가동은 분리되어 있습니다. go-live 선언 전까지 모든 트랜치가 잠깁니다."
  LIVE:
    banner: "가동 중 — go_live {go_live_date}"
  FROZEN:
    banner: "논지 훼손 — 미집행 트랜치 동결"
    banner_detail: "미집행분은 SAA 환류 대상입니다. 기집행 포지션은 exit 판정을 계속합니다."
  WINDOW_END:
    banner: "논지 창 종료 — 정리 판정"
    banner_detail: "window_end에 도달했습니다. 액션 큐 최상단의 정리 항목을 확인하세요."

tranches:
  T1:
    display_name: "즉시 집행분"
    short_desc: "시스템 가동 시 바로 집행하는 몫입니다. 촉매가 일찍 와도 놓치지 않기 위한 헷지입니다."
  T2:
    display_name: "제도 확정 대기분"
    short_desc: "상법·MSCI·IFRS18 등 시장 레벨 제도 이벤트 1건이 확정되면 집행합니다."
  T3:
    display_name: "저가 매수 대기분"
    short_desc: "KOSPI 시장 PBR이 10년 분포 하위 20%에 들어오면 집행합니다. 매월 말에 판정합니다."
  T4:
    display_name: "기한 보험분"
    short_desc: "가동 후 12개월이 지나면 절반을 집행하고, T2·T3가 뒤늦게 오면 나머지를 이어 집행합니다."

judgment:
  pre_launch_locked: "시스템은 지금 가동 전이라 이 몫을 잠가 두었습니다. go-live를 선언하기 전까지는 트리거를 보지 않습니다."
  already_executed: "이 몫은 이미 집행이 끝난 상태입니다. 추가 집행은 없습니다."
  frozen: "논지 훼손 플래그로 이 몫이 동결되었습니다. 미집행분은 SAA로 환류 대상입니다."
  expired: "논지 창이 끝나 이 몫은 소멸(만료)되었습니다."
  ready_to_execute: "집행 조건이 충족되었습니다. 사용자가 집행을 승인·실행할 차례입니다."
  partial_executed: "일부만 집행되었습니다. 남은 몫은 후속 조건(T2·T3 후발 또는 잔여 규칙)을 기다립니다."

  T1:
    met: "가동이 선언되어 즉시 집행 조건이 충족된 상태입니다."
    not_met: "아직 가동 전이라 즉시 집행 조건이 아닙니다."
    unknown: "가동 여부를 확인할 수 없어 즉시 집행 분을 판단할 수 없습니다."
  T2:
    met: "설정한 제도 이벤트 중 하나가 기록되어 집행 조건이 충족되었습니다."
    not_met: "아직 제도 확정 이벤트가 기록되지 않았습니다. 지금은 집행할 때가 아닙니다."
    unknown: "이벤트 기록을 확인할 수 없어 제도 확정 분을 판단할 수 없습니다."
  T3:
    met: "KOSPI 시장 PBR이 10년 하위 20% 밴드에 들어 저가 매수 조건이 충족되었습니다."
    not_met: "아직 저가 밴드에 들어오지 않았습니다. 다음 판정은 매월 말입니다."
    unknown: "PBR 이력 데이터가 없어 저가 매수 조건을 판단할 수 없습니다. 다음 판정은 매월 말입니다."
  T4:
    met: "가동 후 12개월 시점(또는 후속 규칙)에 따라 기한 보험분 집행 조건이 충족되었습니다."
    not_met: "아직 가동 후 12개월 시점이 되지 않았고 후속 조건도 없습니다. 다음 판정은 가동 후 12개월 시점입니다."
    unknown: "가동일 또는 경과 개월을 확인할 수 없어 기한 보험분을 판단할 수 없습니다."

  fallback: "판정 사유 확인 필요"
  next_check:
    T3: "다음 판정: 매월 말"
    T4: "다음 판정: 가동 후 12개월 시점"

action_queue:
  checklist_item: "{title} — {why}. 할 일: {todo}"
  cap_reduce: "비중 한도({cap}%)를 넘긴 종목입니다. 이유: 현재 비중 {weight}%. 할 일: 감축을 검토하세요."
  exit_reduce: "청산·감축 신호입니다. 이유: {why}. 할 일: 포트폴리오에서 확인 후 집행하세요."
  swap_observe: "스왑 후보(관찰)입니다. 이유: {why}. 할 일: 교체 여부를 검토만 하고 자동 집행하지 마세요."
  tranche_ready: "{name} 집행 신호가 있습니다. 이유: {why}. 할 일: 집행 여부를 승인하세요."
  data_stale: "데이터 갱신이 필요합니다. 이유: {why}. 할 일: 결재함(또는 홈)에서 갱신을 실행하세요."
  today_none: "오늘 할 일 없음 — 다음 판정: {next}"
  window_end_wind_down: "논지 창이 종료되었습니다. 이유: window_end {date}. 할 일: 정리 판정을 확인하세요."

regime:
  mode_pure_auto: "순수 자동"
  card_detail_pure: "산출=적용 · 일 파이프라인 갱신 · QVM 순위 불변"
  card_detail_override: "나침반 지표 파일 · 사람 재분류 가능(자동 완화 금지)"
  concerns_title: "레짐 순수 자동 — 유의"
  concerns:
    - "완화(RISK_ON 방향)도 자동입니다. 신규매수 게이트·TAA tilt가 사람 확인 없이 풀릴 수 있습니다."
    - "단기 VIX·낙폭 노이즈로 레짐이 흔들릴 수 있습니다(히스테리시스로 일부만 완화)."
    - "Tier-2(FRED/KOSIS)가 오래되면 산출 신뢰도가 떨어집니다."
    - "레짐은 종목 순위(QVM)를 바꾸지 않습니다. 실행 게이트·자산군 비중만 영향을 받습니다."
    - "긴급 수동 고정이 필요하면 tier2_sources.yaml의 regime_sync_mode를 respect_override로 되돌리세요."

system_judgment:
  title: "시스템 판정"
  caption: "자동 판정 · 승인 아님 · 조회·참고 · 사람이 레짐을 고르지 않음 · target 불변"
  row_regime: "시장 레짐"
  row_t3: "T3"
  row_next: "다음 판정"
  t3_unavailable: "이력 없음 · 월말 판정 연결 전"
  t3_in_band: "하단 밴드 진입"
  t3_out_band: "하단 밴드 밖"
  t3_band_unknown: "밴드 판정 불가"
  t3_cadence: "다음 판정: 매월 말"
  cta_t3: "T3 상세 →"
  cta_regime: "레짐 상세 →"
  cta_settings: "데이터·API →"

regime_page:
  title: "레짐"
  lead: "나침반 시장 레짐·Tier-1 지표 조회. 승인 화면이 아니며 target_portfolio·QVM 순위를 바꾸지 않습니다."
  status_title: "현재 적용 레짐"
  status_caption: "조회·참고 · 사람이 메뉴에서 레짐을 고르지 않음 · 순수 자동 시 산출=적용"
  override_note: "현재 respect_override 모드입니다. CSV regime 값을 사람이 고정할 수 있습니다."
  indicators_title: "Tier-1 시장 지표"
  indicators_caption: "data/market_indicators.csv 최신 행 · 분석 버튼/런처 [3]은 Tier-1 네트워크 갱신+레짐 동기화 후 분석"
  related_title: "연관 판정"
  refresh_title: "나침반 분석 갱신"
  refresh_caption: "런처 [3]과 동일 (standard + --refresh-market). Tier-1·레짐 동기화·outputs 갱신 · target_portfolio 자동 변경 없음 · 보통 5~15분"
  refresh_cta: "나침반·레짐 분석 실행"
  refresh_spinner: "나침반 분석 실행 중… 5~15분 걸릴 수 있습니다. 창을 닫지 마세요."
  refresh_reload: "지표를 다시 읽으려면 아래를 누르거나 페이지를 새로고침하세요."
  refresh_rerun: "화면 새로고침"
  how_title: "안내"
  how_body: |
    1. 위 **나침반·레짐 분석 실행** (또는 런처 [3] Analysis)
    2. 산출: `data/market_indicators.csv` · `outputs/` 일일 리포트
    3. 레짐 값은 UI에서 수동 선택하지 않습니다 (순수 자동/파일 기준).
    4. 알파 점수만 필요하면 홈 **정량 전체 갱신**을 쓰세요 (이 버튼과 다름).
  invariant: "불변: proposal_mode pure_qvm · target_portfolio 자동 변경 없음 · 레짐≠종목 순위"
  cta_settings: "Tier-2·데이터 →"

portfolio:
  target_missing_violation: "목표가 없음 — 편입 규칙 위반"
  target_missing_legacy: "목표가 없음 — 레거시 보유, 이행 심사 대기"
  target_missing_screen: "목표가 없음 — 다음 주 통합 보고서(E)까지 대기 · 편입 차단"
  badge_violation: "위반"
  badge_legacy: "이행대기"
  badge_screen: "스크린"
  ops_cue_hold: "유지"
  ops_cue_trim: "줄이기"
  ops_cue_cash: "환금"
  ops_cue_exit: "전량"
  ops_cue_missing: "목표없음"
  ops_cue_invalid: "데이터없음"
  ops_cue_caption: "도달=절반 환금 · 탈락·타임캡=전량 · 읽기 전용"
  price_missing_signal_invalid: "데이터 없음 — 신호 무효 (가격 확인)"
  target_revalidate_required: "목표가 재검증 필요"
  sector_cap_over: "섹터 합산 {bucket} {weight}% > 한도 {limit}% ({n}종: {tickers}) — 비중·편입 재검토"
  sector_cap_ok: "섹터 합산 한도 {limit}% 이내 (동일 섹터 ≤2종 · 2종 이상 시 합산 ≤{limit}%)"
  entry_journal_empty: "편입 저널 없음"
  entry_journal_legacy: "신규 시스템 편입 절차 미경유 (레거시 보유)"
  screen_book_caption: "객관 스크린(정책 B) 상위 적격 · 매입 비중 아님 · target 미승인 제안 비중"
  watchboard_title: "적격 순위 감시"
  watchboard_caption: "표시만 · 매수/매도 지시 아님 · 편입 수(5~8)와 별개 · positions 보유 미표시 · eligibility 통과 · total_score 순위 · 섹터캡 미적용"
  watchboard_footer: "순위 하락 ≠ 매도 트리거. 제안 탈락 시 익절 배지(S2a)는 별도 권고입니다. positions.csv 보유 하이라이트는 사용하지 않습니다."

action_panel:
  principle: "실행(매매)은 증권사에서, 이 시스템에서는 판정과 기록을 합니다."
  swap_observe_only: "관찰 모드: 기록만 됩니다. 스왑 활성화는 운용 데이터 축적 후 재검토"
  full_screen_aux: "전체 화면에서 보기"
  execute_situation: "{name} 발화 — 총 {amount} 집행 대상"
  execute_situation_no_krw: "{name} 발화 — 트랜치 비중 {pct}% 집행 대상 (금액 환산 불가)"
  reduce_situation: "{name} 평가액 {weight}% — 상한 {cap}%를 {excess}%p 초과"

rules:
  edit_friction: "일반 규칙 변경은 PC에서 config 파일 직접 수정 — 의도된 마찰입니다. score_cutoff만 체크리스트의 상관 리포트·2단계 승인 경로로 확정합니다."

journal:
  append_only: "저널은 append-only입니다. 정정은 취소 기록을 추가로만 남깁니다."
  discretion_tooltip: "재량 이탈 누적이 커지면 규칙 재설계 신호입니다."

checklist:
  score_cutoff:
    title: "score_cutoff 미확정"
    why: "적격 컷라인이 비어 있으면 편입·청산 기준을 확정할 수 없습니다"
    todo: "체크리스트 처리 패널에서 상관 리포트 확인 후, 상위 N종 슬라이더로 score_cutoff를 확정하세요"
  cecs_final:
    title: "CECS 검토(선택·순위 미반영)"
    why: "Ops A: CECS는 proposal 순위에 들어가지 않습니다. final {final}/{total}은 참고 기록입니다"
    todo: "필수 게이트는 T2·논지·목표가입니다. CECS는 여유 있을 때 결재함에서 검토하세요"
  t3_history:
    title: "T3 PBR 이력 CSV 부재"
    why: "월간 저가 밴드 판정에 필요한 10년 PBR 이력이 없습니다"
    todo: "data/kospi_market_pbr_history.csv를 준비하세요"
  go_live_blocked: "go-live를 차단했습니다. 미충족: {items}"

cecs_scoring:
  page_task: "shortlist 30종을 하나씩, 근거를 남기며 채점합니다."
  ai_button_batch: "전체 배치 조사 요청서 생성"
  ai_batch_scope_unrated: "미채점 종목 전체"
  ai_batch_scope_all: "shortlist 30종 전체"
  ai_warning: "AI 제안은 초안입니다. 종목별 출처 원문을 펼쳐 확인하고, 필요하면 점수·근거를 수정한 뒤 승인해야 final이 됩니다."
  ai_provider_note: "외부 AI 도구(웹검색 가능)에 생성 파일을 붙여넣어 채운 뒤 완성된 마크다운 파일을 업로드하세요. 현재 앱은 자체 AI 연동이 없습니다."
  ai_saved: "배치 조사 요청서 저장됨: {path}"
  ai_download_location_note: "다운로드 버튼을 누르면 브라우저 설정에 따라 저장 위치 선택 창이 열리거나 기본 다운로드 폴더에 저장됩니다."
  ai_upload: "완성된 리포트 업로드"
  ai_imported: "AI 제안 {count}종을 ai_suggested 상태로 가져왔습니다."
  ai_parse_failed: "파싱 실패 — 해당 종목은 스키마를 수정하거나 수동 입력하세요: {items}"
  ai_source_review: "출처 링크를 펼쳐 원문 목록을 확인했습니다"
  ai_approve_one: "AI 제안 승인"
  ai_approve_batch: "출처 확인 완료 종목 일괄 승인"
  ai_approved: "승인 완료 — final {final}/{total}"
  execution_help: "최근 4개 분기 중 주주환원 이벤트가 있었던 분기 비율입니다. 4/4=1.00, 3/4=0.75, 2/4=0.50, 1/4=0.25, 0/4=0.00."
  pension_help: "연기금 2분기 이상 증가=0.70~1.00, 보합=0.50, 감소=0.20~0.40, 미보유·보고 없음=0.50."
  purpose_help: "대량보유보고 투자목적이 일반·단순투자=1.00, 경영참여=0.30, 보고 없음=0.50."
  rationale_required: "채점 완료에는 execution·pension·purpose 근거 3개가 모두 필요합니다."
  draft_saved: "임시 저장 완료 — draft 상태를 유지합니다."
  final_saved: "채점 완료 — final 저장 및 저널 기록 완료 ({final}/{total})."

checklist_panel:
  cecs_situation: "CECS 검토 {final}/{total} (선택·순위 미반영)"
  cutoff_situation: "score_cutoff 미확정"
  cutoff_locked: "절대 컷오프는 포트폴리오에서 확정합니다 (CECS 완료 여부와 무관 · Ops A)."
  t3_situation: "KOSPI 시장 PBR 이력 CSV 없음"
  cutoff_absolute_help: "절대 score_cutoff → eligibility → 편입 수(5~8) 순으로 확정합니다. 상대순위(상위 N종 수를 먼저 고르는) 방식은 쓰지 않습니다. 확정은 포트폴리오 화면에서만 합니다. total_score는 정량 100%(CECS 가중 0)."
  cutoff_confirm_1: "절대 컷오프와 경계 종목을 확인했습니다"
  cutoff_confirm_2: "이 값이 편입 eligibility와 향후 exit 판정에 연결됨을 이해하고 확정합니다"

go_live:
  warn: "이 선언은 시스템을 가동합니다. T1 즉시 집행분 트리거가 켜지고 T4 12개월 시계가 시작됩니다."
  confirm_1: "앱 실행과 가동이 다름을 이해했고, 체크리스트를 확인했습니다"
  confirm_2: "go-live를 최종 선언합니다"
  success: "go-live 선언 완료 — {date}"
  already_live: "이미 가동 중입니다 (go_live {date})"

hard_rule:
  reverse_blocked: "역방향 집행이 차단되었습니다. 이유: {why}. 할 일: 트리거가 충족된 뒤에만 집행하세요."

ai_verification:
  button: "AI 검증 리포트 생성"
  usage_banner: "AI 답변은 참고용. 출처 원문을 직접 확인한 후에만 이벤트 입력을 진행하세요."
  saved: "저장됨: {path}"
  t2_events:
    commercial_code_enforcement_decrees:
      label: "상법 시행령·시행규칙 확정"
      question: "상법 관련 시행령·시행규칙이 '확정'되었는가?"
      confirm_criterion: "확정 인정 기준 = 관보 게재. 입법예고·보도만으로는 미확정."
    msci_dm_index_inclusion_confirmed:
      label: "MSCI DM 지수 편입 확정"
      question: "한국(또는 해당 시장)의 MSCI DM 지수 편입이 '확정' 발표되었는가?"
      confirm_criterion: "확정 인정 기준 = MSCI 공식 편입 발표. 워치리스트 등재는 발화 아님(제외)."
    ifrs18_domestic_adoption_schedule_confirmed:
      label: "IFRS18 국내 도입 일정 확정"
      question: "IFRS18 국내 도입 일정이 '확정'되었는가?"
      confirm_criterion: "확정 인정 기준 = 금융위원회 또는 한국회계기준원의 확정 고시. 검토·의견수렴만으로는 미확정."
  thesis_damage:
    question: "논지 훼손 징후가 있는가? 특히 상법개정(주주환원·지배구조 관련)의 후퇴·유예 움직임이 관측되는가?"
    note: "시스템이 자동 관측하지 않음. 1차 출처 기준으로만 답할 것."
  holdings_disclosure:
    question: "가동 후 보유 종목별로 주주환원 정책 변경 공시가 있었는가? (배당·자사주·정관 등)"
    note: "가동(PRE_LAUNCH 해제) 이후에만 해당. 종목 목록은 아래 보유 티커를 사용."
  answer_rules:
    - "모든 답변에 1차 출처(관보·공시·공식 발표) URL을 반드시 포함할 것."
    - "확인 불가 시 '확인 불가'로 답할 것 — 추정·추론 금지."
    - "뉴스 기사만 있고 1차 출처가 없으면 '미확정 보도 단계'로 구분할 것."
```

## 문장 원칙

모든 시스템 출력은 (a) 무슨 일인지 (b) 왜인지 (c) 사용자가 할 일 을 포함합니다.  
내부 로그 문자열(`system_started`, `unknown in snapshot` 등)은 사용자에게 직접 노출하지 않습니다.
