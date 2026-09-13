"""The publication assembly: fetch each hosted source upstream, merge against
the published store, and emit the feed bytes.

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
It returns the feed bytes and the source's **Run** (`feeds.run.SourceRun`).
Who fetches and who reads the store (ADR-0004) is the caller's business.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from feeds import emit as emit_mod
from feeds import fetch, merge, store
from feeds.model import FetchOutcome, Item
from feeds.render import render_index, render_opml
from feeds.run import RunState, SourceRun
from feeds.strategies.rss import last_build_date


def run_source(
    source,
    feed_meta,
    built_at: datetime,
    upstream: FetchOutcome,
    predecessor: bytes | None,
) -> tuple[bytes, SourceRun]:
    """Merge a fetch outcome with the published predecessor and emit.
    Returns the feed bytes and the source's Run for reporting."""
    site_link = source.site or feed_meta.link
    channel_description = feed_meta.channel_description(source)

    if not upstream.ok:
        if predecessor is not None:
            # Byte-stable: the predecessor is copied verbatim, lastBuildDate
            # and all — no re-serialization, so nothing drifts.
            # An unparseable predecessor stamp is reported as unknown ("")
            # rather than faked with this run's clock.
            stamp = last_build_date(predecessor) or ""
            return predecessor, SourceRun(
                source_id=source.id, state=RunState.STALE,
                error=upstream.error or "", last_build=stamp,
                note="upstream fetch failed; predecessor re-emitted unchanged",
            )
        xml = emit_mod.emit(source.name, site_link, channel_description,
                            last_build=None, items=[])
        return xml, SourceRun(
            source_id=source.id, state=RunState.FAILED,
            error=upstream.error or "", last_build="",
            note="upstream fetch failed and no predecessor is published; "
                 "emitted an empty channel with no lastBuildDate",
        )

    items = source.strategy.filter(upstream.items)
    predecessor_items: list[Item] = merge.parse_predecessor(predecessor) if predecessor else []
    merged = merge.merge(items, predecessor_items, built_at)
    xml = emit_mod.emit(source.name, site_link, channel_description, built_at, merged)
    return xml, SourceRun(
        source_id=source.id, state=RunState.OK,
        item_count=len(merged), last_build=emit_mod.rfc2822(built_at),
        note=upstream.note or "",
    )


def generate_site(registry, out_dir: str | Path, built_at: datetime,
                  transport: store.Transport) -> list[SourceRun]:
    """Run every hosted source and write the full site: feeds/, index, OPML."""
    out = Path(out_dir)

    runs: list[SourceRun] = []
    for source in registry.hosted():
        upstream = fetch.fetch(source)
        predecessor = store.read(source, registry.feed, transport)
        xml, run = run_source(source, registry.feed, built_at, upstream, predecessor)
        store.write(out, source, xml)
        runs.append(run)

    (out / "index.html").write_text(
        render_index(registry, runs, built_at), encoding="utf-8",
    )
    (out / "opml.xml").write_bytes(render_opml(registry, built_at))
    return runs
