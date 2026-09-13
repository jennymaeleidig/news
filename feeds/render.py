"""Render the human surfaces from the registry: the Pages index, the OPML
file, the direct-feeds markdown table, and the two CI surfaces — the Job
Summary table and the `::warning::` annotations.

Layout is ticket 07's variant A: two stacked sections — hosted feeds (with
a freshness column) on top, direct sources (with the URL to paste into a
reader) beneath. Freshness is stamped server-side (data-built) and rendered
client-side by a few lines of JS, so a frozen page ages visibly; a stamp
older than 3 hours turns the badge stale (ticket 11). The failed badge
marker, the summary word and the annotation all read
`feeds.run.RunState`, so they cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from feeds import store
from feeds.emit import rfc2822
from feeds.run import RunState, SourceRun


def _hostname(url: str) -> str:
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _iso_stamp(rfc2822: str) -> str:
    """ISO 8601 spelling of a Freshness stamp for the JS <code>Date.parse</code>."""
    try:
        return parsedate_to_datetime(rfc2822).isoformat()
    except (TypeError, ValueError):
        return ""


_CSS = """
  :root { --ink:#1a1a1a; --mut:#6b6b6b; --line:#e3e3e3; --bg:#fafaf8; --accent:#0b62d6; }
  * { box-sizing: border-box; }
  body { margin:0; padding:2.5rem 1.5rem; background:var(--bg); color:var(--ink);
         font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif; }
  main { max-width: 980px; margin: 0 auto; }
  h1 { font-size:1.45rem; margin:0 0 .25rem; }
  h2 { font-size:1.05rem; margin:2.2rem 0 .6rem; }
  .sub { color:var(--mut); margin:0 0 2rem; max-width:62ch; }
  table { border-collapse:collapse; width:100%; background:#fff; border:1px solid var(--line); }
  th, td { text-align:left; padding:.5rem .7rem; border-bottom:1px solid var(--line); vertical-align:top; }
  th { font-size:12px; text-transform:uppercase; letter-spacing:.5px; color:var(--mut); background:#f4f4f1; }
  tr:last-child td { border-bottom:none; }
  td a { color:var(--accent); text-decoration:none; }
  td a:hover { text-decoration:underline; }
  .tag { display:inline-block; font-size:11px; font-weight:600; padding:1px 8px;
         border-radius:99px; white-space:nowrap; }
  .tag.stale { background:#ffe9e3; color:#b3401f; }
  .tag.fresh { background:#e7f6ec; color:#1e7a3f; }
  .url { font:12px/1.4 ui-monospace,"SF Mono",Menlo,monospace; color:var(--mut); word-break:break-all; }
  .note { color:var(--mut); font-size:13px; }
"""

_FRESHNESS_JS = f"""
  (function () {{
    function stale(el) {{
      el.classList.remove("fresh");
      el.classList.add("stale");
      el.title = "upstream fetch failing — predecessor re-emitted";
    }}
    document.querySelectorAll("span[data-built]").forEach(function (el) {{
      if (el.dataset.state === "{RunState.FAILED}") {{ el.textContent = "fetch failed"; stale(el); return; }}
      var t = Date.parse(el.dataset.built);
      if (isNaN(t)) {{ el.textContent = "unknown"; stale(el); return; }}
      var mins = (Date.now() - t) / 60000;
      el.textContent = mins < 90 ? Math.max(1, Math.round(mins)) + " min ago"
                     : mins < 2880 ? Math.round(mins / 60) + " hours ago"
                     : Math.round(mins / 1440) + " days ago";
      if (mins > 180) stale(el);  // stale only once older than 3 hours
    }});
  }})();
"""


def _freshness_span(run: SourceRun) -> str:
    if run.state is RunState.FAILED:
        return f'<span class="tag stale" data-built="" data-state="{RunState.FAILED}"></span>'
    iso = _iso_stamp(run.last_build).replace('"', "&quot;")
    return f'<span class="tag fresh" data-built="{iso}"></span>'


def _site_link(site: str) -> str:
    if not site:
        return "—"
    host = _hostname(site)
    return f'<a href="{escape(site)}">{escape(host or site)}</a>'


def render_index(registry, runs: list[SourceRun], built_at: datetime) -> str:
    by_id = {run.source_id: run for run in runs}

    hosted_rows = []
    for source in registry.hosted():
        run = by_id[source.id]
        feed_href = store.address(registry.feed, source)
        name_cell = (
            f'<a href="{escape(feed_href)}"><b>{escape(source.name)}</b></a><br>'
            f'<span class="url">{escape(store.path(source))}</span>'
        )
        hosted_rows.append(
            "<tr>"
            f"<td>{name_cell}</td>"
            f"<td>{_site_link(source.site)}</td>"
            f"<td>{escape(source.why) if source.why else ''}</td>"
            f"<td>{_freshness_span(run)}</td>"
            "</tr>"
        )

    direct_rows = []
    for source in registry.direct():
        direct_rows.append(
            "<tr>"
            f"<td><b>{escape(source.name)}</b></td>"
            f"<td>{_site_link(source.site)}</td>"
            f"<td>{escape(source.note) if source.note else ''}</td>"
            f'<td><span class="url">{escape(source.url)}</span></td>'
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(registry.feed.title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>{escape(registry.feed.title)}</h1>
<p class="sub">{escape(registry.feed.description)}</p>
<h2>Hosted feeds · generated here</h2>
<table><thead><tr><th>Feed</th><th>Site</th><th>Why it's here</th><th>Last upstream fetch</th></tr></thead>
<tbody>{''.join(hosted_rows)}</tbody></table>
<h2>Direct sources · subscribe to these yourself</h2>
<table><thead><tr><th>Source</th><th>Site</th><th>Why it's here</th><th>Feed URL (paste into your reader)</th></tr></thead>
<tbody>{''.join(direct_rows)}</tbody></table>
<p class="note">OPML at <a href="/opml.xml"><span class="url">/opml.xml</span></a> · direct table also in the repo at <span class="url">docs/direct-feeds.md</span></p>
</main>
<script>{_FRESHNESS_JS}</script>
</body>
</html>
"""


def render_opml(registry, built_at: datetime) -> bytes:
    opml = ET.Element("opml", {"version": "2.0"})
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = registry.feed.title
    ET.SubElement(head, "dateCreated").text = rfc2822(built_at)
    body = ET.SubElement(opml, "body")

    for source in registry.sources:
        attrs = {"text": source.name, "type": "rss"}
        if source.mode == "hosted":
            attrs["xmlUrl"] = store.address(registry.feed, source)
        else:
            attrs["xmlUrl"] = source.url
        if source.site:
            attrs["htmlUrl"] = source.site
        ET.SubElement(body, "outline", attrs)

    body_xml = ET.tostring(opml, encoding="unicode", short_empty_elements=True)
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + body_xml + "\n").encode("utf-8")


def render_direct_table(registry) -> str:
    rows = []
    for source in registry.direct():
        site = f"[{_hostname(source.site)}]({source.site})" if source.site else "—"
        note = escape(source.note) if source.note else ""
        rows.append(
            f"| {escape(source.name)} | {site} | {note} | `{source.url}` |"
        )
    table = "\n".join(rows)
    return f"""\

# Direct feeds

The sources you subscribe to in your reader — no feed is generated for
them here. Generated from [`sources.toml`](../sources.toml); edit the
registry, not this file:

```
python -m feeds gen --direct-table docs/direct-feeds.md
```

| Source | Site | Why it's here | Feed URL |
|--------|------|---------------|----------|
{table}
"""


# --- the CI surfaces ------------------------------------------------------

_SUMMARY_HEADER = (
    "| Feed | State | Items | lastBuildDate | Note |\n"
    "|------|-------|-------|---------------|------|\n"
)


def _cell(text: str) -> str:
    """Keep a value inside one markdown table cell: no raw pipe, no newline."""
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_job_summary(runs: list[SourceRun], built_at: datetime) -> str:
    """The Actions Job Summary: one markdown row per source.

    The state cell is `RunState.summary_word` — the same word the console log
    prints — so the two surfaces cannot disagree.
    """
    lines = [f"Fetched at {built_at.isoformat()}\n", "\n", _SUMMARY_HEADER]
    lines += [
        f"| {_cell(run.source_id)} | {run.state.summary_word} | {run.item_count} "
        f"| {_cell(run.last_build)} | {_cell(run.error or run.note)} |\n"
        for run in runs
    ]
    return "".join(lines)


def _escape_annotation_body(text: str) -> str:
    """Escape a workflow-command message body (D9).

    GitHub Actions reads annotation bodies until the line ends, so an
    unescaped LF truncates the message or injects a second command. The
    escapes are from actions/toolkit's `escapeData`: `%` first, since the
    others introduce a `%`.
    """
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def render_annotations(runs: list[SourceRun]) -> list[str]:
    """The `::warning::` lines for this run's errored sources.

    The bare, property-less command form is kept; only the message body is
    escaped, so a `%` or a newline in an error keeps the annotation intact.
    """
    lines = []
    for run in runs:
        if not run.error:
            continue
        word = run.state.summary_word
        body = f"source {run.source_id}: {run.error} ({word})"
        lines.append(f"::warning::{_escape_annotation_body(body)}")
    return lines
