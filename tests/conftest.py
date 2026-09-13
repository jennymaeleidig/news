"""Shared test helpers.

The suite is fully offline: no test touches the network. The HTTP call is a
seam (`feeds.transport.Get`), so tests queue `(status, body)` pairs and
record the sleeps the retry policy asks for; committed fixtures run through
the real parsing code path (each strategy's `parse`).
"""

import sys
from pathlib import Path

import pytest
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feeds.model import Item  # noqa: E402
from feeds.registry import FeedMeta, Registry, Source  # noqa: E402
from feeds.strategies import passthrough  # noqa: E402

BUILT_AT = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

TEST_FEED = FeedMeta(title="Test log", link="https://example.com/")


def make_item(
    guid: str,
    pub: datetime | None = None,
    title: str = "an item",
    description: str = "",
    link: str | None = None,
) -> Item:
    return Item(
        title=title,
        link=link or f"https://example.com/{guid}",
        guid=guid,
        published=pub,
        published_raw=pub.strftime("%a, %d %b %Y %H:%M:%S +0000") if pub else "",
        description=description,
    )


def hosted_source(registry, source_id: str):
    """The one hosted source with this id — fixtures are per source id."""
    return next(s for s in registry.hosted() if s.id == source_id)


def _hosted(source_id: str, strategy, **overrides) -> Source:
    fields = {
        "name": source_id.title(),
        "url": f"https://up.example/{source_id}.xml",
        "site": "https://site.example/",
        "why": "because",
    }
    fields.update(overrides)
    return Source(id=source_id, mode="hosted", strategy=strategy, **fields)


def rss_source(source_id: str = "alpha", **overrides) -> Source:
    """A hosted source built by hand. Render, publish and fetch tests take
    their sources from here rather than from `sources.toml`: the registry is
    one owner's list of feeds and it changes, but those behaviors never
    cared which feed they were exercising."""
    return _hosted(source_id, passthrough.build({"name": "passthrough"}), **overrides)


def direct_source(source_id: str = "delta", **overrides) -> Source:
    """A direct source built by hand: its own URL is what a reader subscribes
    to, so there is no strategy and no `why`."""
    fields = {
        "name": source_id.title(),
        "url": f"https://site.example/{source_id}.xml",
        "site": "https://site.example/",
    }
    fields.update(overrides)
    return Source(id=source_id, mode="direct", **fields)


def registry_of(*sources) -> Registry:
    return Registry(feed=TEST_FEED, sources=tuple(sources))


class ScriptedTransport:
    """The `get` seam: a queue of `(status, body)` pairs, or exceptions to
    raise, plus every `(url, headers)` it was asked for.

    The queue is finite on purpose: a call past the end fails, so a test can
    script exactly the attempts it expects and any extra retry is a loud
    failure rather than a silently different run.
    """

    def __init__(self, *responses):
        self._queued = list(responses)
        self.requests: list[tuple[str, dict]] = []

    def __call__(self, url: str, headers: dict) -> tuple[int, bytes]:
        self.requests.append((url, headers))
        if not self._queued:
            raise AssertionError(
                f"unscripted request #{len(self.requests)} to {url!r}: the "
                "test scripted every attempt it expected"
            )
        response = self._queued.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class RecordedSleep:
    """The `sleep` seam: records what the retry policy would have waited."""

    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def registry():
    from feeds.registry import load
    return load("sources.toml")
