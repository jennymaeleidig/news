"""RSS 2.0 emission: determinism, escaping, guid/permalink semantics,
pubDate normalization — and the committed fixture golden."""

from datetime import datetime, timezone

import pytest

from feeds.emit import emit
from feeds.fetch import parse_feed_bytes, parse_json_bytes
from feeds.merge import merge
from feeds.publish import run_source
from feeds.transform import filter_items

from conftest import BUILT_AT, make_item

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def test_emit_is_deterministic():
    items = [make_item("b", pub=BUILT_AT), make_item("a", pub=BUILT_AT)]
    first = emit("T", "https://example.com/", "desc", BUILT_AT, items)
    second = emit("T", "https://example.com/", "desc", BUILT_AT, items)
    assert first == second


def test_guid_permalink_attribute_only_when_not_the_link():
    permalink = [make_item("https://example.com/same", link="https://example.com/same")]
    xml = emit("T", "https://example.com/", "d", BUILT_AT, permalink)
    assert b"<guid>https://example.com/same</guid>" in xml      # no attribute

    distinct = [make_item("t3_abc", link="https://example.com/post/abc")]
    xml = emit("T", "https://example.com/", "d", BUILT_AT, distinct)
    assert b'<guid isPermaLink="false">t3_abc</guid>' in xml


def test_description_is_escaped_verbatim_html():
    items = [make_item("1", description='<p class="md">Tom &amp; Jerry <a href="https://x/">link</a></p>')]
    xml = emit("T", "https://example.com/", "d", BUILT_AT, items)
    # ElementTree escapes < > & in text; quotes stay raw in text nodes (valid XML).
    assert b'&lt;p class="md"&gt;Tom &amp;amp; Jerry' in xml


def test_pubdate_normalized_to_rfc2822_raw_fallback():
    dated = [make_item("1", pub=datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc))]
    xml = emit("T", "https://example.com/", "d", BUILT_AT, dated)
    assert b"<pubDate>Sun, 13 Sep 2026 10:00:00 +0000</pubDate>" in xml

    undated = [make_item("2")]
    undated[0].published_raw = "ish, someday"
    xml = emit("T", "https://example.com/", "d", BUILT_AT, undated)
    assert b"<pubDate>ish, someday</pubDate>" in xml


def test_last_build_date_is_built_at():
    xml = emit("T", "https://example.com/", "d", BUILT_AT, [])
    assert b"<lastBuildDate>Sun, 13 Sep 2026 12:00:00 +0000</lastBuildDate>" in xml


def test_last_build_date_omitted_when_no_fetch_ever_succeeded():
    # lastBuildDate means "last successful upstream fetch"; a feed that has
    # never succeeded has no such time, so it is omitted rather than faked
    # with the current run (ticket 11).
    xml = emit("T", "https://example.com/", "d", None, [])
    assert b"<lastBuildDate>" not in xml
    assert b"<channel>" in xml                      # still a valid empty channel


# --- fixture goldens: recorded upstream bytes through the real pipeline ---

def _fixtures():
    return sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())


@pytest.mark.parametrize("source_id", _fixtures())
def test_fixture_roundtrip(source_id, registry):
    """Upstream's own bytes in, the committed expected.xml out — the same
    mapping the live run uses, minus the network."""
    fixture = FIXTURES / source_id
    source = [s for s in registry.hosted() if s.id == source_id][0]

    snapshot = fixture / "upstream.json"
    if snapshot.exists():
        outcome = parse_json_bytes(snapshot.read_bytes(), source.strategy)
    else:
        snapshot = fixture / "upstream.xml"
        outcome = parse_feed_bytes(snapshot.read_bytes())
    assert outcome.ok, outcome.error

    items = filter_items(source, outcome.items)
    merged = merge(items, [], BUILT_AT)                     # first run: no predecessor
    xml = emit(source.name, source.site,
               registry.feed.channel_description(source), BUILT_AT, merged)

    assert xml == (fixture / "expected.xml").read_bytes()
