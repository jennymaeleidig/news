# news-digest-agent

A personal source log that publishes RSS feeds. `sources.toml` is the
registry — 26 feeds worth reading, 20 of them subscribed directly in a
reader app, 6 published by this repo at `https://jennymaeleidig.github.io/news-digest-agent/`.

## The site

| Path | What it is |
|------|------------|
| `/` | The index: hosted feeds with a freshness stamp, direct sources with the URL to paste into a reader |
| `/opml.xml` | All 26 sources as one flat OPML file, importable anywhere |
| `/feeds/<id>.xml` | A feed this repo publishes for a hosted source (arXiv filtered to the LLM/SE subset, Hugging Face Daily Papers, the two Reddits, the Richmond Times-Dispatch) |
| [`docs/direct-feeds.md`](docs/direct-feeds.md) | The 20 direct sources as a committed table |

## How it works

One hourly workflow (`publish-feeds.yml`, at :23) runs the pipeline:

```
registry → fetch → transform → merge → emit → publish
```

- **fetch** — each hosted source is fetched with a browser-like client
  (bounded retry on 429/5xx, deterministic 4xx fail fast).
- **transform** — filters only. `topic_filter` keeps items matching the
  source's term list (the arXiv firehoses); `passthrough` and `json_api`
  change nothing. Item identity is never rewritten: upstream's
  title/link/GUID/date pass through verbatim.
- **merge** — the fresh fetch is merged against the feed as currently
  published: wholesale replace on duplicate guids (upstream wins), items
  older than 30 days drop out, newest first (guid ascending on ties),
  capped at 100 items.
- **emit** — hand-rolled RSS 2.0 on the stdlib, deterministic for goldens.
- **publish** — the site is published to GitHub Pages as an artifact.

**The published site is the store.** There is no database and no state
directory: each run merges against the live published feed, so state lives
in the artifact subscribers read.

**Failures stay green.** When an upstream fetch fails, its feed is
re-emitted byte-for-byte from the predecessor (channel `lastBuildDate`
still marks the last successful fetch), the run logs a `::warning::`, and
the index's freshness badge turns stale after 3 hours. A frozen page ages
visibly instead of breaking.

## The registry

`sources.toml` is the single source of truth. A `direct` source's `url` is
what you subscribe to yourself; a `hosted` source is one a reader can't
fetch as-is (it needs a browser user-agent, or a filter, or has no feed at
all) and declares `why` it is hosted.

To add a source: append a `[[sources]]` block in display order, then
regenerate the committed direct table and commit both:

```sh
python -m feeds gen --direct-table docs/direct-feeds.md
```

(Table rendering is offline — it reads the registry only.) The next push
publishes the updated site.

## Tests

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

The suite is offline and runs in CI before the site is published. Feed fixtures live
in `tests/fixtures/<source-id>/`; refresh them manually with
`PYTHONPATH=. python scripts/refresh_fixture.py <source-id>` and review the
diff — see `CODING_STANDARDS.md`.

## Operations

- **Runs**: hourly at :23, on pushes touching `sources.toml`/`feeds/`, and
  via manual dispatch — see the [Actions tab](../../actions/workflows/publish-feeds.yml).
  The Job Summary table shows per-source state and `lastBuildDate`.
- **No secrets.** The digest era's API keys are gone; every upstream is
  keyless.
- **Bringing the site up (or back up):** run
  [`scripts/setup-pages.sh`](scripts/setup-pages.sh) — a 5-stage wizard that
  enables Pages (Source: **GitHub Actions**), pushes `main`, watches the
  first run, checks the live OPML, and re-enables the workflow if GitHub
  disabled it. Idempotent, so re-running is safe. By hand: Settings → Pages
  → Build and deployment → Source: **GitHub Actions**, then push.
- **Scheduled workflows auto-disable after 60 days of no repo activity.**
  That's stage 5 of the wizard; by hand, enable the workflow from its
  Actions page (or make any commit). The next run catches the feeds back up
  by merging upstream against the feeds already published.

## License

CC0-1.0 — see [LICENSE](LICENSE) and [CITATION.cff](CITATION.cff).
