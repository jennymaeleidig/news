"""The RSS parser shared by the two RSS-shaped strategies (`topic_filter` and
`passthrough`): feedparser entries → Items, plus the predecessor's
lastBuildDate.

One mapping serves both directions — a live upstream fetch and reading back
our own published feed (the merge's predecessor).
"""

from __future__ import annotations

import re

import feedparser

from feeds.model import FetchOutcome, items_from_entries


def parse(data: bytes) -> FetchOutcome:
    """Parse feed bytes into Items — the mapping both live fetches and
    committed fixtures run through, so goldens test the real code path."""
    parsed = feedparser.parse(data)
    if parsed.bozo and not parsed.entries:
        return FetchOutcome(items=[], error=f"feed parse error: {parsed.bozo_exception}")

    # A well-formed channel with zero entries is a success-with-note, not a
    # failure: arXiv declares <skipDays> (weekends, holidays) and serves a
    # valid empty channel those days.
    note = None
    if not parsed.entries and ("skipdays" in parsed.feed or "day" in parsed.feed):
        rebuilt = parsed.feed.get("updated") or ""
        # feedparser 6.x accumulates nothing for <skipDays>: feed['skipdays']
        # is '' and only the LAST <day> survives as feed['day']. The regex over
        # the raw bytes is therefore load-bearing, not a redundant re-parse.
        skip_days = re.findall(
            r"<day>\s*([^<]+?)\s*</day>",
            data.decode("utf-8", errors="replace"),
        )
        days = f" ({', '.join(skip_days)})" if skip_days else ""
        note = (
            "valid but empty channel — source declares skip days"
            f"{days}; channel lastBuildDate {rebuilt or 'unknown'}"
        )

    items = items_from_entries(parsed.entries)
    return FetchOutcome(items=items, note=note)


def last_build_date(data: bytes) -> str | None:
    """The predecessor channel's lastBuildDate, raw. Used to keep the
    freshness stamp truthful when a failed fetch re-emits the predecessor.
    feedparser 6.x maps <lastBuildDate> to the 'updated' key and exposes no
    'lastbuilddate' of its own, so that is the only key read (D10)."""
    stamp = feedparser.parse(data).feed.get("updated")
    return stamp or None
