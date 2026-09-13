"""The strategy modules: each owns its config validation, its request headers,
its parser, and its filter. A strategy receives bytes and returns Items — it
never performs I/O.

Hosting never changes item identity, so a filter may only *drop* items;
titles, links, guids, and dates pass through verbatim. `passthrough` is the
only strategy the registry declares today, and it is built here from a config
block rather than read out of `sources.toml`.
"""

import re

import pytest

from feeds.strategies import names, passthrough, resolve
from feeds.strategies.base import StrategyConfigError, rss_headers
from feeds.strategies.rss import last_build_date, parse

from conftest import make_item

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

# A weekend-shaped channel: no items, and a <skipDays> pair the parser must
# report in full (feedparser 6.x exposes the last <day> only).
SKIP_DAYS_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>weekend-free</title><link>https://up.example/</link><description>d</description>
<skipDays><day>Saturday</day><day>Sunday</day></skipDays>
</channel></rss>
"""


def passthrough_strategy():
    return passthrough.build({"name": "passthrough"})


# --- the resolver ---------------------------------------------------------

def test_names_lists_the_declared_strategies():
    assert names() == ("passthrough",)


def test_resolve_maps_a_name_to_its_module():
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


def test_skip_days_note_names_every_declared_day():
    # feedparser 6.x accumulates nothing for <skipDays>: it exposes the last
    # <day> only and an empty 'skipdays'. The regex over raw bytes is
    # load-bearing, so the upstream shape pins its own full list (D8).
    declared = re.findall(r"<day>\s*([^<]+?)\s*</day>", SKIP_DAYS_RSS.decode())
    assert declared == ["Saturday", "Sunday"]          # the weekend pair, not last-only

    outcome = parse(SKIP_DAYS_RSS)
    assert outcome.ok and outcome.items == []
    for day in declared:
        assert day in outcome.note


def test_rss_parse_error_is_an_outcome_not_an_exception():
    outcome = parse(b"not a feed at all")
    assert not outcome.ok and "parse" in outcome.error.lower()


# --- passthrough ----------------------------------------------------------

def test_passthrough_is_identity():
    items = [make_item("1"), make_item("2")]
    strategy = passthrough_strategy()
    assert strategy.filter(items) is items


def test_passthrough_takes_no_params():
    strategy = passthrough_strategy()
    assert strategy.name == "passthrough"
    assert strategy.snapshot_filename == "upstream.xml"


def test_passthrough_rejects_unknown_params():
    """A typo'd key is a loud registry error, not a silently ignored param."""
    with pytest.raises(StrategyConfigError, match="unknown param"):
        passthrough.build({"name": "passthrough", "terms": ["llm"]})


# --- headers --------------------------------------------------------------

def test_passthrough_sends_browser_rss_headers():
    headers = passthrough_strategy().headers()
    assert headers == rss_headers()
    assert "Mozilla/5.0" in headers["User-Agent"]
    assert "application/rss+xml" in headers["Accept"]
