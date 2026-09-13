"""The publication assembly: a fetch outcome and the predecessor's bytes go
in, published bytes and the source's Run come out. The failure policy lives
here (the rss-refactor ticket 11) and is exercised with values, not fakes.

The sources are built by hand — a passthrough RSS upstream — so the
assembly's contract is what these tests pin, not the owner's current
subscription list.
"""

from feeds import store
from feeds.model import FetchOutcome
from feeds.publish import generate_site, run_source
from feeds.run import RunState
from feeds.strategies.base import rss_headers

from conftest import (
    BUILT_AT,
    TEST_FEED,
    RecordedSleep,
    make_item,
    registry_of,
    rss_source,
)

PREDECESSOR_BYTES = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<rss version="2.0"><channel><title>Alpha</title>'
    b"<link>https://site.example/</link>"
    b"<description>desc</description>"
    b"<lastBuildDate>Sun, 13 Sep 2026 11:02:33 +0000</lastBuildDate>"
    b"<item><title>An old item</title>"
    b"<link>https://up.example/alpha/old</link>"
    b'<guid isPermaLink="false">guid_old</guid>'
    b"<pubDate>Sun, 13 Sep 2026 10:00:00 +0000</pubDate>"
    b"<description>body</description></item>"
    b"</channel></rss>\n"
)


def fresh_item():
    return make_item(
        "guid_fresh", BUILT_AT, title="A fresh item",
        link="https://up.example/alpha/fresh",
        description="<p>fresh body</p>",
    )


def test_failed_fetch_reemits_predecessor_byte_identical():
    source = rss_source()
    xml, run = run_source(
        source, TEST_FEED, BUILT_AT,
        FetchOutcome(items=[], error="HTTP 403"), PREDECESSOR_BYTES,
    )
    assert xml == PREDECESSOR_BYTES                      # byte for byte
    assert run.source_id == "alpha"
    assert run.state is RunState.STALE
    assert run.error == "HTTP 403"
    assert run.last_build == "Sun, 13 Sep 2026 11:02:33 +0000"  # last SUCCESSFUL fetch
    assert "predecessor re-emitted unchanged" in run.note


def test_failed_fetch_without_predecessor_emits_empty_channel():
    source = rss_source()
    xml, run = run_source(
        source, TEST_FEED, BUILT_AT,
        FetchOutcome(items=[], error="HTTP 500"), None,
    )
    assert run.state is RunState.FAILED
    assert b"<item>" not in xml
    assert b"<lastBuildDate>" not in xml    # never a successful fetch: nothing honest to stamp
    assert run.last_build == ""


def test_successful_fetch_merges_against_predecessor():
    source = rss_source()
    xml, run = run_source(
        source, TEST_FEED, BUILT_AT,
        FetchOutcome(items=[fresh_item()]), PREDECESSOR_BYTES,
    )
    assert run.state is RunState.OK
    assert run.item_count == 2        # fresh item + predecessor's item
    body = xml.decode()
    assert body.index("A fresh item") < body.index("An old item")  # newest first


def test_successful_fetch_without_predecessor_publishes_upstream_only():
    source = rss_source()
    xml, run = run_source(
        source, TEST_FEED, BUILT_AT,
        FetchOutcome(items=[fresh_item()]), None,
    )
    assert run.state is RunState.OK
    assert run.item_count == 1
    assert b"An old item" not in xml


def test_a_non_fatal_fetch_note_reaches_the_run():
    source = rss_source()
    _, run = run_source(
        source, TEST_FEED, BUILT_AT,
        FetchOutcome(items=[], note="valid but empty channel — source declares skip days"),
        PREDECESSOR_BYTES,
    )
    assert run.state is RunState.OK
    assert run.note.startswith("valid but empty channel")


# --- the whole composition, offline ---------------------------------------

RSS_ONE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<rss version="2.0"><channel><title>upstream</title>'
    b"<link>https://up.example/</link><description>d</description>"
    b"<item><title>An upstream item</title><link>https://up.example/1</link>"
    b"<pubDate>Sun, 13 Sep 2026 11:00:00 +0000</pubDate></item>"
    b"</channel></rss>\n"
)


class SiteTransport:
    """Routes by URL: a hosted source's upstream from `upstream`, our published
    predecessor from `predecessors`. A URL in neither is a first run (404)."""

    def __init__(self, upstream: dict, predecessors: dict | None = None):
        self.upstream = upstream
        self.predecessors = predecessors or {}
        self.requests: list[tuple[str, dict]] = []

    def __call__(self, url: str, headers: dict) -> tuple[int, bytes]:
        self.requests.append((url, headers))
        if url in self.upstream:
            return self.upstream[url]
        if url in self.predecessors:
            return (200, self.predecessors[url])
        return (404, b"")


def upstream_map(registry) -> dict:
    return {s.url: (200, RSS_ONE) for s in registry.hosted()}


def test_generate_site_runs_the_whole_pipeline_offline(tmp_path):
    """The composition the cron runs — fetch, store read, run_source, write —
    with the HTTP call scripted and nothing monkeypatched."""
    registry = registry_of(rss_source("alpha"), rss_source("beta"))
    get = SiteTransport(upstream_map(registry))

    runs = generate_site(registry, tmp_path, BUILT_AT, get, RecordedSleep())

    assert [r.source_id for r in runs] == [s.id for s in registry.hosted()]
    assert all(r.state is RunState.OK and r.item_count == 1 for r in runs)
    for source in registry.hosted():
        assert (tmp_path / "feeds" / f"{source.id}.xml").is_file()
        # upstream through the strategy's headers, predecessor as RSS
        assert (source.url, source.strategy.headers()) in get.requests
        assert (store.address(registry.feed, source), rss_headers()) in get.requests
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "opml.xml").is_file()
    # each upstream's items reached its own feed
    for source in registry.hosted():
        assert b"An upstream item" in (tmp_path / "feeds" / f"{source.id}.xml").read_bytes()


def test_generate_site_writes_an_empty_channel_when_upstream_dies_unpublished(tmp_path):
    failing = rss_source("alpha")
    registry = registry_of(failing, rss_source("beta"))
    get = SiteTransport({**upstream_map(registry), failing.url: (500, b"")})

    runs = generate_site(registry, tmp_path, BUILT_AT, get, RecordedSleep())

    assert [r.source_id for r in runs if r.state is RunState.FAILED] == [failing.id]
    assert all(r.state is RunState.OK for r in runs if r.source_id != failing.id)
    published = (tmp_path / "feeds" / f"{failing.id}.xml").read_bytes()
    assert b"<item>" not in published
    assert b"<lastBuildDate>" not in published    # never fetched: nothing honest to stamp


def test_generate_site_merges_the_published_predecessor(tmp_path):
    """ADR-0004 end to end: the store read feeds the merge, so an item upstream
    no longer carries survives the run, behind the fresh one."""
    source = rss_source("alpha")
    registry = registry_of(source)
    get = SiteTransport(
        upstream_map(registry),
        predecessors={store.address(registry.feed, source): PREDECESSOR_BYTES},
    )

    runs = generate_site(registry, tmp_path, BUILT_AT, get, RecordedSleep())

    assert all(r.state is RunState.OK for r in runs)
    published = (tmp_path / "feeds" / f"{source.id}.xml").read_bytes()
    assert b"An upstream item" in published and b"An old item" in published
    assert published.index(b"An upstream item") < published.index(b"An old item")  # newest first
