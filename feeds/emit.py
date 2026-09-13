"""RSS 2.0 emission — hand-rolled on the stdlib (ADR, ticket 09).

feedgen is unmaintained; the format we publish is small and frozen, so
xml.etree.ElementTree + xml.sax.saxutils escaping + email.utils RFC-2822
dates cover it. RSS 2.0 only: no Atom, no podcast namespaces (the one
podcast source is direct).

Serialization is deterministic given the channel meta, the items, and
`built_at` — golden files pin it exactly. `built_at` is injected by the
caller (tests pass a fixed stamp) so nothing normalizes timestamps after
the fact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from xml.etree import ElementTree as ET

from feeds.model import Item

GENERATOR = "news-digest-agent feeds"


def rfc2822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc))


def emit(
    channel_title: str,
    channel_link: str,
    channel_description: str,
    built_at: datetime,
    items: list[Item],
) -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = channel_link
    ET.SubElement(channel, "description").text = channel_description
    ET.SubElement(channel, "lastBuildDate").text = rfc2822(built_at)
    ET.SubElement(channel, "generator").text = GENERATOR

    for item in items:
        entry = ET.SubElement(channel, "item")
        ET.SubElement(entry, "title").text = item.title
        ET.SubElement(entry, "link").text = item.link
        # isPermaLink defaults to true; say "false" exactly when the guid
        # is not the item's URL.
        guid_attrs = {} if item.guid == item.link else {"isPermaLink": "false"}
        ET.SubElement(entry, "guid", guid_attrs).text = item.guid
        if item.published is not None:
            ET.SubElement(entry, "pubDate").text = rfc2822(item.published)
        elif item.published_raw:
            # Unparseable upstream date: pass the raw string through so
            # readers at least see what the source published.
            ET.SubElement(entry, "pubDate").text = item.published_raw
        ET.SubElement(entry, "description").text = item.description

    body = ET.tostring(rss, encoding="unicode", short_empty_elements=True)
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + body + "\n").encode("utf-8")
