"""Publish: one upstream fetch per hosted source, merged with the feed as
currently published, emitted, and written into the site directory.

Failure policy (tickets 08/11): a failed upstream fetch is never a red run
and never an empty feed. The predecessor's bytes are re-emitted unchanged
(byte-stable), so the feed freezes with its last successful-fetch
lastBuildDate and the staleness badge — not a red X — is the signal. If no
predecessor exists either (first publication with a dead upstream), a
zero-item channel is emitted — with no lastBuildDate, since there has
never been a successful fetch to stamp — so the deploy stays complete.

The published site is the store (ADR-0004): the predecessor is fetched
from the live Pages URL derived from [feed].link, so state lives in the
artifact, not in this repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from feeds import emit as emit_mod
from feeds import fetch, merge, transform
from feeds.model import Item


@dataclass
class SourceStatus:
    source_id: str
    state: str            # "ok" | "stale" | "failed"
    item_count: int = 0
    last_build: str = ""  # what the emitted file's lastBuildDate says (RFC-2822)
    error: str = ""
    note: str = ""


def public_url(feed_meta, source) -> str:
    """The published URL of a hosted feed (the store we merge against)."""
    return f"{feed_meta.link.rstrip('/')}/feeds/{source.id}.xml"


def run_source(source, feed_meta, built_at: datetime) -> tuple[bytes, SourceStatus]:
    """Fetch → transform → merge → emit for one hosted source.
    Returns the feed bytes and a status for reporting."""
    site_link = source.site or feed_meta.link
    channel_description = feed_meta.channel_description(source)

    outcome = fetch.fetch(source)
    if not outcome.ok:
        predecessor = fetch.fetch_predecessor(public_url(feed_meta, source))
        if predecessor is not None:
            # Byte-stable: the predecessor is copied verbatim, lastBuildDate
            # and all — no re-serialization, so nothing drifts.
            # An unparseable predecessor stamp is reported as unknown ("")
            # rather than faked with this run's clock.
            stamp = fetch.parse_last_build_date(predecessor) or ""
            return predecessor, SourceStatus(
                source_id=source.id, state="stale",
                error=outcome.error, last_build=stamp,
                note="upstream fetch failed; predecessor re-emitted unchanged",
            )
        xml = emit_mod.emit(source.name, site_link, channel_description,
                            last_build=None, items=[])
        return xml, SourceStatus(
            source_id=source.id, state="failed",
            error=outcome.error, last_build="",
            note="upstream fetch failed and no predecessor is published; "
                 "emitted an empty channel with no lastBuildDate",
        )

    items = transform.filter_items(source, outcome.items)
    predecessor = fetch.fetch_predecessor(public_url(feed_meta, source))
    predecessor_items: list[Item] = merge.parse_predecessor(predecessor) if predecessor else []
    merged = merge.merge(items, predecessor_items, built_at)
    xml = emit_mod.emit(source.name, site_link, channel_description, built_at, merged)
    return xml, SourceStatus(
        source_id=source.id, state="ok",
        item_count=len(merged), last_build=emit_mod.rfc2822(built_at),
        note=outcome.note or "",
    )


def generate_site(registry, out_dir: str | Path, built_at: datetime) -> list[SourceStatus]:
    """Run every hosted source and write the full site: feeds/, index, OPML."""
    from feeds import render

    out = Path(out_dir)
    (out / "feeds").mkdir(parents=True, exist_ok=True)

    statuses: list[SourceStatus] = []
    for source in registry.hosted():
        xml, status = run_source(source, registry.feed, built_at)
        (out / "feeds" / f"{source.id}.xml").write_bytes(xml)
        statuses.append(status)

    (out / "index.html").write_text(
        render.render_index(registry, statuses, built_at), encoding="utf-8",
    )
    (out / "opml.xml").write_bytes(render.render_opml(registry, built_at))
    return statuses
