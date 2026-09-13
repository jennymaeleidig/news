"""The published store (ADR-0004): one spelling of the feed's path, its
absolute URL, its on-disk home, and the read that merges against it."""

from pathlib import Path

import pytest

from feeds import store
from feeds.registry import FeedMeta, Source
from feeds.strategies.base import rss_headers
from feeds.transport import TransportError

from conftest import ScriptedTransport, hosted_source

SITE = "https://jennymaeleidig.github.io/news-digest-agent"


def bare_source():
    return Source(id="x", name="X", mode="hosted", url="https://example.com/x.xml",
                  why="because")


def test_path_of_a_hosted_source(registry):
    # Literal from the contract sources.toml documents: /feeds/<id>.xml.
    assert store.path(hosted_source(registry, "reddit-rva")) == "/feeds/reddit-rva.xml"


def test_address_is_the_absolute_published_url(registry):
    assert store.address(registry.feed, hosted_source(registry, "reddit-rva")) == f"{SITE}/feeds/reddit-rva.xml"


def test_address_normalizes_a_feed_link_without_a_trailing_slash():
    feed = FeedMeta(title="t", link="https://example.com")
    assert store.address(feed, bare_source()) == "https://example.com/feeds/x.xml"


def test_local_path_places_the_feed_under_the_site_root(registry):
    assert store.local_path("site", hosted_source(registry, "reddit-rva")) == Path("site/feeds/reddit-rva.xml")


def test_write_publishes_the_feed_at_its_layout_path(registry, tmp_path):
    store.write(tmp_path, hosted_source(registry, "reddit-rva"), b"<rss>published</rss>")
    assert (tmp_path / "feeds" / "reddit-rva.xml").read_bytes() == b"<rss>published</rss>"


def test_write_creates_the_feed_directory_when_absent(registry, tmp_path):
    nested = tmp_path / "site"
    store.write(nested, hosted_source(registry, "reddit-rva"), b"<rss>x</rss>")
    assert (nested / "feeds" / "reddit-rva.xml").is_file()


def test_read_returns_the_published_bytes(registry):
    get = ScriptedTransport((200, b"<rss>published</rss>"))

    assert store.read(hosted_source(registry, "reddit-rva"), registry.feed, get) == b"<rss>published</rss>"
    # the predecessor is our own published RSS, so it is asked for as RSS
    assert get.requests == [(f"{SITE}/feeds/reddit-rva.xml", rss_headers())]


@pytest.mark.parametrize("unreadable", [
    (404, b"not found"),                      # first publication: nothing there yet
    (500, b"pages blew up"),
    TransportError("Pages unavailable"),      # the request never came back
])
def test_read_returns_none_when_the_feed_is_missing_or_unreadable(registry, unreadable):
    get = ScriptedTransport(unreadable)

    assert store.read(hosted_source(registry, "reddit-rva"), registry.feed, get) is None
