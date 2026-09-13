"""passthrough: publish upstream's items unchanged.

The browser request headers and the RSS parser are the whole strategy: no
filter, no field mapping.
"""

from __future__ import annotations

from feeds.model import FetchOutcome, Item
from feeds.strategies import rss
from feeds.strategies.base import reject_unknown, rss_headers

NAME = "passthrough"
_ALLOWED = {"name"}


def build(block: dict) -> "Passthrough":
    """Validate a `[sources.strategy]` block into a typed strategy."""
    reject_unknown(block, _ALLOWED)
    return Passthrough()


class Passthrough:
    name = NAME
    snapshot_filename = "upstream.xml"

    def headers(self) -> dict:
        return rss_headers()

    def parse(self, data: bytes) -> FetchOutcome:
        return rss.parse(data)

    def filter(self, items: list[Item]) -> list[Item]:
        return items
