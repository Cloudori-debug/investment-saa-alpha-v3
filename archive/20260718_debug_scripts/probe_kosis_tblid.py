"""One-off probe script — KOSIS statisticsList BFS for CPI/PMI tblIds."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from src.data_refresh.tier2_refresh import _kosis_api_key


def parse_kosis_json(raw: str):
    fixed = re.sub(r"([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', raw.strip())
    return json.loads(fixed)


def get_list(api_key: str, parent: str, vw: str = "MT_ZTITLE"):
    url = "https://kosis.kr/openapi/statisticsList.do?" + urllib.parse.urlencode({
        "method": "getList",
        "apiKey": api_key,
        "vwCd": vw,
        "parentId": parent,
        "format": "json",
        "content": "json",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-trigger-portfolio/2.2"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return parse_kosis_json(resp.read().decode("utf-8"))


def debug_tree(api_key: str, parents: list[str]) -> None:
    for p in parents:
        try:
            lst = get_list(api_key, p)
            print(f"parent {p} count {len(lst) if isinstance(lst, list) else lst}")
            if isinstance(lst, list):
                for x in lst[:8]:
                    print(
                        " ",
                        x.get("LIST_ID"),
                        str(x.get("LIST_NM", ""))[:45],
                        "TBL=",
                        x.get("TBL_ID"),
                    )
        except Exception as exc:
            print(f"parent {p} ERR {exc}")


def main() -> None:
    key = _kosis_api_key(Path("data")).strip()
    keywords = [
        "소비자물가", "물가지수", "전년동월", "구매관리자", "PMI",
        "경기실사", "업황전망", "제조업", "BSI",
    ]
    found: list[dict] = []
    queue = ["A"]
    seen: set[str] = set()
    while queue and len(seen) < 400:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        try:
            lst = get_list(key, pid)
        except Exception as exc:
            print("ERR", pid, exc)
            continue
        if not isinstance(lst, list):
            continue
        for x in lst:
            lid = str(x.get("LIST_ID") or "")
            nm = str(x.get("LIST_NM") or "")
            tbl = str(x.get("TBL_ID") or "")
            if tbl:
                if any(k in nm for k in keywords):
                    found.append({
                        "LIST_ID": lid,
                        "LIST_NM": nm,
                        "TBL_ID": tbl,
                        "ORG_ID": str(x.get("ORG_ID") or ""),
                        "STAT_ID": str(x.get("STAT_ID") or ""),
                        "SEND_DE": str(x.get("SEND_DE") or ""),
                        "parent": pid,
                    })
            elif lid:
                queue.append(lid)

    out_path = Path("outputs/_kosis_probe.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"found {len(found)} tables -> {out_path}")


if __name__ == "__main__":
    import sys

    key = _kosis_api_key(Path("data")).strip()
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        debug_tree(key, sys.argv[2:] or ["A", "B", "C", "E", "E_1", "E_2"])
    else:
        main()
