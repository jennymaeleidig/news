"""The shape every strategy module implements, and the browser header sets
our outbound requests send.

A **Strategy** is built from one source's `[sources.strategy]` block. It owns
that source's request headers, its parser (`parse(bytes)`), and its filter
(`filter(items)`), and it performs no I/O: `feeds.transport` makes the
request and `feeds.fetch` retries it and hands the bytes over. (The published
store's read sends the RSS set too — its predecessor is our own feed.)
"""

from __future__ import annotations

from typing import Protocol

from feeds.model import FetchOutcome, Item

# Browser impersonation for every outbound request: our hosted upstream
# (richmond.com) rate-limits plain clients with an HTTP 429 from datacenter IPs.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Advertise only encodings requests decodes without extra deps.
_COMMON_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def rss_headers() -> dict:
    """Headers for an RSS/Atom upstream: the browser Accept set."""
    return {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": (
            "application/rss+xml, application/atom+xml, "
            "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"
        ),
        **_COMMON_HEADERS,
    }


class StrategyConfigError(ValueError):
    """A `[sources.strategy]` block that a strategy cannot accept.

    The registry turns this into a RegistryError under the source's label, so
    a malformed block fails the whole run rather than publishing a half-site.
    """


def reject_unknown(block: dict, allowed: set[str]) -> None:
    """Fail a block carrying keys the strategy does not know.

    Every strategy validates strictly: a typo'd key (``term`` for ``terms``)
    is a loud registry error, not a silently ignored param.
    """
    extra = set(block) - allowed
    if extra:
        raise StrategyConfigError(f"unknown param(s) {sorted(extra)}")


class Strategy(Protocol):
    """What `feeds.fetch` and `run_source` need from any strategy."""

    name: str
    snapshot_filename: str       # the committed fixture's upstream snapshot

    def headers(self) -> dict: ...

    def parse(self, data: bytes) -> FetchOutcome: ...

    def filter(self, items: list[Item]) -> list[Item]: ...
