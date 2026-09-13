"""The merge model's canonical cases (ticket 12): wholesale replace,
duplicate guids, age-out, ordering, cap, and byte-stable failure."""

from datetime import datetime, timedelta, timezone

import feeds.fetch as fetch_mod
import feeds.publish as publish_mod
from feeds.merge import merge
from feeds.model import FetchOutcome

from conftest import BUILT_AT, make_item


def test_ordering_pubdate_desc_tiebreak_guid_asc():
    upstream = [
        make_item("b", pub=BUILT_AT - timedelta(hours=1)),
        make_item("a", pub=BUILT_AT - timedelta(hours=1)),  # tie with "b"
        make_item("z", pub=BUILT_AT - timedelta(minutes=1)),
    ]
    merged = merge(upstream, [], BUILT_AT)
    assert [i.guid for i in merged] == ["z", "a", "b"]


def test_cap_100_keeps_newest():
    upstream = [
        make_item(str(n), pub=BUILT_AT - timedelta(hours=n)) for n in range(150)
    ]
    merged = merge(upstream, [], BUILT_AT)
    assert len(merged) == 100
    assert merged[0].guid == "0"          # newest
    assert merged[-1].guid == "99"        # cap cuts the oldest
    assert "149" not in [i.guid for i in merged]


def test_age_out_drops_items_older_than_30_days():
    old = make_item("old", pub=BUILT_AT - timedelta(days=31))
    edge = make_item("edge", pub=BUILT_AT - timedelta(days=29))
    undated = make_item("undated")
    merged = merge([], [old, edge, undated], BUILT_AT)
    assert [i.guid for i in merged] == ["edge", "undated"]


def test_duplicate_guid_keeps_first_occurrence():
    upstream = [make_item("same", title="fresh from upstream")]
    predecessor = [make_item("same", title="stale from predecessor")]
    merged = merge(upstream, predecessor, BUILT_AT)
    assert len(merged) == 1
    assert merged[0].title == "fresh from upstream"


def test_wholesale_replace_never_field_merge():
    upstream = [
        make_item("same", title="New title", description="New description",
                  link="https://example.com/new")
    ]
    predecessor = [
        make_item("same", title="Old title", description="Old description",
                  link="https://example.com/old")
    ]
    merged = merge(upstream, predecessor, BUILT_AT)
    assert len(merged) == 1
    assert merged[0].title == "New title"
    assert merged[0].description == "New description"
    assert merged[0].link == "https://example.com/new"


def test_missing_pubdate_sorts_last():
    upstream = [
        make_item("undated"),
        make_item("dated", pub=BUILT_AT - timedelta(days=2)),
    ]
    merged = merge(upstream, [], BUILT_AT)
    assert [i.guid for i in merged] == ["dated", "undated"]


# --- failure policy (publish level, offline via fakes) ---

PREDECESSOR_BYTES = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<rss version="2.0"><channel><title>Reddit r/rva</title>'
    b"<link>https://www.reddit.com/r/rva</link>"
    b"<description>desc</description>"
    b"<lastBuildDate>Sun, 13 Sep 2026 11:02:33 +0000</lastBuildDate>"
    b"<item><title>An old post</title>"
    b"<link>https://www.reddit.com/r/rva/comments/old/</link>"
    b"<guid isPermaLink=\"false\">t3_old</guid>"
    b"<pubDate>Sun, 13 Sep 2026 10:00:00 +0000</pubDate>"
    b"<description>body</description></item>"
    b"</channel></rss>\n"
)


def _patch_fetch(monkeypatch, outcome, predecessor):
    monkeypatch.setattr(fetch_mod, "fetch", lambda source: outcome)
    monkeypatch.setattr(fetch_mod, "fetch_predecessor", lambda url: predecessor)


def _hosted(registry, sid="reddit-rva"):
    return [s for s in registry.hosted() if s.id == sid][0]


def test_failed_fetch_reemits_predecessor_byte_identical(registry, monkeypatch):
    _patch_fetch(monkeypatch, FetchOutcome(items=[], error="HTTP 403"), PREDECESSOR_BYTES)
    xml, status = publish_mod.run_source(_hosted(registry), registry.feed, BUILT_AT)
    assert xml == PREDECESSOR_BYTES                      # byte for byte
    assert status.state == "stale"
    assert status.error == "HTTP 403"
    assert status.last_build == "Sun, 13 Sep 2026 11:02:33 +0000"  # last SUCCESSFUL fetch


def test_failed_fetch_without_predecessor_emits_empty_channel(registry, monkeypatch):
    _patch_fetch(monkeypatch, FetchOutcome(items=[], error="HTTP 500"), None)
    xml, status = publish_mod.run_source(_hosted(registry), registry.feed, BUILT_AT)
    assert status.state == "failed"
    assert b"<item>" not in xml
    assert b"<lastBuildDate>" not in xml    # never a successful fetch: nothing honest to stamp
    assert status.last_build == ""


def test_successful_fetch_merges_against_predecessor(registry, monkeypatch):
    from feeds.model import Item
    fresh = Item(
        title="A fresh post",
        link="https://www.reddit.com/r/rva/comments/fresh/",
        guid="t3_fresh",
        published=BUILT_AT,
        published_raw="Sun, 13 Sep 2026 12:00:00 +0000",
        description="<p>fresh body</p>",
    )
    _patch_fetch(monkeypatch, FetchOutcome(items=[fresh]), PREDECESSOR_BYTES)
    xml, status = publish_mod.run_source(_hosted(registry), registry.feed, BUILT_AT)
    assert status.state == "ok"
    assert status.item_count == 2        # fresh item + predecessor's item
    body = xml.decode()
    assert body.index("A fresh post") < body.index("An old post")  # newest first
