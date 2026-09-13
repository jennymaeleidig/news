"""Publication: fetch each hosted source upstream, merge against the published
store, and emit the feed bytes.

Failure policy (tickets 08/11): a failed upstream fetch is never a red run
and never an empty feed. The predecessor's bytes are re-emitted unchanged
(byte-stable), so the feed freezes with its last successful-fetch
lastBuildDate and the staleness badge — not a red X — is the signal. If no
predecessor exists either (first publication with a dead upstream), a
zero-item channel is emitted — with no lastBuildDate, since there has
never been a successful fetch to stamp — so the publication stays complete.

`run_source` is the assembly and takes both sides as values — the fetch
outcome and the predecessor's bytes — so the failure policy is exercised
without fakes, and the fixture path runs the same assembly the cron does.
Who fetches and who reads the store (ADR-0004) is the caller's business.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from feeds import emit as emit_mod
from feeds import fetch, merge, store, transform
from feeds.model import FetchOutcome, Item


@dataclass
class SourceRun:
    """One source's outcome for a run: its freshness state, what it
    published, and the failure note when there was one."""

    source_id: str
    state: str            # "ok" | "stale" | "failed"
    item_count: int = 0
    last_build: str = ""  # what the emitted file's lastBuildDate says (RFC-2822)
    error: str = ""
    note: str = ""


def run_source(
    source,
    feed_meta,
    built_at: datetime,
    upstream: FetchOutcome,
    predecessor: bytes | None,
) -> tuple[bytes, SourceRun]:
    """Merge a fetch outcome with the published predecessor and emit.
    Returns the feed bytes and a status for reporting."""
    site_link = source.site or feed_meta.link
    channel_description = feed_meta.channel_description(source)

    if not upstream.ok:
        if predecessor is not None:
            # Byte-stable: the predecessor is copied verbatim, lastBuildDate
            # and all — no re-serialization, so nothing drifts.
            # An unparseable predecessor stamp is reported as unknown ("")
            # rather than faked with this run's clock.
            stamp = fetch.last_build_date(predecessor) or ""
            return predecessor, SourceRun(
                source_id=source.id, state="stale",
                error=upstream.error or "", last_build=stamp,
                note="upstream fetch failed; predecessor re-emitted unchanged",
            )
        xml = emit_mod.emit(source.name, site_link, channel_description,
                            last_build=None, items=[])
        return xml, SourceRun(
            source_id=source.id, state="failed",
            error=upstream.error or "", last_build="",
            note="upstream fetch failed and no predecessor is published; "
                 "emitted an empty channel with no lastBuildDate",
        )

    items = transform.filter_items(source, upstream.items)
    predecessor_items: list[Item] = merge.parse_predecessor(predecessor) if predecessor else []
    merged = merge.merge(items, predecessor_items, built_at)
    xml = emit_mod.emit(source.name, site_link, channel_description, built_at, merged)
    return xml, SourceRun(
        source_id=source.id, state="ok",
        item_count=len(merged), last_build=emit_mod.rfc2822(built_at),
        note=upstream.note or "",
    )


def generate_site(registry, out_dir: str | Path, built_at: datetime,
                  transport: store.Transport) -> list[SourceRun]:
    """Run every hosted source and write the full site: feeds/, index, OPML."""
    from feeds import render

    out = Path(out_dir)

    statuses: list[SourceRun] = []
    for source in registry.hosted():
        upstream = fetch.fetch(source)
        predecessor = store.read(source, registry.feed, transport)
        xml, status = run_source(source, registry.feed, built_at, upstream, predecessor)
        store.write(out, source, xml)
        statuses.append(status)

    (out / "index.html").write_text(
        render.render_index(registry, statuses, built_at), encoding="utf-8",
    )
    (out / "opml.xml").write_bytes(render.render_opml(registry, built_at))
    return statuses
