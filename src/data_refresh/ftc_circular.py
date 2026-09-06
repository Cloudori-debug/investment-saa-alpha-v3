"""Fair Trade Commission circular-ownership hits via data.go.kr REST.

Official OpenAPI (XML), not HTML scraping. Fail-open when the key is missing
or the portal is down. Does not write target_portfolio.csv or change QVM scores.

Only True flags are emitted. Names not on the latest circular-group list stay
unmeasured (None), so the Hakedaka gate does not mass-reject the universe.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

FTC_BASE = "https://apis.data.go.kr/1130000"
ROTAT_PATH = "/grupRotatInvstmntList/grupRotatInvstmntListApi"
GROUP_PATH = "/appnGroupSttusList/appnGroupSttusListApi"
AFFILIATE_PATHS = (
    "/appnGroupCmpnyList/appnGroupCmpnyListApi",
    "/appnGroupCmpnySttusList/appnGroupCmpnySttusListApi",
)
PUBLIC_YM_PATHS = (
    "/publicYmList/publicYmListApi",
    "/publicYmListApi/publicYmListApi",
)
CACHE_NAME = "ftc_circular.json"
UA = "saa-alpha-screener/ftc-circular"


def _tk(raw: object) -> str:
    text = str(raw or "").strip()
    return text.zfill(6) if text.isdigit() else text


def normalize_service_key(raw: str) -> str:
    """data.go.kr shows encoding+decoding keys. Decoding is the raw secret.

    If the encoding key (already percent-escaped) is pasted, unquote once so
    urlencode does not double-escape and trigger HTTP 403.
    """
    key = (raw or "").strip()
    for _ in range(2):
        if "%" not in key:
            break
        decoded = urllib.parse.unquote(key)
        if decoded == key:
            break
        key = decoded
    return key


GetUrl = Callable[[str], bytes]


class FtcCredentialsError(RuntimeError):
    pass


class FtcApiError(RuntimeError):
    pass


@dataclass
class FtcRefreshResult:
    ok: bool
    tickers: list[str] = field(default_factory=list)
    groups: int = 0
    presentn_ym: str = ""
    detail: str = ""
    cache_path: str = ""


def cache_path(root: Path) -> Path:
    return Path(root) / "data" / "cache" / CACHE_NAME


def get_data_go_kr_key(data_dir: Path | None = None) -> str:
    if data_dir is not None:
        from src.settings.user_secrets import apply_secrets_to_env

        apply_secrets_to_env(data_dir)
    key = (
        os.environ.get("DATA_GO_KR_API_KEY", "").strip()
        or os.environ.get("DATA_API_KEY", "").strip()
    )
    if not key and data_dir is not None:
        from src.settings.user_secrets import load_user_secrets

        key = load_user_secrets(data_dir).data_go_kr_api_key
    key = normalize_service_key(key)
    if not key:
        raise FtcCredentialsError(
            "공공데이터포털 인증키가 필요합니다. 설정에 data.go.kr 일반 인증키를 넣으세요."
        )
    return key


def normalize_corp_name(raw: object) -> str:
    text = str(raw or "")
    text = text.replace("㈜", "").replace("(주)", "").replace("（주）", "")
    text = re.sub(r"주식회사|유한회사", "", text)
    text = re.sub(r"[\s\-_.]", "", text)
    return text.strip().lower()


def _local(tag: str) -> str:
    return tag.split("}")[-1] if tag else ""


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return str(node.text).strip()


_XML_META = frozenset(
    {
        "numOfRows",
        "pageNo",
        "resultCode",
        "resultMsg",
        "totalCount",
        "header",
        "body",
        "items",
        "item",
        "response",
    }
)
_XML_ROW_FIELDS = frozenset(
    {
        "unityGrupNm",
        "unityGrupCode",
        "entrprsNm",
        "cmpnyNm",
        "unityCmpnyNm",
        "repreCmpny",
        "rotatInvstmntLoopCo",
        "loopCo",
    }
)
# Listed names that do not match FTC group titles 1:1.
_NAME_ALIASES = {
    "현대자동차": "현대차",
    "현대차": "현대자동차",
}


def _rows_from_named_lists(root: ET.Element) -> list[dict[str, str]]:
    """data.go.kr FTC XML uses <grupRotatInvstmnt>, not generic <item>."""
    rows: list[dict[str, str]] = []
    for node in root.iter():
        if node is root or _local(node.tag) in _XML_META:
            continue
        row = {_local(child.tag): _text(child) for child in list(node)}
        if row.keys() & _XML_ROW_FIELDS:
            rows.append(row)
    return rows


def parse_items_xml(raw: bytes) -> tuple[str, str, int, list[dict[str, str]]]:
    """Return (result_code, result_msg, total_count, item dicts)."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise FtcApiError(f"FTC XML parse failed: {exc}") from exc
    code = ""
    msg = ""
    total = 0
    items: list[dict[str, str]] = []
    for node in root.iter():
        name = _local(node.tag)
        if name == "resultCode" and not code:
            code = _text(node)
        elif name == "resultMsg" and not msg:
            msg = _text(node)
        elif name == "totalCount" and not total:
            try:
                total = int(_text(node) or "0")
            except ValueError:
                total = 0
        elif name == "item":
            row = {_local(child.tag): _text(child) for child in list(node)}
            if row:
                items.append(row)
    if not items:
        items = _rows_from_named_lists(root)
    return code, msg, total, items


def _http_get(url: str, *, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise FtcApiError(f"FTC HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise FtcApiError(f"FTC network error: {exc}") from exc


def ftc_get(
    path: str,
    params: Mapping[str, Any],
    *,
    api_key: str,
    get_url: GetUrl | None = None,
    timeout: int = 30,
) -> tuple[str, str, int, list[dict[str, str]]]:
    query = dict(params)
    query["serviceKey"] = normalize_service_key(api_key)
    url = f"{FTC_BASE}{path}?{urllib.parse.urlencode(query)}"
    raw = (get_url or (lambda u: _http_get(u, timeout=timeout)))(url)
    # Some gateways wrap a JSON error; surface it.
    head = raw[:32].lstrip().lower()
    if head.startswith(b"{") or head.startswith(b"["):
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FtcApiError("FTC JSON error payload") from exc
        raise FtcApiError(str(payload)[:240])
    code, msg, total, items = parse_items_xml(raw)
    if code and code not in {"00", "000", "0"}:
        raise FtcApiError(f"FTC status {code}: {msg or 'unknown'}")
    return code, msg, total, items


def _paginate(
    path: str,
    base_params: Mapping[str, Any],
    *,
    api_key: str,
    get_url: GetUrl | None = None,
    page_size: int = 100,
    max_pages: int = 40,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    total = 0
    for page in range(1, max_pages + 1):
        params = {**dict(base_params), "pageNo": page, "numOfRows": page_size}
        _code, _msg, total, items = ftc_get(path, params, api_key=api_key, get_url=get_url)
        rows.extend(items)
        if not items or len(rows) >= total:
            break
    return rows


def candidate_presentn_yms(*, today: date | None = None) -> list[str]:
    """May designation + Aug/Sep stock-ownership release windows, then prior years."""
    day = today or date.today()
    out: list[str] = []
    for year in range(day.year, day.year - 5, -1):
        for month in (9, 8, 7, 5, 4, 1):
            stamp = f"{year}{month:02d}"
            if stamp not in out:
                out.append(stamp)
    return out


def _loop_count(row: Mapping[str, str]) -> int:
    raw = row.get("rotatInvstmntLoopCo") or row.get("loopCo") or "0"
    try:
        return int(float(str(raw).replace(",", "") or "0"))
    except ValueError:
        return 0


def _build_name_index(root: Path) -> dict[str, str]:
    """normalized name → ticker from universe + DART corp cache."""
    index: dict[str, str] = {}
    universe = Path(root) / "data" / "universe.csv"
    if universe.exists():
        try:
            import csv

            with universe.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    ticker = _tk(row.get("ticker"))
                    name = normalize_corp_name(row.get("name"))
                    if ticker and name and name not in index:
                        index[name] = ticker
        except (OSError, csv.Error):
            pass
    dart = Path(root) / "data" / "cache" / "dart_corp_codes.csv"
    if dart.exists():
        try:
            import csv

            with dart.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    ticker = _tk(row.get("stock_code") or row.get("ticker"))
                    name = normalize_corp_name(row.get("corp_name") or row.get("name"))
                    if ticker and name and name not in index:
                        index[name] = ticker
        except (OSError, csv.Error):
            pass
    return index


def _lookup_ticker(raw: object, name_index: Mapping[str, str]) -> str:
    key = normalize_corp_name(raw)
    if not key:
        return ""
    ticker = name_index.get(key) or ""
    if ticker:
        return ticker
    alias = _NAME_ALIASES.get(key) or _NAME_ALIASES.get(str(raw or "").strip())
    if alias:
        ticker = name_index.get(normalize_corp_name(alias)) or ""
        if ticker:
            return ticker
    stripped = re.sub(r"그룹$", "", key)
    if stripped != key:
        ticker = name_index.get(stripped) or ""
        if ticker:
            return ticker
    return ""


def map_names_to_tickers(names: list[str], name_index: Mapping[str, str]) -> tuple[list[str], list[str]]:
    hit: list[str] = []
    miss: list[str] = []
    seen: set[str] = set()
    for raw in names:
        ticker = _lookup_ticker(raw, name_index)
        if ticker:
            if ticker not in seen:
                seen.add(ticker)
                hit.append(ticker)
        elif normalize_corp_name(raw):
            miss.append(str(raw).strip())
    return hit, miss


def load_ftc_circular_tickers(root: Path) -> set[str]:
    path = cache_path(root)
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return set()
    if not isinstance(raw, dict):
        return set()
    out: set[str] = set()
    for item in raw.get("tickers") or []:
        ticker = _tk(item)
        if ticker:
            out.add(ticker)
    return out


def _pick_ym(
    api_key: str,
    *,
    get_url: GetUrl | None,
    today: date | None,
) -> str:
    for path in PUBLIC_YM_PATHS:
        try:
            rows = _paginate(path, {}, api_key=api_key, get_url=get_url, page_size=50)
        except FtcApiError:
            continue
        stamps: list[str] = []
        for row in rows:
            for key in ("presentnYm", "presentnYear", "publicYm", "stdrYm"):
                val = str(row.get(key) or "").strip()
                if len(val) >= 6 and val[:6].isdigit():
                    stamps.append(val[:6])
                    break
        for stamp in sorted(set(stamps), reverse=True):
            try:
                _c, _m, _total, items = ftc_get(
                    ROTAT_PATH,
                    {"pageNo": 1, "numOfRows": 1, "presentnYm": stamp},
                    api_key=api_key,
                    get_url=get_url,
                )
            except FtcApiError:
                continue
            if items:
                return stamp
    for ym in candidate_presentn_yms(today=today):
        try:
            _c, _m, total, items = ftc_get(
                ROTAT_PATH,
                {"pageNo": 1, "numOfRows": 1, "presentnYm": ym},
                api_key=api_key,
                get_url=get_url,
            )
        except FtcApiError:
            continue
        if items:
            return ym
    return candidate_presentn_yms(today=today)[0]


def refresh_ftc_circular(
    root: Path,
    *,
    api_key: str | None = None,
    get_url: GetUrl | None = None,
    today: date | None = None,
) -> FtcRefreshResult:
    """Pull FTC circular groups, map listed affiliates, cache True-only tickers."""
    root = Path(root)
    data_dir = root / "data"
    try:
        key = (api_key or "").strip() or get_data_go_kr_key(data_dir)
    except FtcCredentialsError as exc:
        return FtcRefreshResult(ok=False, detail=str(exc))
    try:
        ym = _pick_ym(key, get_url=get_url, today=today)
        rotat = _paginate(ROTAT_PATH, {"presentnYm": ym}, api_key=key, get_url=get_url)
        circular_groups = [row for row in rotat if _loop_count(row) > 0]
        if not circular_groups:
            return FtcRefreshResult(
                ok=False,
                presentn_ym=ym,
                detail=f"순환출자 목록 없음 ({ym})",
            )
        groups: list[dict[str, str]] = []
        group_error = ""
        year_keys = [ym]
        if len(ym) >= 4 and ym[:4] not in year_keys:
            year_keys.append(ym[:4])
        for year_key in year_keys:
            try:
                groups = _paginate(
                    GROUP_PATH,
                    {"presentnYear": year_key},
                    api_key=key,
                    get_url=get_url,
                )
            except FtcApiError as exc:
                group_error = str(exc)
                continue
            if groups:
                group_error = ""
                break
        by_name = {
            normalize_corp_name(row.get("unityGrupNm")): row
            for row in groups
            if row.get("unityGrupNm")
        }
        company_names: list[str] = []
        group_meta: list[dict[str, Any]] = []
        affiliate_path = ""
        for row in circular_groups:
            gname = str(row.get("unityGrupNm") or "").strip()
            meta = by_name.get(normalize_corp_name(gname), {})
            code = str(meta.get("unityGrupCode") or row.get("unityGrupCode") or "").strip()
            repre = str(meta.get("repreCmpny") or "").strip()
            if gname:
                company_names.append(gname)
            if repre:
                company_names.append(repre)
            loops = _loop_count(row)
            group_meta.append(
                {
                    "name": gname,
                    "code": code,
                    "loops": loops,
                    "representative": repre,
                }
            )
            if not code:
                continue
            if not affiliate_path:
                for cand in AFFILIATE_PATHS:
                    try:
                        probe = _paginate(
                            cand,
                            {"presentnYear": ym, "unityGrupCode": code},
                            api_key=key,
                            get_url=get_url,
                            page_size=20,
                        )
                    except FtcApiError:
                        continue
                    if probe:
                        affiliate_path = cand
                        for item in probe:
                            nm = item.get("entrprsNm") or item.get("cmpnyNm") or item.get("unityCmpnyNm")
                            if nm:
                                company_names.append(nm)
                        break
            elif affiliate_path:
                try:
                    affiliates = _paginate(
                        affiliate_path,
                        {"presentnYear": ym, "unityGrupCode": code},
                        api_key=key,
                        get_url=get_url,
                    )
                except FtcApiError:
                    affiliates = []
                for item in affiliates:
                    nm = item.get("entrprsNm") or item.get("cmpnyNm") or item.get("unityCmpnyNm")
                    if nm:
                        company_names.append(nm)
        name_index = _build_name_index(root)
        tickers, unmatched = map_names_to_tickers(company_names, name_index)
        payload = {
            "as_of": (today or date.today()).isoformat(),
            "presentn_ym": ym,
            "source": "data.go.kr/1130000 grupRotatInvstmntList + appnGroupSttusList",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "groups": group_meta,
            "tickers": tickers,
            "names_unmatched": unmatched[:80],
            "target_portfolio_written": False,
        }
        path = cache_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return FtcRefreshResult(
            ok=True,
            tickers=tickers,
            groups=len(group_meta),
            presentn_ym=ym,
            detail=(
                f"순환출자 집단 {len(group_meta)} · 상장 매칭 {len(tickers)}종"
                + (f" · 지정집단 API 생략({group_error})" if group_error else "")
            ),
            cache_path=str(path.relative_to(root)).replace("\\", "/"),
        )
    except FtcApiError as exc:
        return FtcRefreshResult(ok=False, detail=str(exc))
    except Exception as exc:
        return FtcRefreshResult(ok=False, detail=f"FTC refresh skipped: {exc}")
