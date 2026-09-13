"""Shared value types for the feeds pipeline.

An Item is a verbatim feed entry: upstream's title/link/GUID/pubDate pass
through untouched (hosting never changes item identity). The
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

    `note` is a non-fatal observation on a success (e.g. upstream serving a
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
    URLs on one scheme, which matters because a guid falls back to the link
    when upstream omits one: an upstream flipping schemes would otherwise
    change every guid and make readers re-surface old items as new
    (ticket 09's stable-guid rule). This is the sole deliberate exception
    to ticket 05's verbatim principle.
    """
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def entry_description(entry) -> str:
    """Verbatim upstream HTML — no stripping, no truncation.

    The digest-era strip_html/1500-char snippet died with the digest; the
    reader renders the description, so it passes through as the publisher
    wrote it (ElementTree escapes it at emit time).
    """
    if "content" in entry and entry.content:
        return entry.content[0].get("value", "")
    return entry.get("summary") or entry.get("description") or ""


def items_from_entries(entries) -> list[Item]:
    """Map feedparser entries to Items.

    One mapping for both directions: a live upstream fetch and reading back
    our own published feed (the merge's predecessor). Entries without a
    title or link are unusable and dropped.
    """
    items = []
    for entry in entries:
        title = (entry.get("title") or "").strip()
        link = https_normalize((entry.get("link") or "").strip())
        if not title or not link:
            continue
        published, published_raw = parse_published(entry)
        items.append(Item(
            title=title,
            link=link,
            guid=(entry.get("id") or link).strip(),
            published=published,
            published_raw=published_raw,
            description=entry_description(entry),
        ))
    return items
