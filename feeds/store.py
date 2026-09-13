"""The published store — the feed as currently published on Pages, read back
as this run's predecessor (ADR-0004: the published site is the store).

One module owns the layout, so `/feeds/<id>.xml` is spelled once and the
index, the OPML, the merge, and the site writer all derive from it. The read
is a transport call plus the failure policy that makes a missing or
unreadable store survive: first publication and Pages hiccups both proceed
with the upstream fetch alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import requests

# Fetch a URL and return its body; raises requests.RequestException on
# failure. Landing 04 replaces the requests implementation with the HTTP
# seam while this shape — and every caller's — stays put.
Transport = Callable[[str], bytes]

# The one place the published layout is spelled.
_FEED_DIR = "feeds"


def path(source) -> str:
    """The published feed's path on the site: `/feeds/<id>.xml`."""
    return f"/{_FEED_DIR}/{source.id}.xml"


def address(feed_meta, source) -> str:
    """The absolute published URL the merge reads the predecessor from."""
    return f"{feed_meta.link.rstrip('/')}{path(source)}"


def local_path(out_dir: str | Path, source) -> Path:
    """Where the site generator writes this feed under its output root.

    The artifact is the site, so the file layout is the URL layout under a
    root — derived, not re-spelled.
    """
    return Path(out_dir) / path(source).lstrip("/")


def write(out_dir: str | Path, source, data: bytes) -> None:
    """Publish one feed at its place in the layout."""
    target = local_path(out_dir, source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def read(source, feed_meta, transport: Transport) -> bytes | None:
    """The predecessor's bytes, or None when the read fails — nothing
    published yet, or Pages down. Either way the run continues with the
    upstream fetch alone.

    "Fails" is the transport's declared failure mode, requests'
    RequestException: that is the contract of Transport below, and a
    transport that breaks it has a bug worth crashing the run over.
    """
    try:
        return transport(address(feed_meta, source))
    except requests.RequestException:
        return None
