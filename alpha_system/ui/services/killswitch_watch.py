"""Official-host watch for kill-switch T2 / thesis — candidates, not scores.

Polls allowlisted RSS (금융위 등). Does not set fired/damage. Does not write
target_portfolio.csv. Empty search is not proof of absence.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from alpha_system.journal import append_record
from alpha_system.ui.services.weekly_qual_report import (
    T2_EVENT_LABELS,
    T2_TRUE_HOST_SUFFIXES,
    t2_true_source_allowed,
)

WATCH_FILENAME = "killswitch_watch.json"
WATCH_UA = "SAA-alpha-v3/1.0 (killswitch-watch; official-rss-only)"
THESIS_EVENT_ID = "thesis"
DEFAULT_LOOKBACK_DAYS = 180
MSCI_LOOKBACK_DAYS = 400
MAX_HITS_PER_EVENT = 8
STALE_HOURS = 24

# Official RSS / listing pages on allowlisted hosts only. No news aggregators.
WATCH_FEEDS: tuple[dict[str, str], ...] = (
    {
        "id": "fsc_press",
        "kind": "rss",
        "url": "https://www.fsc.go.kr/about/fsc_bbs_rss/?fid=0111",
        "label": "금융위 보도자료",
    },
    {
        "id": "fsc_explain",
        "kind": "rss",
        "url": "https://www.fsc.go.kr/about/fsc_bbs_rss/?fid=0112",
        "label": "금융위 보도설명",
    },
    {
        "id": "fsc_notice",
        "kind": "rss",
        "url": "https://www.fsc.go.kr/about/fsc_bbs_rss/?fid=0114",
        "label": "금융위 공지",
    },
    {
        "id": "msci_ir_feed",
        "kind": "rss",
        "url": "https://ir.msci.com/rss/news-releases.xml",
        "label": "MSCI IR 보도",
    },
)

# All groups must match (any token in a group). Case-insensitive substring.
_EVENT_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "commercial_code_enforcement_decrees": (
        ("상법",),
        ("시행령", "시행규칙", "주주환원", "자기주식", "배당", "이사회", "집중투표"),
    ),
    "msci_dm_index_inclusion_confirmed": (
        (
            "market classification",
            "시장분류",
            "시장 분류",
            "developed market",
            "선진시장",
            "선진국 편입",
            "dm inclusion",
        ),
    ),
    "ifrs18_domestic_adoption_schedule_confirmed": (
        (
            "ifrs 18",
            "ifrs18",
            "ifrs 1118",
            "k-ifrs 1118",
            "제1118호",
            "1118호",
            "재무제표의 표시와 공시",
            "표시와 공시",
        ),
    ),
    THESIS_EVENT_ID: (
        ("상법", "주주환원", "밸류업", "기업가치"),
        ("유예", "후퇴", "철회", "폐지", "연기", "백지화", "축소"),
    ),
}

MANUAL_SEARCH_LINKS: tuple[tuple[str, str], ...] = (
    ("전자관보 검색", "https://gwanbo.go.kr/user/search/searchDetail.do"),
    ("법령 검색", "https://www.law.go.kr/"),
    ("MSCI IR 보도", "https://ir.msci.com/investor-news"),
    ("금융위 보도자료", "https://www.fsc.go.kr/no010101"),
    ("회계기준원 보도", "https://www.kasb.or.kr/front/board/comm020List.do"),
)


@dataclass(frozen=True)
class WatchItem:
    title: str
    url: str
    published: str
    summary: str
    feed_id: str


@dataclass(frozen=True)
class WatchHit:
    event_id: str
    title: str
    url: str
    published: str
    feed_id: str
    note: str


@dataclass(frozen=True)
class FeedStatus:
    id: str
    label: str
    ok: bool
    n: int = 0
    error: str = ""


@dataclass
class WatchSnapshot:
    version: int = 1
    fetched_at: str = ""
    as_of: str = ""
    feeds: list[dict[str, Any]] = field(default_factory=list)
    hits: list[dict[str, Any]] = field(default_factory=list)

    def hit_models(self) -> tuple[WatchHit, ...]:
        out: list[WatchHit] = []
        for raw in self.hits:
            try:
                out.append(
                    WatchHit(
                        event_id=str(raw.get("event_id") or ""),
                        title=str(raw.get("title") or ""),
                        url=str(raw.get("url") or ""),
                        published=str(raw.get("published") or ""),
                        feed_id=str(raw.get("feed_id") or ""),
                        note=str(raw.get("note") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
        return tuple(h for h in out if h.event_id and h.url)


def watch_path(root: Path) -> Path:
    return Path(root) / "data" / WATCH_FILENAME


def load_watch(root: Path) -> WatchSnapshot | None:
    path = watch_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return WatchSnapshot(
        version=int(data.get("version") or 1),
        fetched_at=str(data.get("fetched_at") or ""),
        as_of=str(data.get("as_of") or ""),
        feeds=list(data.get("feeds") or []),
        hits=list(data.get("hits") or []),
    )


def watch_is_stale(snap: WatchSnapshot | None, *, hours: int = STALE_HOURS) -> bool:
    if snap is None or not snap.fetched_at:
        return True
    fetched = _parse_iso(snap.fetched_at)
    if fetched is None:
        return True
    now = datetime.now(timezone.utc)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return now - fetched > timedelta(hours=hours)


def event_label(event_id: str) -> str:
    if event_id == THESIS_EVENT_ID:
        return "논지 훼손"
    return T2_EVENT_LABELS.get(event_id, event_id)


def _parse_iso(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _norm_blob(title: str, summary: str) -> str:
    return re.sub(r"\s+", " ", f"{title} {summary}".lower())


def matches_event(event_id: str, *, title: str, summary: str) -> bool:
    groups = _EVENT_GROUPS.get(event_id)
    if not groups:
        return False
    blob = _norm_blob(title, summary)
    return all(any(token.lower() in blob for token in group) for group in groups)


def _host_allowed(url: str) -> bool:
    return t2_true_source_allowed((url,))


def _parse_pub(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError, IndexError):
        pass
    iso = _parse_iso(text)
    if iso is not None and iso.tzinfo is None:
        return iso.replace(tzinfo=timezone.utc)
    return iso


def _within_lookback(published: datetime | None, event_id: str, *, as_of: date) -> bool:
    if published is None:
        return True
    days = MSCI_LOOKBACK_DAYS if event_id == "msci_dm_index_inclusion_confirmed" else DEFAULT_LOOKBACK_DAYS
    cutoff = datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=days)
    pub = published if published.tzinfo else published.replace(tzinfo=timezone.utc)
    return pub >= cutoff


def parse_feed_xml(raw: bytes, *, feed_id: str, base_url: str = "") -> tuple[WatchItem, ...]:
    """RSS 2.0 or Atom. Relative links resolved against base_url."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"RSS 파싱 실패: {exc}") from exc
    items: list[WatchItem] = []
    nodes = list(root.findall(".//item")) + list(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
    if not nodes:
        nodes = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
    for node in nodes:
        fields: dict[str, str] = {}
        href = ""
        for child in list(node):
            local = child.tag.rsplit("}", 1)[-1]
            if local == "link":
                href = (child.get("href") or "").strip() or href
                text = "".join(child.itertext()).strip()
                if text.startswith("http"):
                    href = text
            elif local in {"title", "description", "summary", "pubDate", "published", "updated"}:
                fields[local] = "".join(child.itertext()).strip()
        title = fields.get("title") or ""
        url = href or fields.get("link") or ""
        if url and not url.startswith("http") and base_url:
            url = urljoin(base_url, url)
        published = fields.get("pubDate") or fields.get("published") or fields.get("updated") or ""
        summary = fields.get("description") or fields.get("summary") or ""
        if title and url:
            items.append(
                WatchItem(
                    title=title[:240],
                    url=url,
                    published=published,
                    summary=re.sub(r"<[^>]+>", " ", summary)[:800],
                    feed_id=feed_id,
                )
            )
    return tuple(items)


def _fetch_bytes(url: str, *, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": WATCH_UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"네트워크: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ValueError("타임아웃") from exc


def fetch_feed_items(feed: Mapping[str, str]) -> tuple[WatchItem, ...]:
    raw = _fetch_bytes(str(feed["url"]))
    return parse_feed_xml(raw, feed_id=str(feed["id"]), base_url=str(feed["url"]))


def collect_hits(
    items: Sequence[WatchItem],
    *,
    as_of: date,
    event_ids: Sequence[str],
) -> tuple[WatchHit, ...]:
    wanted = list(dict.fromkeys([*event_ids, THESIS_EVENT_ID]))
    buckets: dict[str, list[WatchHit]] = {eid: [] for eid in wanted}
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not _host_allowed(item.url):
            continue
        pub_dt = _parse_pub(item.published)
        for eid in wanted:
            if not matches_event(eid, title=item.title, summary=item.summary):
                continue
            if not _within_lookback(pub_dt, eid, as_of=as_of):
                continue
            key = (eid, item.url)
            if key in seen:
                continue
            seen.add(key)
            host = (urlparse(item.url).hostname or "").lower()
            note = f"키워드 후보 · 확정 아님 · {host}"
            buckets[eid].append(
                WatchHit(
                    event_id=eid,
                    title=item.title,
                    url=item.url,
                    published=item.published,
                    feed_id=item.feed_id,
                    note=note,
                )
            )
    hits: list[WatchHit] = []
    for eid in wanted:
        hits.extend(buckets[eid][:MAX_HITS_PER_EVENT])
    return tuple(hits)


def refresh_killswitch_watch(
    root: Path,
    *,
    as_of: date | None = None,
    event_ids: Sequence[str] | None = None,
    journal_path: Path | None = None,
    fetch_items=fetch_feed_items,
) -> WatchSnapshot:
    """Fetch official feeds, keep keyword hits, persist. Never fires gates."""
    day = as_of or date.today()
    ids = (
        list(event_ids)
        if event_ids is not None
        else [
            "commercial_code_enforcement_decrees",
            "msci_dm_index_inclusion_confirmed",
            "ifrs18_domestic_adoption_schedule_confirmed",
        ]
    )
    feed_rows: list[FeedStatus] = []
    gathered: list[WatchItem] = []
    for feed in WATCH_FEEDS:
        try:
            items = tuple(fetch_items(feed))
            gathered.extend(items)
            feed_rows.append(
                FeedStatus(id=str(feed["id"]), label=str(feed["label"]), ok=True, n=len(items))
            )
        except (ValueError, OSError) as exc:
            feed_rows.append(
                FeedStatus(
                    id=str(feed["id"]),
                    label=str(feed["label"]),
                    ok=False,
                    error=str(exc)[:160],
                )
            )
    hits = collect_hits(gathered, as_of=day, event_ids=ids)
    snap = WatchSnapshot(
        version=1,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        as_of=day.isoformat(),
        feeds=[asdict(row) for row in feed_rows],
        hits=[asdict(h) for h in hits],
    )
    path = watch_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(snap), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok_n = sum(1 for row in feed_rows if row.ok)
    append_record(
        action_kind="KILLSWITCH_WATCH",
        as_of=day,
        subject="killswitch",
        rationale=f"공식 RSS 탐색 · 피드 {ok_n}/{len(feed_rows)} · 후보 {len(hits)}건",
        payload={
            "path": str(path),
            "hit_n": len(hits),
            "feeds_ok": ok_n,
            "feeds_fail": len(feed_rows) - ok_n,
        },
        journal_path=journal_path,
    )
    return snap


def recent_hit_count(snap: WatchSnapshot | None) -> int:
    if snap is None:
        return 0
    return len(snap.hit_models())
