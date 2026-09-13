#!/usr/bin/env python
"""Refresh a hosted source's committed fixture with a live upstream fetch.

Fixture refreshes are manual and reviewed by a human (CODING_STANDARDS.md):
the upstream snapshot and the emitted golden are both overwritten, and the
diff must be read before committing — a hostile or drifted upstream must
never silently redefine what we consider correct output.

    PYTHONPATH=. python scripts/refresh_fixture.py <source-id> [--built-at ISO]

Writes tests/fixtures/<source-id>/: the strategy's `snapshot_filename`,
holding upstream's own response body byte for byte, plus `expected.xml`
produced by `publish.run_source` — the assembly the cron runs — with no
predecessor and the clock frozen at --built-at, so the golden only changes
when behavior or upstream content changes. Any other file in that directory
is a shape a former strategy left behind and is dropped.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"


def drop_stale(out: Path, snapshot: str) -> list[str]:
    """Delete whatever in a fixture directory is not part of the fixture now.

    The directory's shape is fixed — the strategy's snapshot plus
    `expected.xml` — so anything else is a shape a former strategy wrote and
    would otherwise sit there forever. Returns the names dropped.
    """
    dropped = []
    for stale in sorted(p for p in out.iterdir()
                        if p.is_file() and p.name not in (snapshot, "expected.xml")):
        stale.unlink()
        dropped.append(stale.name)
    return dropped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    parser.add_argument("--built-at", default=None, help="freeze the clock (ISO 8601)")
    args = parser.parse_args()

    from feeds.fetch import FetchError, fetch_bytes
    from feeds.publish import run_source
    from feeds.registry import load
    from feeds.transport import requests_get

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

    try:
        raw = fetch_bytes(source, requests_get, time.sleep)   # upstream's own bytes
    except FetchError as e:
        print(f"{e}", file=sys.stderr)
        return 1

    outcome = source.strategy.parse(raw)
    if not outcome.ok:
        print(f"parse failed: {outcome.error}", file=sys.stderr)
        return 1
    if outcome.note:
        print(f"note: {outcome.note}")

    # The expected golden comes from the same assembly the cron runs; the only
    # difference is where the upstream bytes came from (this live fetch, which
    # also records the snapshot).
    xml, run = run_source(source, registry.feed, built_at, outcome, predecessor=None)

    snapshot = source.strategy.snapshot_filename
    out = FIXTURES / source.id
    out.mkdir(parents=True, exist_ok=True)
    for name in drop_stale(out, snapshot):
        print(f"dropped stale {name}")

    (out / snapshot).write_bytes(raw)
    (out / "expected.xml").write_bytes(xml)
    print(f"wrote {out}/{snapshot} ({len(raw)} bytes, upstream's own response)")
    print(f"wrote {out}/expected.xml ({len(xml)} bytes, {run.item_count} items)")
    print("review the diff before committing:")
    print(f"  git diff tests/fixtures/{source.id}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
