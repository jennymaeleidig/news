"""Strategy modules: each owns its config validation, its request headers,
its parser, and its filter. A strategy receives bytes and returns Items — it
never performs I/O.

Hosting never changes item identity (ADR-0003), so a filter may only *drop*
items; titles, links, guids, and dates pass through verbatim.
"""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from feeds.strategies import json_api, names, passthrough, resolve, topic_filter
from feeds.strategies.base import (
    StrategyConfigError,
    json_headers,
    rss_headers,
)
from feeds.strategies.rss import last_build_date, parse

from conftest import hosted_source, make_item

FIXTURES = Path(__file__).parent / "fixtures"

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

PAPER = {
    "id": "2409.12345",
    "title": "A paper",
    "summary": "The abstract.",
    "upvotes": 7,
    "submittedOnDailyAt": "2026-09-13T00:00:00.000Z",
}


def payload(**paper_overrides) -> bytes:
    paper = {**PAPER, **paper_overrides}
    return json.dumps([{"paper": paper}]).encode()


def hf_strategy(registry):
    return hosted_source(registry, "hf-daily-papers").strategy


# --- the resolver ---------------------------------------------------------

def test_names_lists_the_three_declared_strategies():
    assert names() == ("json_api", "passthrough", "topic_filter")


def test_resolve_maps_a_name_to_its_module():
    assert resolve("json_api") is json_api
    assert resolve("topic_filter") is topic_filter
    assert resolve("passthrough") is passthrough


def test_resolve_is_none_for_an_unknown_name():
    assert resolve("scrape_html") is None


# --- the shared RSS parser ------------------------------------------------

def test_rss_entries_map_with_guid_fallback_and_scheme_normalization():
    outcome = parse(RSS)
    assert outcome.ok and outcome.note is None
    assert len(outcome.items) == 2                     # the link-less entry is dropped

    normalized = outcome.items[0]
    assert normalized.link == "https://up.example/post/1"   # http upgraded
    assert normalized.guid == normalized.link          # no upstream guid: link is the guid

    explicit = outcome.items[1]
    assert explicit.guid == "t3_2"                     # upstream guid wins over the link
    assert explicit.description == "<p>html</p>"       # verbatim upstream HTML


def test_last_build_date_reads_the_channel_stamp():
    # feedparser maps <lastBuildDate> to 'updated'; this is the parser's
    # answer for the predecessor's freshness stamp (D10).
    assert last_build_date(RSS) == "Sun, 13 Sep 2026 11:02:33 +0000"


@pytest.mark.parametrize("source_id", ["arxiv-cl", "arxiv-se"])
def test_skip_days_note_names_every_declared_day(source_id):
    # feedparser 6.x accumulates nothing for <skipDays>: it exposes the last
    # <day> only and an empty 'skipdays'. The regex over raw bytes is
    # load-bearing, so each weekend fixture pins its own full list (D8).
    raw = (FIXTURES / source_id / "upstream.xml").read_bytes()
    declared = re.findall(r"<day>\s*([^<]+?)\s*</day>", raw.decode())
    assert declared == ["Saturday", "Sunday"]          # the weekend pair, not last-only

    outcome = parse(raw)
    assert outcome.ok and outcome.items == []
    for day in declared:
        assert day in outcome.note


def test_rss_parse_error_is_an_outcome_not_an_exception():
    outcome = parse(b"not a feed at all")
    assert not outcome.ok and "parse" in outcome.error.lower()


# --- topic_filter ---------------------------------------------------------

def test_topic_filter_keeps_title_and_description_matches(registry):
    items = [
        make_item("1", title="Kitten pictures considered harmful", description="<p>no terms</p>"),
        make_item("2", title="LLM agents for code review", description="we study <b>rlhf</b>"),
        make_item("3", title="City council zoning fight", description="prompt: nothing here"),
    ]
    kept = hosted_source(registry, "arxiv-cl").strategy.filter(items)
    assert [i.guid for i in kept] == ["2", "3"]  # title "LLM agents…"; description "prompt: …"


def test_topic_filter_is_case_insensitive(registry):
    items = [make_item("x", title="IN-CONTEXT LEARNING AT SCALE")]
    kept = hosted_source(registry, "arxiv-cl").strategy.filter(items)
    assert [i.guid for i in kept] == ["x"]


def test_topic_filter_validates_its_terms():
    with pytest.raises(StrategyConfigError, match="terms"):
        topic_filter.build({"name": "topic_filter"})
    with pytest.raises(StrategyConfigError, match="terms"):
        topic_filter.build({"name": "topic_filter", "terms": []})
    with pytest.raises(StrategyConfigError, match="terms"):
        topic_filter.build({"name": "topic_filter", "terms": ["ok", "  "]})


def test_topic_filter_config_is_typed():
    strategy = topic_filter.build({"name": "topic_filter", "terms": ["llm", "rlhf"]})
    assert strategy.name == "topic_filter"
    assert strategy.terms == ("llm", "rlhf")
    assert strategy.snapshot_filename == "upstream.xml"


# --- passthrough ----------------------------------------------------------

def test_passthrough_is_identity(registry):
    items = [make_item("1"), make_item("2")]
    strategy = hosted_source(registry, "reddit-rva").strategy
    assert strategy.filter(items) is items


def test_passthrough_takes_no_params():
    strategy = passthrough.build({"name": "passthrough"})
    assert strategy.name == "passthrough"
    assert strategy.snapshot_filename == "upstream.xml"


def test_every_strategy_rejects_unknown_params():
    """A typo'd key is a loud registry error, not a silently ignored param."""
    with pytest.raises(StrategyConfigError, match="unknown param"):
        topic_filter.build({"name": "topic_filter", "terms": ["llm"], "term": "x"})
    with pytest.raises(StrategyConfigError, match="unknown param"):
        passthrough.build({"name": "passthrough", "terms": ["llm"]})
    with pytest.raises(StrategyConfigError, match="unknown param"):
        json_api.build({"name": "json_api", "item": "$", "title": "t",
                        "link": "l", "date": "d", "extra": "x"})


# --- json_api -------------------------------------------------------------

def test_json_api_shape_comes_from_the_registered_strategy(registry):
    strategy = hf_strategy(registry)
    outcome = strategy.parse(payload())
    assert outcome.ok
    item = outcome.items[0]
    assert item.link == "https://huggingface.co/papers/2409.12345"
    assert item.guid == item.link                      # HF has no upstream guid
    assert item.title == "A paper"
    assert item.description == "▲ 7 — The abstract."
    assert item.published is not None and item.published.year == 2026
    assert item.published_raw == "2026-09-13T00:00:00.000Z"


def test_json_api_description_falls_back_when_upvotes_are_missing(registry):
    outcome = hf_strategy(registry).parse(payload(upvotes=None))
    assert outcome.items[0].description == "The abstract."   # not "▲  — The abstract."


def test_json_api_without_a_link_prefix_uses_the_raw_value(registry):
    strategy = replace(hf_strategy(registry), link_prefix="")
    assert strategy.parse(payload()).items[0].link == "2409.12345"


def test_json_api_reports_an_item_path_that_does_not_resolve(registry):
    outcome = hf_strategy(registry).parse(b"{}")
    assert not outcome.ok and "'$'" in outcome.error


def test_json_api_reports_invalid_json(registry):
    outcome = hf_strategy(registry).parse(b"not json")
    assert not outcome.ok and "invalid JSON" in outcome.error


def test_json_api_validates_its_dot_paths():
    with pytest.raises(StrategyConfigError, match="'link'"):
        json_api.build({
            "name": "json_api", "item": "$", "title": "t", "date": "d",
        })


def test_json_api_config_is_typed(registry):
    strategy = hf_strategy(registry)
    assert strategy.item == "$"
    assert strategy.title == "paper.title"
    assert strategy.snapshot_filename == "upstream.json"


# --- headers --------------------------------------------------------------

def test_rss_strategies_send_browser_rss_headers(registry):
    for source_id in ("arxiv-cl", "reddit-rva"):
        headers = hosted_source(registry, source_id).strategy.headers()
        assert headers == rss_headers()
        assert "Mozilla/5.0" in headers["User-Agent"]
        assert "application/rss+xml" in headers["Accept"]


def test_json_api_sends_json_headers(registry):
    headers = hf_strategy(registry).headers()
    assert headers == json_headers()
    assert "application/json" in headers["Accept"]
    assert "Mozilla/5.0" in headers["User-Agent"]
