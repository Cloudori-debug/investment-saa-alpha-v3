"""Inspect KOSIS row metadata for CPI table."""
import json
import urllib.parse
import urllib.request
from pathlib import Path

from src.data_refresh.tier2_refresh import _kosis_api_key

key = _kosis_api_key(Path("data")).strip()
params = {
    "method": "getList",
    "apiKey": key,
    "format": "json",
    "jsonVD": "Y",
    "orgId": "101",
    "tblId": "DT_1J22042",
    "itmId": "ALL",
    "objL1": "ALL",
    "objL2": "",
    "objL3": "",
    "objL4": "",
    "objL5": "",
    "objL6": "",
    "objL7": "",
    "objL8": "",
    "prdSe": "M",
    "startPrdDe": "202601",
    "endPrdDe": "202606",
}
url = "https://kosis.kr/openapi/Param/statisticsParameterData.do?" + urllib.parse.urlencode(params)
with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "test"}), timeout=60) as resp:
    rows = json.loads(resp.read().decode("utf-8"))

for row in rows[:20]:
    if not isinstance(row, dict):
        continue
    print(
        row.get("ITM_ID"),
        row.get("ITM_NM"),
        row.get("C1"),
        row.get("C1_NM"),
        row.get("PRD_DE"),
        row.get("DT"),
        row.get("UNIT_NM"),
    )

print("--- unique ITM for 202606 ---")
items = {}
for row in rows:
    if str(row.get("PRD_DE")) != "202606":
        continue
    k = (row.get("ITM_ID"), row.get("ITM_NM"), row.get("C1"), row.get("C1_NM"))
    items[k] = row.get("DT")
for k, v in sorted(items.items(), key=lambda x: str(x[0])):
    print(k, v)
