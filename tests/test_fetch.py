"""Fetch transport: the raw-body path fixture snapshots use, and the
strategy-dispatched outcome. Retry, backoff, and status classification get
their own seam in the transport landing; until then the HTTP call itself is
monkeypatched. No test touches the network.

SPDX-License-Identifier: CC0-1.0
"""

import requests

from feeds import fetch as fetch_mod
from feeds.fetch import fetch, fetch_bytes

from conftest import hosted_source

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>upstream</title><link>https://up.example/</link><description>d</description>
<item><title>one</title><link>https://up.example/1</link></item>
</channel></rss>
"""


def _response(content: bytes) -> object:
    return type("Resp", (), {"content": content, "status_code": 200})()


def test_fetch_bytes_returns_upstream_bytes_untouched(registry, monkeypatch):
    """The fixture snapshot must be upstream's own bytes, not a re-render."""
    raw = b"whatever upstream sent\xff\xfe"
    monkeypatch.setattr(fetch_mod, "_fetch_response", lambda url, headers: _response(raw))

    source = hosted_source(registry, "hf-daily-papers")
    assert fetch_bytes(source) == raw


def test_fetch_parses_the_body_with_the_source_strategy(registry, monkeypatch):
    seen = {}

    def fake_get(url, headers):
        seen["url"] = url
        seen["headers"] = headers
        return _response(RSS)

    monkeypatch.setattr(fetch_mod, "_fetch_response", fake_get)

    source = hosted_source(registry, "reddit-rva")
    outcome = fetch(source)
    assert outcome.ok
    assert [i.title for i in outcome.items] == ["one"]
    assert seen["url"] == source.url                    # the hosted source's upstream
    assert seen["headers"] == source.strategy.headers()  # headers belong to the strategy


def test_fetch_maps_a_raised_http_error_to_a_status(registry, monkeypatch):
    def fake_get(url, headers):
        raise requests.HTTPError("HTTP 403", response=type("R", (), {"status_code": 403})())

    monkeypatch.setattr(fetch_mod, "_fetch_response", fake_get)

    outcome = fetch(hosted_source(registry, "reddit-rva"))
    assert not outcome.ok
    assert outcome.error == "HTTP 403"


def test_fetch_maps_a_transport_error_to_an_outcome(registry, monkeypatch):
    def fake_get(url, headers):
        raise requests.ConnectionError("dns is down")

    monkeypatch.setattr(fetch_mod, "_fetch_response", fake_get)

    outcome = fetch(hosted_source(registry, "reddit-rva"))
    assert not outcome.ok
    assert "fetch failed" in outcome.error
