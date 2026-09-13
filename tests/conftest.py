"""Shared test helpers.

The suite is fully offline: no test touches the network. Fetch-level
behavior is covered with fakes (monkeypatching feeds.fetch) and committed
fixtures run through the real parsing code path (feeds.fetch.parse_feed_bytes).
"""

import sys
from pathlib import Path

import pytest
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feeds.model import Item  # noqa: E402

BUILT_AT = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


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


@pytest.fixture
def registry():
    from feeds.registry import load
    return load("sources.toml")
