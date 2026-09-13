"""topic_filter: keep the items whose title or description matches any term.

Case-insensitive substring matching — the digest-era semantics that scoped the
arXiv firehoses. It may only *drop* items: hosting never changes item identity
(ADR-0003).
"""

from __future__ import annotations

from feeds.model import FetchOutcome, Item
from feeds.strategies import rss
from feeds.strategies.base import StrategyConfigError, reject_unknown, rss_headers

NAME = "topic_filter"
_ALLOWED = {"name", "terms"}


def build(block: dict) -> "TopicFilter":
    """Validate a `[sources.strategy]` block into a typed strategy."""
    reject_unknown(block, _ALLOWED)
    terms = block.get("terms")
    if not (
        isinstance(terms, list)
        and terms
        and all(isinstance(t, str) and t.strip() for t in terms)
    ):
        raise StrategyConfigError(
            "topic_filter needs a non-empty list of non-empty 'terms'"
        )
    return TopicFilter(tuple(t.strip() for t in terms))


class TopicFilter:
    name = NAME
    snapshot_filename = "upstream.xml"

    def __init__(self, terms: tuple[str, ...]):
        self.terms = terms

    def headers(self) -> dict:
        return rss_headers()

    def parse(self, data: bytes) -> FetchOutcome:
        return rss.parse(data)

    def filter(self, items: list[Item]) -> list[Item]:
        lowered = [t.lower() for t in self.terms]
        kept = []
        for item in items:
            hay = f"{item.title}\n{item.description}".lower()
            if any(term in hay for term in lowered):
                kept.append(item)
        return kept
