#!/usr/bin/env python
"""Refresh a hosted source's committed fixture with a live upstream fetch.

Fixture refreshes are manual and reviewed by a human (CODING_STANDARDS.md):
the upstream snapshot and the emitted golden are both overwritten, and the
diff must be read before committing — a hostile or drifted upstream must
never silently redefine what we consider correct output.

    PYTHONPATH=. python scripts/refresh_fixture.py <source-id> [--built-at ISO]

Writes tests/fixtures/<source-id>/{upstream.xml | upstream.json,expected.xml}.
The snapshot is upstream's own response body, byte for byte (rss strategies
land in upstream.xml, the json_api strategy in upstream.json), so the fixture
test parses exactly what the source sent. expected.xml is produced by
`publish.run_source` — the assembly the cron runs — with no predecessor and
the clock frozen at --built-at, so the golden only changes when behavior or
upstream content changes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
SNAPSHOTS = {"json_api": "upstream.json"}
DEFAULT_SNAPSHOT = "upstream.xml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    parser.add_argument("--built-at", default=None, help="freeze the clock (ISO 8601)")
    args = parser.parse_args()

    import requests

    from feeds.fetch import fetch_bytes, parse_feed_bytes, parse_json_bytes
    from feeds.publish import run_source
    from feeds.registry import load

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

    strategy = source.strategy.name if source.strategy else "rss"
    try:
        raw = fetch_bytes(source)                       # upstream's own bytes
    except requests.RequestException as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1

    outcome = (
        parse_json_bytes(raw, source.strategy)
        if strategy == "json_api"
        else parse_feed_bytes(raw)
    )
    if not outcome.ok:
        print(f"parse failed: {outcome.error}", file=sys.stderr)
        return 1
    if outcome.note:
        print(f"note: {outcome.note}")

    # The expected golden comes from the same assembly the cron runs; the only
    # difference is where the upstream bytes came from (this live fetch, which
    # also records the snapshot).
    xml, status = run_source(source, registry.feed, built_at, outcome, predecessor=None)

    snapshot = SNAPSHOTS.get(strategy, DEFAULT_SNAPSHOT)
    out = FIXTURES / source.id
    out.mkdir(parents=True, exist_ok=True)
    for stale in sorted({"upstream.xml", "upstream.json"} - {snapshot}):
        if (out / stale).exists():                      # strategy changed: drop the old shape
            (out / stale).unlink()

    (out / snapshot).write_bytes(raw)
    (out / "expected.xml").write_bytes(xml)
    print(f"wrote {out}/{snapshot} ({len(raw)} bytes, upstream's own response)")
    print(f"wrote {out}/expected.xml ({len(xml)} bytes, {status.item_count} items)")
    print("review the diff before committing:")
    print(f"  git diff tests/fixtures/{source.id}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
