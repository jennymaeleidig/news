"""The publication assembly: a fetch outcome and the predecessor's bytes go
in, published bytes and a run status come out. The failure policy lives here
(the rss-refactor ticket 11) and is exercised with values, not fakes."""

from feeds.model import FetchOutcome
from feeds.publish import run_source

from conftest import BUILT_AT, hosted_source, make_item

PREDECESSOR_BYTES = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<rss version="2.0"><channel><title>Reddit r/rva</title>'
    b"<link>https://www.reddit.com/r/rva</link>"
    b"<description>desc</description>"
    b"<lastBuildDate>Sun, 13 Sep 2026 11:02:33 +0000</lastBuildDate>"
    b"<item><title>An old post</title>"
    b"<link>https://www.reddit.com/r/rva/comments/old/</link>"
    b'<guid isPermaLink="false">t3_old</guid>'
    b"<pubDate>Sun, 13 Sep 2026 10:00:00 +0000</pubDate>"
    b"<description>body</description></item>"
    b"</channel></rss>\n"
)


def fresh_item():
    return make_item(
        "t3_fresh", BUILT_AT, title="A fresh item",
        link="https://www.reddit.com/r/rva/comments/fresh/",
        description="<p>fresh body</p>",
    )


def test_failed_fetch_reemits_predecessor_byte_identical(registry):
    xml, status = run_source(
        hosted_source(registry, "reddit-rva"), registry.feed, BUILT_AT,
        FetchOutcome(items=[], error="HTTP 403"), PREDECESSOR_BYTES,
    )
    assert xml == PREDECESSOR_BYTES                      # byte for byte
    assert status.source_id == "reddit-rva"
    assert status.state == "stale"
    assert status.error == "HTTP 403"
    assert status.last_build == "Sun, 13 Sep 2026 11:02:33 +0000"  # last SUCCESSFUL fetch
    assert "predecessor re-emitted unchanged" in status.note


def test_failed_fetch_without_predecessor_emits_empty_channel(registry):
    xml, status = run_source(
        hosted_source(registry, "reddit-rva"), registry.feed, BUILT_AT,
        FetchOutcome(items=[], error="HTTP 500"), None,
    )
    assert status.state == "failed"
    assert b"<item>" not in xml
    assert b"<lastBuildDate>" not in xml    # never a successful fetch: nothing honest to stamp
    assert status.last_build == ""


def test_successful_fetch_merges_against_predecessor(registry):
    xml, status = run_source(
        hosted_source(registry, "reddit-rva"), registry.feed, BUILT_AT,
        FetchOutcome(items=[fresh_item()]), PREDECESSOR_BYTES,
    )
    assert status.state == "ok"
    assert status.item_count == 2        # fresh item + predecessor's item
    body = xml.decode()
    assert body.index("A fresh item") < body.index("An old post")  # newest first


def test_successful_fetch_without_predecessor_publishes_upstream_only(registry):
    xml, status = run_source(
        hosted_source(registry, "reddit-rva"), registry.feed, BUILT_AT,
        FetchOutcome(items=[fresh_item()]), None,
    )
    assert status.state == "ok"
    assert status.item_count == 1
    assert b"An old post" not in xml


def test_a_non_fatal_fetch_note_reaches_the_run_status(registry):
    _, status = run_source(
        hosted_source(registry, "reddit-rva"), registry.feed, BUILT_AT,
        FetchOutcome(items=[], note="valid but empty channel — source declares skip days"),
        PREDECESSOR_BYTES,
    )
    assert status.state == "ok"
    assert status.note.startswith("valid but empty channel")
