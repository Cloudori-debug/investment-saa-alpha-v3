# 컨센서스 데이터 실현 가능성 (P1 선행 조사)

> 작성: 2026-07-19 · v2  
> 결론: **PyKRX / OpenDART로는 애널리스트 컨센서스 EPS·목표가·투자의견을 자동 수집할 수 없다.**

---

## 조사 결과

| 소스 | 가능한 것 | 컨센서스 EPS/목표가/등급 |
|------|-----------|-------------------------|
| **PyKRX** | trailing PER·PBR·배당수익률, 시세 | **불가** |
| **OpenDART** | 공시·재무제표·실적 YoY | **불가** (회사 보고 실적 ≠ 컨센서스) |
| Wise/FnGuide 등 | 컨센서스 가능(유료) | 정책상 **스크래핑·무단 수집 금지** |

따라서 Charter의 `earnings_surprise` / `rating_downgrade` / `target_gap_narrowed` 는:

1. **자동 파이프라인으로 강행하지 않음**
2. 주간 정성 **`## F_QUANT_EVENTS`** 에 사람이 기입
3. 업로드 시 `RESCORE_TRIGGER_FIRED` + 홈 액션 큐 「재채점 검토」만 생성
4. **CECS·total_score 자동 변경 없음**
5. SUE/% 임계값은 **TODO** (문헌 정렬 후 별도 승인)

---

## 공시형 트리거 (이미 yaml)

`value_up_program_disclosure`, `treasury_share_cancellation_resolution`, `dividend_articles_amendment`  
→ T2 승인 훅과 병존. 포트 전체 T2 트랜치와 **역할 분리**.

---

## 운영 함의

- 컨센서스 자동화는 **보류**
- 수동 F 섹션 + 기존 공시 트리거로 P1 신호 레이어 MVP 충족
- 유료 API를 쓰려면 별도 계약·승인 후에만
