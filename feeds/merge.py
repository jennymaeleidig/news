"""The merge model — how a fresh upstream fetch becomes the next
publication (ADR-0004: the published site is the store).

  wholesale replace   an upstream item replaces the predecessor item with
                      the same guid in full — never a field merge
  duplicate guids     the first occurrence wins (upstream is prepended,
                      so upstream beats predecessor)
  age-out             items published more than 30 days ago drop out
                      (items with no parseable date are kept)
  ordering            pubDate descending, guid ascending on ties;
                      items with no parseable date sort last
  cap                 the 100 newest items survive

Failed fetch: the predecessor is re-emitted byte-identical (handled in
publish, not here) — the feed freezes with its last successful-fetch
lastBuildDate rather than losing its items.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import feedparser

from feeds.model import Item, parse_published

MAX_ITEMS = 100
MAX_AGE_DAYS = 30


def _sort_key(item: Item):
    # None-published items sort last regardless of guid; among dated items,
    # pubDate descending with guid ascending as the tie-break.
    if item.published is None:
        return (1, "", "")
    return (0, -item.published.timestamp(), item.guid)


def merge(
    upstream: list[Item],
    predecessor: list[Item],
    built_at: datetime,
) -> list[Item]:
    """Combine the fresh fetch with the published feed's items."""
    combined: list[Item] = []
    seen: set[str] = set()
    for item in [*upstream, *predecessor]:
        if item.guid in seen:
            continue
        seen.add(item.guid)
        combined.append(item)

    cutoff = built_at - timedelta(days=MAX_AGE_DAYS)
    combined = [
        it for it in combined
        if it.published is None or it.published >= cutoff
    ]

    combined.sort(key=_sort_key)
    return combined[:MAX_ITEMS]


def parse_predecessor(data: bytes) -> list[Item]:
    """Items from the currently-published feed (our own earlier output)."""
    parsed = feedparser.parse(data)
    items = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        guid = (entry.get("id") or link).strip()
        published, published_raw = parse_published(entry)
        description = ""
        if "content" in entry and entry.content:
            description = entry.content[0].get("value", "")
        else:
            description = entry.get("summary") or entry.get("description") or ""
        items.append(Item(
            title=title,
            link=link,
            guid=guid,
            published=published,
            published_raw=published_raw,
            description=description,
        ))
    return items
