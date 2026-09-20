"""Official RSS kill-switch watch — candidates only, no fired flags."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from alpha_system.journal import clear_entries, list_entries
from alpha_system.ui.services.killswitch_watch import (
    THESIS_EVENT_ID,
    WATCH_FEEDS,
    WatchItem,
    WatchSnapshot,
    collect_hits,
    matches_event,
    parse_feed_xml,
    refresh_killswitch_watch,
    watch_is_stale,
    watch_path,
)


_FSC_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>상법 시행령 일부개정</title>
<link>https://www.fsc.go.kr/no010101/1001</link>
<description>주주환원</description>
<pubDate>Mon, 31 Aug 2026 00:00:00 GMT</pubDate>
</item>
<item>
<title>IFRS 18 확정 고시</title>
<link>https://www.fsc.go.kr/no010101/1002</link>
<pubDate>Mon, 31 Aug 2026 00:00:00 GMT</pubDate>
</item>
<item>
<title>밸류업 제도 유예</title>
<link>https://www.fsc.go.kr/no010101/1003</link>
<description>주주환원 밸류업 후퇴</description>
<pubDate>Mon, 31 Aug 2026 00:00:00 GMT</pubDate>
</item>
<item>
<title>군장병 금융교육</title>
<link>https://www.fsc.go.kr/no010101/1004</link>
<pubDate>Mon, 31 Aug 2026 00:00:00 GMT</pubDate>
</item>
<item>
<title>IFRS 18 신문</title>
<link>https://www.fnnews.com/news/x</link>
<pubDate>Mon, 31 Aug 2026 00:00:00 GMT</pubDate>
</item>
<item>
<title>상법 시행령 뉴스</title>
<link>https://news.google.com/rss/articles/abc</link>
<pubDate>Mon, 31 Aug 2026 00:00:00 GMT</pubDate>
</item>
</channel></rss>
""".encode("utf-8")


def test_feeds_are_official_hosts_only() -> None:
    assert WATCH_FEEDS
    joined = " ".join(f["url"].lower() for f in WATCH_FEEDS)
    assert "news.google" not in joined
    assert "google.com/rss" not in joined
    assert all(
        any(h in f["url"] for h in ("fsc.go.kr", "msci.com"))
        for f in WATCH_FEEDS
    )
    msci = next(f for f in WATCH_FEEDS if f["id"] == "msci_ir_feed")
    assert msci["url"].endswith("/rss/news-releases.xml")
    assert "PressRelease.svc" not in msci["url"]


def test_parse_rss_and_keyword_hits() -> None:
    items = parse_feed_xml(_FSC_RSS, feed_id="fsc_press")
    assert len(items) == 6
    hits = collect_hits(
        items,
        as_of=date(2026, 8, 31),
        event_ids=[
            "commercial_code_enforcement_decrees",
            "msci_dm_index_inclusion_confirmed",
            "ifrs18_domestic_adoption_schedule_confirmed",
        ],
    )
    by = {h.event_id: h for h in hits}
    assert "commercial_code_enforcement_decrees" in by
    assert by["commercial_code_enforcement_decrees"].url.endswith("1001")
    assert "ifrs18_domestic_adoption_schedule_confirmed" in by
    assert by["ifrs18_domestic_adoption_schedule_confirmed"].url.endswith("1002")
    assert THESIS_EVENT_ID in by
    assert all("fnnews" not in h.url for h in hits)
    assert all("news.google" not in h.url for h in hits)
    assert all(h.event_id != "msci_dm_index_inclusion_confirmed" for h in hits)


def test_msci_classification_title_without_korea() -> None:
    assert matches_event(
        "msci_dm_index_inclusion_confirmed",
        title="Results of the MSCI 2026 Market Classification Review",
        summary="",
    )
    assert not matches_event(
        "msci_dm_index_inclusion_confirmed",
        title="MSCI Equity Indexes August 2026 Index Review",
        summary="",
    )


def test_ifrs17_does_not_match_ifrs18() -> None:
    assert not matches_event(
        "ifrs18_domestic_adoption_schedule_confirmed",
        title="IFRS 17 계리 가이드라인",
        summary="",
    )


def test_old_items_dropped() -> None:
    old = WatchItem(
        title="Results of the MSCI 2011 Market Classification Review",
        url="https://ir.msci.com/news/2011",
        published="Tue, 21 Jun 2011 07:00:00 GMT",
        summary="",
        feed_id="msci",
    )
    hits = collect_hits(
        (old,),
        as_of=date(2026, 8, 31),
        event_ids=["msci_dm_index_inclusion_confirmed"],
    )
    assert hits == ()


def test_refresh_persists_without_firing(tmp_path: Path) -> None:
    clear_entries()
    (tmp_path / "data").mkdir()

    def fake_fetch(feed):
        if feed["id"] == "fsc_press":
            return parse_feed_xml(_FSC_RSS, feed_id="fsc_press")
        raise ValueError("HTTP 500")

    snap = refresh_killswitch_watch(
        tmp_path,
        as_of=date(2026, 8, 31),
        fetch_items=fake_fetch,
        journal_path=tmp_path / "j.jsonl",
    )
    assert watch_path(tmp_path).exists()
    assert snap.hits
    assert all("fired" not in h for h in snap.hits)
    assert any(not f["ok"] for f in snap.feeds)
    assert list_entries(action_kind="KILLSWITCH_WATCH")
    assert not watch_is_stale(snap, hours=24)
    stale = WatchSnapshot(
        version=1,
        fetched_at=datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat(),
        as_of="2026-08-01",
        feeds=[],
        hits=[],
    )
    assert watch_is_stale(stale, hours=24)
    clear_entries()
