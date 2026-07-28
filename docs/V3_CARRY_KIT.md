# v3 — 들고 다닐 것 단 2개

> 목표: **프로그램**과 **장부**만 USB에 넣으면 끝.

```
dist\CARRY\
  01_SAA-Alpha-App\        ← ① 프로그램 (또는 Setup.exe)
  02_SAA-Alpha-Backup\     ← ② 장부 백업
  이렇게_두_개만_들고가세요.txt
```

---

## 쉬운 그림

| 들고 다닐 것 | 안에 뭐가 있나 | 언제 쓰나 |
|--------------|----------------|-----------|
| **① 앱** | 실행 파일·아이콘·코드 | 새 PC에 설치/복사 |
| **② 장부** | 보유·목표·승인·목표가 | 백업·이사·주고받기 |

프로그램 업데이트 ≠ 장부 백업.  
`업데이트.bat` = ①만 교체 · `장부_내보내기/가져오기` = ②만 이동.

---

## 아이콘

- 파일: `saa_alpha.ico` (나침반 · 청록+호박색)
- 바로가기: `SAA알파.lnk` (빌드 시 생성)
- Setup/시작메뉴도 같은 아이콘

다시 만들기: `python scripts/build_app_icon.py`

---

## 일상

| 하고 싶은 일 | 더블클릭 |
|--------------|----------|
| 실행 | `투자나침반.bat` 또는 `SAA알파` 아이콘 |
| 장부 USB로 빼기 | `장부_내보내기.bat` |
| 장부 다시 넣기 | `장부_가져오기.bat` |
| 프로그램만 업데이트 | `업데이트.bat` |

---

## USB 키트 만들기

```powershell
# 장부(②)만 빠르게
powershell -File scripts\build_carry_kit.ps1

# 앱(①)까지 포터블로 같이 (시간 김)
powershell -File scripts\build_carry_kit.ps1 -Bundle
```

Setup.exe를 쓰려면:

1. `-Bundle` 후 `packaging\saa_alpha.iss` 컴파일  
2. USB에 `SAAAlphaSetup-*.exe` + `02_SAA-Alpha-Backup` 폴더

---

## 새 PC

1. ① 설치 또는 폴더 복사 → 실행  
2. `장부_가져오기.bat` → ② 폴더 지정  
3. 끝
