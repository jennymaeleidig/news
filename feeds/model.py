"""Shared value types for the feeds pipeline.

An Item is a verbatim feed entry: upstream's title/link/GUID/pubDate pass
through untouched (hosting never changes item identity, ADR-0003). The
only normalization is scheme-level (_https_normalize on links) and the
pubDate re-render, which preserves the instant — same time, RFC-2822
spelling — so a feed's output is stable across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


@dataclass
class Item:
    title: str
    link: str
    guid: str                    # upstream <guid>, else the link
    published: datetime | None   # aware (UTC) when parseable, else None
    published_raw: str           # upstream's own date string ("" if absent)
    description: str             # verbatim upstream HTML / composed abstract


@dataclass
class FetchOutcome:
    """One upstream fetch: items on success, an error string on failure.

    `note` is a non-fatal observation on a success (e.g. arXiv serving a
    valid-but-empty channel on a declared skip day).
    """

    items: list[Item]
    error: str | None = None
    note: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def parse_published(entry) -> tuple[datetime | None, str]:
    """(aware datetime, raw string) for a feedparser entry's date.

    feedparser's published_parsed wins (timezone-safe); updated is the
    fallback; the raw string survives for re-emission when nothing parses.
    """
    raw = entry.get("published") or entry.get("updated") or ""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc), raw
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, raw
        except (TypeError, ValueError):
            return None, raw
    return None, ""


def https_normalize(url: str) -> str:
    """Upgrade an ``http://`` permalink to ``https://``.

    Some feeds publish ``http://`` permalinks even though the https origin
    serves the same page. Normalizing at fetch time keeps a source's item
    URLs on one scheme so the merge's guid matching sees one spelling.
    """
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url
