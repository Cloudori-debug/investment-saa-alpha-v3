"""Debug KOSIS CPI series values."""
from pathlib import Path

from src.data_refresh.kosis_client import fetch_kosis_series, kosis_yoy_pct
from src.data_refresh.tier2_refresh import _kosis_api_key
from src.data_refresh.kosis_tblid_discovery import kosis_search, parse_kosis_json

key = _kosis_api_key(Path("data"))
base = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

for kw in ["전년동월비", "소비자물가지수 등락률", "소비자물가지수(2020=100)"]:
    rows = kosis_search(key, kw)
    print("SEARCH", kw, "org101", len([r for r in rows if str(r.get('ORG_ID'))=='101']))
    for r in rows:
        if str(r.get("ORG_ID")) == "101":
            print(" ", r.get("TBL_ID"), r.get("TBL_NM"))

for tbl, itm, obj, label in [
    ("DT_1J22042", "ALL", "ALL", "cpi_rate"),
    ("DT_1J22042", "T10", "ALL", "cpi_rate_t10"),
    ("DT_1J22003", "ALL", "ALL", "cpi_index"),
    ("DT_1J22003", "T10", "ALL", "cpi_index_t10"),
    ("DT_1J22003", "T1", "ALL", "cpi_index_t1"),
]:
    r = fetch_kosis_series(base, api_key=key, org_id="101", tbl_id=tbl, itm_id=itm, obj_l1=obj, months_back=36)
    print("TBL", label, tbl, itm, obj, "err", r.error, "n", len(r.points), "last", r.last_period)
    if r.points:
        print("  head", [(p.period, p.value) for p in r.points[:6]])
        if len(r.points) >= 13:
            yoy, p = kosis_yoy_pct(r.points)
            print("  yoy_calc", yoy, p)

