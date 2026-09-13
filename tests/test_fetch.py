"""Upstream fetching at the transport seam: a scripted `get(url, headers) ->
(status, body)` and a recorded `sleep`, so the retry budget, the linear
backoff, the deterministic-4xx rule and the per-strategy headers all execute
offline. No test names a private function, and no test touches the network.

SPDX-License-Identifier: CC0-1.0
"""

import pytest

from feeds import store
from feeds.fetch import FetchError, fetch, fetch_bytes
from feeds.transport import TransportError

from conftest import RecordedSleep, ScriptedTransport, hosted_source

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>upstream</title><link>https://up.example/</link><description>d</description>
<item><title>one</title><link>https://up.example/1</link></item>
</channel></rss>
"""

JSON = b'[{"paper": {"title": "A paper", "id": "2409.1"}}]'

# 2s then 4s: linear backoff after attempts 1 and 2, none after the last.
BACKOFF = [2.0, 4.0]


def test_fetch_bytes_returns_upstream_bytes_untouched(registry):
    """The fixture snapshot must be upstream's own bytes, not a re-render."""
    raw = b"whatever upstream sent\xff\xfe"
    get = ScriptedTransport((200, raw))

    assert fetch_bytes(hosted_source(registry, "hf-daily-papers"), get,
                       RecordedSleep()) == raw


def test_fetch_parses_the_body_with_the_source_strategy(registry):
    get = ScriptedTransport((200, RSS))
    source = hosted_source(registry, "reddit-rva")

    outcome = fetch(source, get, RecordedSleep())

    assert outcome.ok
    assert [i.title for i in outcome.items] == ["one"]
    assert get.requests == [(source.url, source.strategy.headers())]


def test_fetch_sends_a_json_strategy_its_own_headers(registry):
    get = ScriptedTransport((200, JSON))
    source = hosted_source(registry, "hf-daily-papers")

    outcome = fetch(source, get, RecordedSleep())

    assert outcome.ok and outcome.items[0].title == "A paper"
    url, headers = get.requests[0]
    assert url == source.url
    assert headers == source.strategy.headers()
    assert "application/json" in headers["Accept"]


def test_a_retryable_status_is_retried_until_it_succeeds(registry):
    get = ScriptedTransport((503, b""), (429, b""), (200, RSS))
    sleep = RecordedSleep()

    outcome = fetch(hosted_source(registry, "reddit-rva"), get, sleep)

    assert outcome.ok
    assert len(get.requests) == 3
    assert sleep.calls == BACKOFF


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_the_retry_budget_is_three_attempts(registry, status):
    get = ScriptedTransport(*[(status, b"")] * 3)      # a fourth call would fail
    sleep = RecordedSleep()

    outcome = fetch(hosted_source(registry, "reddit-rva"), get, sleep)

    assert not outcome.ok and outcome.error == f"HTTP {status}"
    assert len(get.requests) == 3
    assert sleep.calls == BACKOFF


def test_a_deterministic_4xx_fails_without_retrying(registry):
    get = ScriptedTransport((403, b""))                 # a retry would fail
    sleep = RecordedSleep()

    outcome = fetch(hosted_source(registry, "reddit-rva"), get, sleep)

    assert not outcome.ok and outcome.error == "HTTP 403"
    assert len(get.requests) == 1
    assert sleep.calls == []


def test_a_missing_feed_is_a_deterministic_failure(registry):
    get = ScriptedTransport((404, b""))

    outcome = fetch(hosted_source(registry, "reddit-rva"), get, RecordedSleep())

    assert not outcome.ok and outcome.error == "HTTP 404"


def test_a_transport_failure_is_retried_and_then_reported(registry):
    get = ScriptedTransport(*[TransportError("dns is down")] * 3)
    sleep = RecordedSleep()

    outcome = fetch(hosted_source(registry, "reddit-rva"), get, sleep)

    assert not outcome.ok
    assert outcome.error == "fetch failed: dns is down"
    assert len(get.requests) == 3
    assert sleep.calls == BACKOFF


def test_a_transport_failure_can_be_followed_by_success(registry):
    get = ScriptedTransport(TransportError("connection reset"), (200, RSS))

    outcome = fetch(hosted_source(registry, "reddit-rva"), get, RecordedSleep())

    assert outcome.ok


def test_fetch_bytes_raises_rather_than_returning_an_outcome(registry):
    """The fixture path must fail loudly — a snapshot is only written for a
    response that actually arrived."""
    get = ScriptedTransport((403, b""))

    with pytest.raises(FetchError, match="HTTP 403"):
        fetch_bytes(hosted_source(registry, "reddit-rva"), get, RecordedSleep())


def test_the_http_seam_has_no_default_adapter(registry):
    """D5: no module-level default, so the offline suite cannot reach the
    network by forgetting an argument."""
    source = hosted_source(registry, "reddit-rva")

    for call in (
        lambda: fetch(source),
        lambda: fetch_bytes(source),
        lambda: store.read(source, registry.feed),
    ):
        with pytest.raises(TypeError):
            call()
