"""CLI: generate the site and/or the direct-feeds table.

    python -m feeds gen --out site
        Fetch every hosted source and write feeds/, index.html, opml.xml
        under --out. Failed fetches print warning annotations and a
        Job Summary table (when --summary-file is set) but stay green.

    python -m feeds gen --direct-table docs/direct-feeds.md
        Regenerate the committed direct-feeds table from sources.toml and
        exit — no fetching, so this is safe to run anywhere. (Run the site
        generation as a separate command.)

    --built-at ISO
        Freeze the generation clock (deterministic output for goldens
        and local diffs). Defaults to now, UTC.

Every surface this prints is a `feeds.render` function; this module keeps
argument handling, the file writes, and the console log.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from feeds import fetch
from feeds.publish import generate_site
from feeds.registry import load
from feeds.render import render_annotations, render_direct_table, render_job_summary


def _parse_built_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="feeds")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("gen", help="generate the site and/or the direct table")
    gen.add_argument("--out", default="site", help="output directory for the site")
    gen.add_argument("--direct-table", metavar="PATH", help="write the direct-feeds markdown table to PATH")
    gen.add_argument("--built-at", metavar="ISO", help="freeze the generation clock")
    gen.add_argument("--summary-file", metavar="PATH",
                     help="write a per-source run table to PATH (for the Actions Job Summary)")
    args = parser.parse_args(argv)

    registry = load()
    built_at = _parse_built_at(args.built_at)

    if args.direct_table:
        # Table-only and offline: rendering the registry never fetches.
        path = Path(args.direct_table)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_direct_table(registry), encoding="utf-8")
        print(f"direct table -> {path}")
        return 0

    runs = generate_site(registry, args.out, built_at, fetch.http_get)
    for run in runs:
        word = run.state.summary_word
        print(f"{run.source_id}: {word} ({run.item_count} items, lastBuildDate {run.last_build})")
        if run.note:
            print(f"  note: {run.note}")
        if run.error:
            print(f"  error: {run.error}")
    for line in render_annotations(runs):
        print(line)
    print(f"site -> {args.out}/ (index.html, opml.xml, feeds/*.xml)")

    if args.summary_file:
        Path(args.summary_file).write_text(
            render_job_summary(runs, built_at), encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
