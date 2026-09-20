# 제도·논지 킬스위치 SPEC

**상태:** 공식 RSS 탐색만 (2026-08-31)  
**코드:** `killswitch_watch.refresh_killswitch_watch`  
**UI:** 확인 › ② — 공식 RSS 후보 조회. 기입·승인 칸 없음  
**목표가·종목 게이트:** 포트폴리오 › 제안 종목에서 자동  
**클로드 요청서 없음.** 30종 CECS 채점 없음.

## 질문

1. 이 제안 종목은 들어가도 되나 — 컷·편입 수 확정 시 OpenDART 자동 탐색 → 경영참여·연기금은 제안에서 자동 제외  
2. 익절 숫자는 — 컷 확정 시 정당 60%+섹터 40% 자동 → `kr_alpha_exit_targets.yaml`  
3. 제도·논지가 깨졌나 — **공식 RSS가 후보를 모은 뒤** 원문을 본다. `fired`/`damage`를 켜지 않음

순위는 정량(Ops A). 홈은 주간 리포트 없음을 다음 할 일로 막지 않음. 탐색 후보는 `blocks_next=False`.

## 탐색 (프로그램)

- 허용 호스트 **공식 RSS만** (금융위 보도·설명·공지, MSCI IR 피드). 뉴스 검색·DART HTML 없음.  
- 키워드로 **후보만** `data/killswitch_watch.json`에 저장. `fired`/`damage`를 켜지 않음.  
- 정량 전체 갱신 성공 뒤 같이 돌고, 확인 › ② 버튼으로도 돈다.  
- 빈 탐색 ≠ 없음. 관보 원문은 RSS에 없을 수 있어, 화면의 공식 검색 링크로 직접 연다.  
- `target_portfolio.csv` 불변.

## 사람 기입 없음

상법·MSCI·IFRS18·논지 라디오, URL 칸, 이슈 초안 저장, 킬스위치 승인 보드는 두지 않는다.  
신평·공공 게이트·자리 교체 폼도 두지 않는다. 정량·정성은 자동 경로만 쓴다.

## 불변

- AI는 이 경로에 없음
- `target_portfolio.csv` 자동 쓰기 금지
- FASTJUSIK 금지 · `proposal_mode: pure_qvm`
- OpenDART JSON만. DART/KIND HTML 스크래핑 없음
