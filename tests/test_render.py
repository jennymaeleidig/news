"""Rendered surfaces: index (variant A), OPML, direct table, and the two CI
surfaces — the Job Summary table and the `::warning::` annotations."""

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from xml.sax.saxutils import escape

import pytest

from feeds.render import (
    render_annotations,
    render_direct_table,
    render_index,
    render_job_summary,
    render_opml,
)
from feeds.run import RunState, SourceRun

from conftest import BUILT_AT

RUNS = [
    SourceRun(source_id="arxiv-cl", state=RunState.OK, item_count=12,
              last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
    SourceRun(source_id="reddit-rva", state=RunState.STALE, item_count=0,
              last_build="Sun, 13 Sep 2026 11:02:33 +0000", error="HTTP 403"),
    SourceRun(source_id="hf-daily-papers", state=RunState.FAILED, item_count=0,
              last_build="Sun, 13 Sep 2026 12:00:00 +0000", error="HTTP 500"),
    SourceRun(source_id="arxiv-se", state=RunState.OK, item_count=3,
              last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
    SourceRun(source_id="reddit-localllama", state=RunState.OK, item_count=9,
              last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
    SourceRun(source_id="richmond-times-dispatch", state=RunState.OK, item_count=40,
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


def test_the_index_js_reads_the_badge_state_from_the_vocabulary(registry):
    # The client-side branch and the server-side stamp both spell the failed
    # state from RunState, so a renamed state cannot leave the JS behind.
    html = render_index(registry, RUNS, BUILT_AT)
    assert f'el.dataset.state === "{RunState.FAILED}"' in html
    assert f'data-state="{RunState.FAILED}"' in html


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


# --- the Job Summary surface ---------------------------------------------

def test_render_job_summary_stamps_the_run_and_lists_every_source():
    summary = render_job_summary(RUNS, BUILT_AT)
    assert summary.startswith(f"Fetched at {BUILT_AT.isoformat()}")
    assert "| Feed | State | Items | lastBuildDate | Note |" in summary
    # the header row plus one row per run
    assert summary.count("\n| ") == len(RUNS) + 1
    for run in RUNS:
        assert run.source_id in summary
        assert run.state.summary_word in summary            # the shared vocabulary
    assert "HTTP 403" in summary                             # error fills the note column


def test_render_job_summary_keeps_a_pathological_note_on_one_row():
    runs = [SourceRun(source_id="x", state=RunState.STALE, error="a | b\nc")]
    row = [line for line in render_job_summary(runs, BUILT_AT).splitlines()
           if line.startswith("| x ")][0]
    assert "a \\| b c" in row


# --- the annotation surface ----------------------------------------------

def test_render_annotations_covers_only_errored_sources():
    assert render_annotations(RUNS) == [
        "::warning::source reddit-rva: HTTP 403 (STALE — predecessor re-emitted)",
        "::warning::source hf-daily-papers: HTTP 500 (FAILED — empty channel)",
    ]


@pytest.mark.parametrize("raw, escaped", [
    ("cookie=9%", "cookie=9%25"),
    ("two\nlines", "two%0Alines"),
    ("cr\rhere", "cr%0Dhere"),
    ("already %0A escaped", "already %250A escaped"),   # '%' is escaped first
])
def test_annotation_body_escapes_workflow_command_metacharacters(raw, escaped):
    [line] = render_annotations(
        [SourceRun(source_id="s", state=RunState.FAILED, error=raw)]
    )
    assert line.startswith("::warning::")            # the bare, property-less form
    assert escaped in line
    assert not any(ch in line for ch in "\r\n")      # one intact annotation


def test_annotations_are_one_per_error():
    assert len(render_annotations(RUNS)) == 2

