# 주간 정성 AI 요청서 프롬프트 (범용)

**용도:** 매주 제도·논지 초안만 외부 AI에 맡길 때.  
**입력:** 결재함에서 생성한 `weekly_qual_report_YYYYMMDD.md` 전체.  
**출력:** 헤더·필드명 불변인 완성 Markdown만.

---

## 설계 원칙

1. **범위** — AI는 **C→D**만 채운다. 종목 채점·목표가·심층은 대시보드.
2. **파서 계약** — `##` / `###` / `- 필드:` 라벨 불변.
3. **`fired:true`** — 관보(`gwanbo.go.kr`)·법령(`law.go.kr`)·MSCI(`msci.com`)·금융위(`fsc.go.kr`)·회계기준원(`kasb.or.kr`) URL만. 신문·로펌·DART 뷰어는 false.
4. **사람 결재** — 한 번 채움 ≠ 최종. 업로드 후 확인 › ②에서 승인.

---

## 복사용 프롬프트 A — 제도·논지 (매주 기본)

```text
당신은 한국 상장주식 주간 정성 조사 보조입니다.
첨부 Markdown은 SAA 알파 시스템의 주간 제도·논지 요청서입니다.
첨부 상단의 as_of·섹션 헤더·「작성 규칙」·T2 확정 기준을 그대로 따르세요.
종목 목록·CECS 점수를 추가하지 마세요.

# 역할
- 빈칸을 채울 곳: C_T2_EVENTS → D_THESIS 만.
- 종목 채점, TARGET 블록, DEEP, SIGNAL을 만들지 마세요.

# 절대 규칙
1. `##` / `###` 헤더와 `- 필드:` 라벨을 변경·삭제·번역하지 마세요.
2. 추정 금지. 확인 불가면 근거에 `확인 불가; 검색 키워드: "..."` .
3. 출처는 줄마다 http(s) URL.
4. `target_portfolio.csv` 변경·매수 추천 금지.
5. 출력은 완성 Markdown만. as_of 기준.

# C_T2_EVENTS
각 `### EVENT [...]`마다 fired: true 또는 false, 근거, 출처.
fired:true 는 다음 호스트만: gwanbo.go.kr, law.go.kr, msci.com, fsc.go.kr, kasb.or.kr.
신문·로펌 해설만 있으면 false.

# D_THESIS
- damage: true 또는 false
- 근거·출처 필수
주주환원·지배구조·밸류업 제도가 as_of 기준 확정적으로 훼손·후퇴·유예되었는가?
개별 실적만으로 damage:true 금지. 불확실하면 false.

# 자기점검
- C: 각 EVENT 근거 ≠ _____ , fired ∈ {true,false}
- D: 근거 ≠ _____
- true인 출처 호스트가 허용 목록인지

[아래에 요청서 Markdown 전체를 붙이세요]
```

---

## 복사용 프롬프트 B — 목표가 보충 (도구·테스트용, UI 없음)

목표가는 포트폴리오 › 제안 종목에서 정량초안을 승인한다.

```text
당신은 한국 상장주식 목표가(익절·밸류 상한) 조사 보조입니다.
첨부는 E_TARGET_VALUATION만 있는 보충 요청서입니다.
첨부된 모든 `### TARGET [티커] 이름`만 채우세요. 헤더·필드명 변경 금지.
target_portfolio.csv 변경 금지. 완성 Markdown만.
```

---

## 복사용 프롬프트 C — 폐기

월간 30종 CECS 채점은 하지 않는다. 종목 게이트는 제안 종목 화면의 OpenDART 초안이다.

```text
월간 CECS 채점 요청서는 사용하지 마세요.
종목 게이트(경영참여·연기금 이탈)와 목표가는 대시보드 포트폴리오 › 제안 종목에서 처리합니다.
DART/KIND HTML 뷰어(dsaf001, viewer.do)를 열지 마세요.
```
