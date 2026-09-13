"""Rendered surfaces: index (variant A), OPML, direct table."""

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from xml.sax.saxutils import escape

from feeds.publish import SourceRun
from feeds.render import render_direct_table, render_index, render_opml

from conftest import BUILT_AT

RUNS = [
    SourceRun(source_id="arxiv-cl", state="ok", item_count=12,
                 last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
    SourceRun(source_id="reddit-rva", state="stale", item_count=0,
                 last_build="Sun, 13 Sep 2026 11:02:33 +0000", error="HTTP 403"),
    SourceRun(source_id="hf-daily-papers", state="failed", item_count=0,
                 last_build="Sun, 13 Sep 2026 12:00:00 +0000", error="HTTP 500"),
    SourceRun(source_id="arxiv-se", state="ok", item_count=3,
                 last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
    SourceRun(source_id="reddit-localllama", state="ok", item_count=9,
                 last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
    SourceRun(source_id="richmond-times-dispatch", state="ok", item_count=40,
                 last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
]


def test_opml_lists_all_sources_flat(registry):
    xml = render_opml(registry, BUILT_AT)
    root = ET.fromstring(xml)
    outlines = root.findall("./body/outline")
    assert len(outlines) == 26                                # flat, no grouping
    by_text = {o.get("text"): o for o in outlines}
    hosted = by_text["Reddit r/rva"]
    assert hosted.get("xmlUrl").endswith("/feeds/reddit-rva.xml")  # hosted: published URL
    direct = by_text["404 Media"]
    assert direct.get("xmlUrl") == "https://www.404media.co/rss/"  # direct: subscribe URL
    assert direct.get("htmlUrl") == "https://www.404media.co"


def test_direct_table_lists_all_direct_sources(registry):
    table = render_direct_table(registry)
    for source in registry.direct():
        assert source.name in table
        assert source.url in table
    assert "python -m feeds gen --direct-table" in table      # regen instructions
    body = table.split("|--------|", 1)[1]                    # rows only
    for hosted in registry.hosted():
        assert hosted.name not in body


def test_index_renders_both_sections_with_freshness(registry):
    html = render_index(registry, RUNS, BUILT_AT)
    assert "Hosted feeds · generated here" in html
    assert "Direct sources · subscribe to these yourself" in html
    assert html.count('data-built="') == 6                    # every hosted row stamped
    assert 'data-state="failed"' in html                      # failed feed marked server-side
    assert "mins > 180" in html                               # stale only once older than 3 h
    assert "/feeds/arxiv-cl.xml" in html
    assert "https://www.404media.co/rss/" in html


def test_hosted_rows_explain_the_hosting(registry):
    # The "Why it's here" cell carries `why` (what forces the hosting), so a
    # hosted source with no note still explains itself. It used to render
    # `note`, which left the Reddit rows blank under that header.
    html = render_index(registry, RUNS, BUILT_AT)
    for hosted in registry.hosted():
        assert escape(hosted.why) in html
    rva = [s for s in registry.hosted() if s.id == "reddit-rva"][0]
    assert rva.note == "" and escape(rva.why) in html           # the row that used to be blank


def test_index_has_no_digest_era_strings(registry):
    html = render_index(registry, RUNS, BUILT_AT)
    # "digest" survives only inside the repo/site name news-digest-agent.
    for dead in ("curator", "openrouter", "resend", "category", "tier"):
        assert dead not in html.lower()
