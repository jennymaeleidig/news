"""Transforms: filter hosted sources' items. Hosting never changes item
identity (ADR-0003), so a transform may only *drop* items — titles, links,
guids, and dates pass through exactly as upstream published them.

topic_filter  keep items whose title or description matches any term
              (case-insensitive substring — the digest-era semantics that
              scoped the arXiv firehoses)
passthrough   identity; the browser-UA fetch is the whole strategy
json_api      identity at transform time; its field mapping (and the
              composed description) happens at fetch time
"""

from __future__ import annotations

from feeds.model import Item


def filter_items(source, items: list[Item]) -> list[Item]:
    strategy = source.strategy
    if not strategy or strategy.name != "topic_filter":
        return items
    terms = [t.lower() for t in strategy.params["terms"]]
    kept = []
    for item in items:
        hay = f"{item.title}\n{item.description}".lower()
        if any(term in hay for term in terms):
            kept.append(item)
    return kept
