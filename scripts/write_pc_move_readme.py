"""Write dist/CARRY/새PC에서_하세요.txt after a ledger export."""

from __future__ import annotations

import argparse
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=_ROOT)
    args = p.parse_args()
    carry = args.root / "dist" / "CARRY"
    carry.mkdir(parents=True, exist_ok=True)
    text = """코스피 알파 스크리너 — 다른 Windows PC에서 쓰기
================================

이 시스템은 자동매매가 아닙니다. 프로그램 + 장부만 옮기면 됩니다.

새 PC에서 할 일
----------------
1. Python 3.11 이상을 설치합니다. 설치 화면에서 PATH에 추가에 체크.
   https://www.python.org/downloads/
2. 지금 쓰던 프로그램 폴더 전체를 USB/클라우드에서 복사합니다.
   폴더 이름은 바꿔도 됩니다. .venv 폴더는 빼도 됩니다.
3. 복사한 폴더에서 투자나침반.bat 을 더블클릭합니다.
   처음이면 .venv를 자동으로 만듭니다. 인터넷이 필요하고 수분 걸릴 수 있습니다.
4. 브라우저가 열리면 확인 → 포트폴리오.

장부만 따로 온 경우
--------------------
보유·목표가가 비어 있으면:
  설정 › 도구 › 장부 가져오기 에서 zip을 올리거나
  python scripts/import_ledger.py  02_SAA-Alpha-Backup
API 키를 백업에 안 넣었으면 설정 › API 키에서 DART를 다시 입력합니다.

하지 말 것
----------
- 다른 PC의 .venv 를 그대로 복사해 쓰기 (깨지면 런처가 다시 만듭니다)
- target_portfolio.csv 를 프로그램이 자동으로 고치게 두기 (사람만)

문의용 문서: docs\\V3_CARRY_KIT.md
"""
    path = carry / "새PC에서_하세요.txt"
    path.write_text(text, encoding="utf-8")
    print(f"OK {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
