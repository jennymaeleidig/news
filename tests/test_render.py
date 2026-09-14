"""Rendered surfaces: index (variant A), OPML, direct table, and the two CI
surfaces — the Job Summary table and the `::warning::` annotations.

The registry here is built by hand: rendering reads the rows it is handed,
so a source added to or removed from `sources.toml` cannot break these
tests, and the states a badge can carry are all in one place.
"""

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

from conftest import (
    BUILT_AT,
    TEST_FEED,
    direct_source,
    registry_of,
    rss_source,
)

REGISTRY = registry_of(
    rss_source("alpha", name="Alpha", note="Why Alpha is worth reading.",
               why="Alpha 403s a reader app's user agent."),
    rss_source("beta", name="Beta", why="Beta has no feed at all."),
    rss_source("gamma", name="Gamma", why="Gamma is rate-limited upstream."),
    direct_source("delta", name="Delta", url="https://delta.example/feed.xml",
                  site="https://delta.example", note="Delta is read directly."),
)

RUNS = [
    SourceRun(source_id="alpha", state=RunState.OK, item_count=12,
              last_build="Sun, 13 Sep 2026 12:00:00 +0000"),
    SourceRun(source_id="beta", state=RunState.STALE, item_count=0,
              last_build="Sun, 13 Sep 2026 11:02:33 +0000", error="HTTP 403"),
    SourceRun(source_id="gamma", state=RunState.FAILED, item_count=0,
              last_build="Sun, 13 Sep 2026 12:00:00 +0000", error="HTTP 500"),
]


def test_opml_lists_all_sources_flat():
    xml = render_opml(REGISTRY, BUILT_AT)
    root = ET.fromstring(xml)
    outlines = root.findall("./body/outline")
    assert len(outlines) == len(REGISTRY.sources)              # flat, no grouping
    by_text = {o.get("text"): o for o in outlines}
    hosted = by_text["Beta"]
    assert hosted.get("xmlUrl").endswith("/feeds/beta.xml")     # hosted: published URL
    direct = by_text["Delta"]
    assert direct.get("xmlUrl") == "https://delta.example/feed.xml"  # direct: subscribe URL
    assert direct.get("htmlUrl") == "https://delta.example"


def test_direct_table_lists_all_direct_sources():
    table = render_direct_table(REGISTRY)
    for source in REGISTRY.direct():
        assert source.name in table
        assert source.url in table
    assert "python -m feeds gen --direct-table" in table      # regen instructions
    assert "| Feed | Site | Why it's here | Feed URL |" in table  # same headers as the index
    body = table.split("|------|", 1)[1]                    # rows only
    for hosted in REGISTRY.hosted():
        assert hosted.name not in body


def test_both_index_tables_share_the_same_headers():
    # The two sections differ only in the hosted table's trailing freshness
    # column: Feed, Site, Why it's here, Feed URL read the same in both.
    html = render_index(REGISTRY, RUNS, BUILT_AT)
    shared = "<th>Feed</th><th>Site</th><th>Why it's here</th><th>Feed URL</th>"
    assert html.count(shared) == 2
    assert f"{shared}<th>Last upstream fetch</th>" in html


def test_index_renders_both_sections_with_freshness():
    html = render_index(REGISTRY, RUNS, BUILT_AT)
    assert "Hosted feeds · generated here" in html
    assert "Direct feeds · subscribe to these yourself" in html
    assert html.count('data-built="') == len(REGISTRY.hosted())  # every hosted row stamped
    assert 'data-state="failed"' in html                      # failed feed marked server-side
    assert "mins > 180" in html                               # stale only once older than 3 h
    assert "/feeds/alpha.xml" in html
    assert "https://delta.example/feed.xml" in html


def test_the_index_js_reads_the_badge_state_from_the_vocabulary():
    # The client-side branch and the server-side stamp both spell the failed
    # state from RunState, so a renamed state cannot leave the JS behind.
    html = render_index(REGISTRY, RUNS, BUILT_AT)
    assert f'el.dataset.state === "{RunState.FAILED}"' in html
    assert f'data-state="{RunState.FAILED}"' in html


def test_index_advertises_hosted_feeds_for_reader_autodiscovery():
    # A reader app handed the site URL finds the feeds this repo publishes
    # from these tags alone (Reeder's feed discovery reads them).
    html = render_index(REGISTRY, RUNS, BUILT_AT)
    for hosted in REGISTRY.hosted():
        href = f'{TEST_FEED.link.rstrip("/")}/feeds/{hosted.id}.xml'
        assert (
            f'<link rel="alternate" type="application/rss+xml" '
            f'title="{hosted.name}" href="{href}">'
        ) in html
    # Direct sources are subscribed to at their own addresses, not discovered here.
    assert 'title="Delta"' not in html


def test_discovery_titles_are_attribute_escaped():
    reg = registry_of(rss_source("amp", name='A & "B"', why="why"))
    html = render_index(
        reg, [SourceRun(source_id="amp", state=RunState.OK)], BUILT_AT,
    )
    assert 'title="A &amp; &quot;B&quot;"' in html


def test_hosted_rows_explain_the_hosting():
    # The "Why it's here" cell carries `why` (what forces the hosting), so a
    # hosted source with no note still explains itself. It used to render
    # `note`, which left the note-less rows blank under that header.
    html = render_index(REGISTRY, RUNS, BUILT_AT)
    for hosted in REGISTRY.hosted():
        assert escape(hosted.why) in html
    note_less = [s for s in REGISTRY.hosted() if s.id == "beta"][0]
    assert note_less.note == "" and escape(note_less.why) in html  # the row that used to be blank


def test_index_has_no_digest_era_strings():
    html = render_index(REGISTRY, RUNS, BUILT_AT)
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
        "::warning::source beta: HTTP 403 (STALE — predecessor re-emitted)",
        "::warning::source gamma: HTTP 500 (FAILED — empty channel)",
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
