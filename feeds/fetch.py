"""Upstream fetching for hosted sources: the retry policy above the HTTP seam,
and how a failure becomes a FetchOutcome.

Retry mechanics are ported verbatim from the digest-era fetchers/rss.py:
bounded retry on transient causes (429/5xx blips, network errors) with linear
backoff, and immediate failure on deterministic 4xx. The HTTP call itself is
`feeds.transport`'s seam and is passed in by the caller; the request headers
and the body's parsing belong to the source's Strategy (`feeds.strategies`).
"""

from __future__ import annotations

from feeds.model import FetchOutcome
from feeds.transport import Get, Sleep, TransportError

_FETCH_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """A fetch that will not be retried further: a deterministic 4xx (raised
    at once) or an exhausted retry budget. The message carries the status
    when a response had one."""


def _get(url: str, headers: dict, get: Get, sleep: Sleep) -> tuple[int, bytes]:
    """GET through the seam, retrying transient causes with linear backoff.

    Raises once the retry budget is exhausted, or immediately on a
    deterministic 4xx — the answer won't change on retry.
    """
    last: FetchError | None = None
    for attempt in range(1, _FETCH_ATTEMPTS + 1):
        try:
            status, body = get(url, headers)
        except TransportError as e:
            last = FetchError(f"fetch failed: {e}")
        else:
            if status < 400:
                return status, body
            last = FetchError(f"HTTP {status}")
            if status not in _RETRYABLE_STATUSES:
                raise last
        if attempt < _FETCH_ATTEMPTS:
            sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise last


def fetch_bytes(source, get: Get, sleep: Sleep) -> bytes:
    """GET a source's raw response body — the fixture-snapshot path.

    A fixture must be upstream's own bytes (CODING_STANDARDS.md), so this
    returns the body untouched; the caller parses it with the source's
    strategy, the same mapping the live path uses. Raises FetchError.
    """
    return _get(source.url, source.strategy.headers(), get, sleep)[1]


def fetch(source, get: Get, sleep: Sleep) -> FetchOutcome:
    """Fetch a hosted source and hand the body to its strategy to parse."""
    try:
        _, body = _get(source.url, source.strategy.headers(), get, sleep)
    except FetchError as e:
        return FetchOutcome(items=[], error=str(e))
    return source.strategy.parse(body)
