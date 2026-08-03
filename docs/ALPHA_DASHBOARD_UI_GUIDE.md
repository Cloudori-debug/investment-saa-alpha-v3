# 알파 시스템 대시보드 UI — 실행 가이드

Streamlit 단일 앱. `alpha_system` 모듈을 직접 import 하며 별도 API 서버는 없습니다.

> 실투 범위: [`REAL_INVEST_SCOPE_CHECKLIST.md`](REAL_INVEST_SCOPE_CHECKLIST.md)  
> 런처: [`LAUNCHERS.md`](LAUNCHERS.md) · **`투자나침반.bat`**

## 실행

```powershell
cd C:\Cursor\investment-saa-alpha-v3
.\투자나침반.bat
# 또는: streamlit run alpha_dashboard.py --server.address 127.0.0.1 --server.port 8501
```

## 화면 구성 (현재 IA)

| 화면 | 파일 | 설명 |
|------|------|------|
| **오늘**(홈) | `pages/home.py` | 비중·보유/제안 · 정량 갱신 · 월리밸 접힘 |
| **확인**(결재함) | `pages/approval.py` | ①숫자 · ②이번 주(T2/논지/목표가) · ③가동 · CECS는 접힌 원장 |
| **포트폴리오** | `pages/portfolio.py` | 실보유 · 컷오프 · 제안 북 · 교체 |
| 저널 / 레짐 / 설정 | 각 `pages/*.py` | 더보기 메뉴 |

진입점: [`alpha_dashboard.py`](../alpha_dashboard.py)

정성 = **선택 공적 브레이크** ([`QUAL_PUBLIC_OVERLAY_SPEC.md`](QUAL_PUBLIC_OVERLAY_SPEC.md)). 월간 CECS·pension/purpose = **스킵 기본**.

## 데이터 갱신

- 결재함「① 숫자」또는 홈 정량 CTA → PyKRX(보유 스코프) + alpha_scores
- KRX ID/PW는 **설정**에 저장 ·「KRX 테스트」로 확인
- T3: `data/kospi_market_pbr_history.csv`

## 레거시 UI

일상은 `alpha_dashboard.py`만. 옛 나침반: [`archive/20260803_legacy_compass_ui/`](../archive/20260803_legacy_compass_ui/).
