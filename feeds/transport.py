"""The HTTP seam: `get(url, headers) -> (status, body)`, plus the one
production adapter.

`feeds.fetch` owns retry, backoff and status classification; this module owns
only how a request is actually made. No module supplies a default adapter —
each composition root (`feeds.__main__`, `scripts/refresh_fixture.py`) passes
`requests_get` and `time.sleep` down explicitly, so the offline suite cannot
reach the network by forgetting an argument.
"""

from __future__ import annotations

from typing import Callable

import requests

_HTTP_TIMEOUT_SECONDS = 30

# GET a URL with the given headers; returns (status_code, body). Raises
# TransportError when no response was received at all.
Get = Callable[[str, dict], tuple[int, bytes]]

# Wait between retry attempts — a seam so a test can assert the backoff
# without spending the time.
Sleep = Callable[[float], None]


class TransportError(Exception):
    """The request never produced a response: DNS, connect, TLS, timeout."""


def requests_get(url: str, headers: dict) -> tuple[int, bytes]:
    """The production adapter: one `requests.get`, status and body out.

    Redirects are followed here rather than above the seam, so the retry
    policy only ever sees a final status.
    """
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=_HTTP_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        raise TransportError(str(e)) from e
    return response.status_code, response.content
