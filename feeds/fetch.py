"""Upstream fetching for hosted sources: the HTTP call, its retry policy, and
how a failure becomes a FetchOutcome.

Retry mechanics are ported verbatim from the digest-era fetchers/rss.py:
bounded retry on transient causes (429/5xx blips, network errors) with linear
backoff, and immediate failure on deterministic 4xx. The request headers and
the body's parsing belong to the source's Strategy (`feeds.strategies`); this
module owns only the request.

`http_get` is the published store's transport (`feeds.store.Transport`).
"""

from __future__ import annotations

import time

import requests

from feeds.model import FetchOutcome
from feeds.strategies.base import rss_headers

_HTTP_TIMEOUT_SECONDS = 30
_FETCH_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _fetch_response(url: str, headers: dict) -> requests.Response:
    """GET ``url`` with bounded retry on transient causes.

    Raises the last RequestException, or a requests.HTTPError carrying the
    final status, only once the retry budget is exhausted. A deterministic
    status (403/404 and other non-retryable 4xx) raises immediately —
    the answer won't change on retry.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _FETCH_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=_HTTP_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
        except requests.RequestException as e:
            last_exc = e
        else:
            if resp.status_code < 400:
                return resp
            if resp.status_code not in _RETRYABLE_STATUSES:
                resp.raise_for_status()  # deterministic: fail now
            last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
        if attempt < _FETCH_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise last_exc  # type: ignore[misc]


def _get_bytes(url: str, headers: dict) -> bytes:
    """GET a URL and return the response body, retrying transient causes."""
    return _fetch_response(url, headers).content


def fetch_bytes(source) -> bytes:
    """GET a source's raw response body — the fixture-snapshot path.

    A fixture must be upstream's own bytes (CODING_STANDARDS.md), so this
    returns the body untouched; the caller parses it with the source's
    strategy, the same mapping the live path uses.
    """
    return _get_bytes(source.url, source.strategy.headers())


def fetch(source) -> FetchOutcome:
    """Fetch a hosted source and hand the body to its strategy to parse."""
    try:
        resp = _fetch_response(source.url, source.strategy.headers())
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        return FetchOutcome(items=[], error=f"HTTP {status}" if status else f"fetch failed: {e}")
    except requests.RequestException as e:
        return FetchOutcome(items=[], error=f"fetch failed: {e}")
    return source.strategy.parse(resp.content)


def http_get(url: str) -> bytes:
    """GET a URL and return its body, retrying transient causes — the
    published store's transport (feeds.store.Transport). Raises
    requests.RequestException once the retry budget is exhausted."""
    return _get_bytes(url, rss_headers())
