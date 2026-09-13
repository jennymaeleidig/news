#!/usr/bin/env python
"""Refresh a hosted source's committed fixture with a live upstream fetch.

Fixture refreshes are manual and reviewed by a human (CODING_STANDARDS.md):
the upstream snapshot and the emitted golden are both overwritten, and the
diff must be read before committing — a hostile or drifted upstream must
never silently redefine what we consider correct output.

    PYTHONPATH=. python scripts/refresh_fixture.py <source-id> [--built-at ISO]

Writes tests/fixtures/<source-id>/{upstream.xml,expected.xml}. expected.xml
is produced by the exact test-pipeline path (parse_feed_bytes → transform →
merge against no predecessor → emit), with the clock frozen at --built-at
so the golden only changes when behavior or upstream content changes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    parser.add_argument("--built-at", default=None, help="freeze the clock (ISO 8601)")
    args = parser.parse_args()

    from feeds.emit import emit
    from feeds.fetch import fetch
    from feeds.merge import merge
    from feeds.registry import load
    from feeds.transform import filter_items

    registry = load(REPO / "sources.toml")
    source = next((s for s in registry.hosted() if s.id == args.source_id), None)
    if source is None:
        print(f"no hosted source {args.source_id!r} in sources.toml", file=sys.stderr)
        return 1

    built_at = (
        datetime.fromisoformat(args.built_at.replace("Z", "+00:00"))
        if args.built_at
        else datetime.now(timezone.utc)
    )

    outcome = fetch.fetch(source)
    if not outcome.ok:
        print(f"fetch failed: {outcome.error}", file=sys.stderr)
        return 1
    if outcome.note:
        print(f"note: {outcome.note}")

    items = filter_items(source, outcome.items)
    merged = merge(items, [], built_at)
    xml = emit(source.name, source.site,
               registry.feed.channel_description(source), built_at, merged)

    out = FIXTURES / source.id
    out.mkdir(parents=True, exist_ok=True)
    # The upstream snapshot is the raw fetch: re-serialize? No — for RSS we
    # can't reproduce upstream bytes without keeping the response, so we
    # snapshot what feedparser consumed via a fresh fetch. For the golden
    # path the snapshot and the parse must agree, so we write the parsed
    # items back out as a normalized RSS snapshot instead of pretending we
    # kept the original bytes.
    snapshot = emit_snapshot(source, registry, outcome, built_at)
    (out / "upstream.xml").write_bytes(snapshot)
    (out / "expected.xml").write_bytes(xml)
    print(f"wrote {out}/upstream.xml ({len(snapshot)} bytes)")
    print(f"wrote {out}/expected.xml ({len(xml)} bytes, {len(merged)} items)")
    print("review the diff before committing:")
    print(f"  git diff tests/fixtures/{source.id}/")
    return 0


def emit_snapshot(source, registry, outcome, built_at):
    """A normalized snapshot of the upstream fetch: same items, our spelling.

    The raw upstream bytes can't be reproduced on refresh (no storage), and
    feedparser accepts any well-formed spelling anyway — what the golden
    path needs is items that parse identically. Emitting them as RSS gives a
    diffable, version-controlled snapshot.
    """
    from feeds.emit import emit
    return emit(
        f"[upstream] {source.name}",
        source.site or registry.feed.link,
        f"normalized upstream snapshot for {source.id}",
        built_at,
        outcome.items,
    )


if __name__ == "__main__":
    sys.exit(main())
