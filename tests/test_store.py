"""The published store (ADR-0004): one spelling of the feed's path, its
absolute URL, its on-disk home, and the read that merges against it.

The source and the feed metadata are built by hand: the store's contract is
`/feeds/<id>.xml`, and it never cared which feed was being published.
"""

from pathlib import Path

import pytest

from feeds import store
from feeds.registry import FeedMeta
from feeds.strategies.base import rss_headers
from feeds.transport import TransportError

from conftest import ScriptedTransport, rss_source

SITE = "https://jennymaeleidig.github.io/news-digest-agent"


def feed():
    return FeedMeta(title="Test log", link=SITE)


def test_path_of_a_hosted_source():
    # Literal from the contract sources.toml documents: /feeds/<id>.xml.
    assert store.path(rss_source("rva")) == "/feeds/rva.xml"


def test_address_is_the_absolute_published_url():
    assert store.address(feed(), rss_source("rva")) == f"{SITE}/feeds/rva.xml"


def test_address_normalizes_a_feed_link_without_a_trailing_slash():
    bare = FeedMeta(title="t", link="https://example.com")
    assert store.address(bare, rss_source("x")) == "https://example.com/feeds/x.xml"


def test_local_path_places_the_feed_under_the_site_root():
    assert store.local_path("site", rss_source("rva")) == Path("site/feeds/rva.xml")


def test_write_publishes_the_feed_at_its_layout_path(tmp_path):
    store.write(tmp_path, rss_source("rva"), b"<rss>published</rss>")
    assert (tmp_path / "feeds" / "rva.xml").read_bytes() == b"<rss>published</rss>"


def test_write_creates_the_feed_directory_when_absent(tmp_path):
    nested = tmp_path / "site"
    store.write(nested, rss_source("rva"), b"<rss>x</rss>")
    assert (nested / "feeds" / "rva.xml").is_file()


def test_read_returns_the_published_bytes():
    get = ScriptedTransport((200, b"<rss>published</rss>"))

    assert store.read(rss_source("rva"), feed(), get) == b"<rss>published</rss>"
    # the predecessor is our own published RSS, so it is asked for as RSS
    assert get.requests == [(f"{SITE}/feeds/rva.xml", rss_headers())]


@pytest.mark.parametrize("unreadable", [
    (404, b"not found"),                      # first publication: nothing there yet
    (500, b"pages blew up"),
    TransportError("Pages unavailable"),      # the request never came back
])
def test_read_returns_none_when_the_feed_is_missing_or_unreadable(unreadable):
    get = ScriptedTransport(unreadable)

    assert store.read(rss_source("rva"), feed(), get) is None
