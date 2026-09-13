"""Fetch-level mapping: feedparser entries → Items (shared by the live fetch
and the merge's predecessor read), the registry-driven json_api shape, and
raw-body fetching for fixture snapshots. No test touches the network.

SPDX-License-Identifier: CC0-1.0
"""

import json

from feeds import fetch as fetch_mod
from feeds.fetch import fetch_bytes, parse_feed_bytes, parse_json_bytes
from feeds.registry import Strategy

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>upstream</title><link>https://up.example/</link><description>d</description>
<lastBuildDate>Sun, 13 Sep 2026 11:02:33 +0000</lastBuildDate>
<item>
  <title>http permalink, no guid</title>
  <link>http://up.example/post/1</link>
  <pubDate>Sun, 13 Sep 2026 10:00:00 +0000</pubDate>
  <description>body &amp; more</description>
</item>
<item>
  <title>upstream guid</title>
  <link>https://up.example/post/2</link>
  <guid isPermaLink="false">t3_2</guid>
  <description><![CDATA[<p>html</p>]]></description>
</item>
<item><title>no link, unusable</title></item>
</channel></rss>
"""

HF_PARAMS = {
    "name": "json_api",
    "item": "$",
    "title": "paper.title",
    "link": "paper.id",
    "link_prefix": "https://huggingface.co/papers/",
    "date": "paper.submittedOnDailyAt",
    "summary": "paper.summary",
    "upvotes": "paper.upvotes",
    "description": "▲ {upvotes} — {summary}",
}


def hf_strategy(**overrides) -> Strategy:
    return Strategy(name="json_api", params={**HF_PARAMS, **overrides})


def hf_payload(**paper_overrides) -> bytes:
    paper = {
        "id": "2409.12345",
        "title": "A paper",
        "summary": "The abstract.",
        "upvotes": 7,
        "submittedOnDailyAt": "2026-09-13T00:00:00.000Z",
        **paper_overrides,
    }
    return json.dumps([{"paper": paper}]).encode()


def test_entries_map_with_guid_fallback_and_scheme_normalization():
    outcome = parse_feed_bytes(RSS)
    assert outcome.ok and outcome.note is None
    assert len(outcome.items) == 2                     # the link-less entry is dropped

    normalized = outcome.items[0]
    assert normalized.link == "https://up.example/post/1"   # http upgraded
    assert normalized.guid == normalized.link          # no upstream guid: link is the guid

    explicit = outcome.items[1]
    assert explicit.guid == "t3_2"                     # upstream guid wins over the link
    assert explicit.description == "<p>html</p>"       # verbatim upstream HTML


def test_predecessor_read_uses_the_same_mapping(registry):
    """The merge reads our own feed back; it must map identically to a fetch."""
    from feeds import merge

    items = merge.parse_predecessor(RSS)
    fetched = parse_feed_bytes(RSS).items
    assert [(i.title, i.link, i.guid, i.description) for i in items] == \
           [(i.title, i.link, i.guid, i.description) for i in fetched]


def test_json_api_shape_comes_from_the_strategy_block():
    outcome = parse_json_bytes(hf_payload(), hf_strategy())
    assert outcome.ok
    item = outcome.items[0]
    assert item.link == "https://huggingface.co/papers/2409.12345"
    assert item.guid == item.link                      # HF has no upstream guid
    assert item.title == "A paper"
    assert item.description == "▲ 7 — The abstract."
    assert item.published is not None and item.published.year == 2026
    assert item.published_raw == "2026-09-13T00:00:00.000Z"


def test_json_api_description_falls_back_when_upvotes_are_missing():
    outcome = parse_json_bytes(hf_payload(upvotes=None), hf_strategy())
    assert outcome.items[0].description == "The abstract."   # not "▲  — The abstract."


def test_json_api_without_a_link_prefix_uses_the_raw_value():
    outcome = parse_json_bytes(hf_payload(), hf_strategy(link_prefix=""))
    assert outcome.items[0].link == "2409.12345"


def test_json_api_reports_an_item_path_that_does_not_resolve():
    outcome = parse_json_bytes(b"{}", hf_strategy())
    assert not outcome.ok and "'$'" in outcome.error


def test_json_api_reports_invalid_json():
    outcome = parse_json_bytes(b"not json", hf_strategy())
    assert not outcome.ok and "invalid JSON" in outcome.error


def test_fetch_bytes_returns_upstream_bytes_untouched(registry, monkeypatch):
    """The fixture snapshot must be upstream's own bytes, not a re-render."""
    raw = b"whatever upstream sent\xff\xfe"
    monkeypatch.setattr(fetch_mod, "_fetch_response", lambda url, headers: type(
        "Resp", (), {"content": raw})())

    source = [s for s in registry.hosted() if s.id == "hf-daily-papers"][0]
    assert fetch_bytes(source) == raw
