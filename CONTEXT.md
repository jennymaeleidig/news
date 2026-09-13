# Personal source log

A log of where the owner reads: one flat registry of sources, and per-source
RSS feeds as its renderings. Sources a reader can fetch itself are subscribed
to directly; for the rest, this repo generates and publishes a feed.

## Language

### The registry

**Source**:
One unique place to read, recorded as a row in the registry — either a
**Direct source** or a **Hosted source**.
_Avoid_: channel, stream

**Direct source**:
A source whose own URL a reader subscribes to as-is; nothing is generated
for it.
_Avoid_: pure, raw

**Hosted source**:
A source a reader cannot fetch itself — it needs filtering, a format
conversion, or a request header — so this repo generates one RSS feed for
it.
_Avoid_: proxied, transformed

**Registry**:
The single source of truth for every source: one flat file that the direct
table, the index page, and the OPML are all rendered from.
_Avoid_: catalog, inventory, config

### What gets read

**Feed**:
The subscribable thing — a Direct source's own URL, or a Hosted source's
generated RSS document. One term, two origins.
_Avoid_: output, channel, XML

**Item**:
An entry in a feed: title, link, summary, publish date, carried verbatim
from upstream — hosting changes delivery, never identity.
_Avoid_: article, post, story, digest entry

### The hosted pipeline

Direct sources touch none of this.

**Fetch**:
The stage that pulls items from a hosted source's upstream endpoint, using
that source's **Strategy**.
_Avoid_: scrape, crawl

**Freshness**:
A hosted source's signal of whether fetch is currently succeeding: fresh
while upstream fetches keep succeeding, stale once they stop and
last-known-good is being re-served. Direct sources have none — they are
never fetched here.
_Avoid_: health, liveness, status

**Run**:
One hosted source's result within one generation: its **Run state**, the
item count it published, the emitted feed's lastBuildDate (the
**Freshness** stamp), and any error or note.
_Avoid_: job, task, execution

**Run state**:
A source's three-valued outcome for one run — `ok` (upstream fetched),
`stale` (fetch failed, predecessor re-emitted unchanged), or `failed`
(fetch failed with nothing to re-emit either). It is the machine-readable
spelling of **Freshness**: the one word the console line, the Job Summary
row, and the annotation all spell (`summary_word`). The index badge marks
`failed` server-side and ages every other state from the emitted stamp.
_Avoid_: status, health, result code

**Strategy**:
A hosted source's named shape (`topic_filter`, `passthrough`, `json_api`):
its request headers, its parser, its filter, and its parameters. One
strategy spans the Fetch and Transform stages.
_Avoid_: fetcher, handler, fetch config

**Transform**:
The stage that applies a hosted source's **Strategy** filter to upstream
items — pure filtering and field mapping, never the network.
_Avoid_: conversion

**Publication**:
The stage that renders and ships the published site: each hosted feed
merges with its live published predecessor under the retention cap, a
failed source re-emits last-known-good, and the index, direct table, and
OPML are rendered here.
_Avoid_: deploy, build, release

**Published store**:
The feed as currently published on Pages, read back as this run's
predecessor. The published site is the store (ADR-0004): a hosted feed
merges the fresh upstream fetch against it, so state lives in the
artifact, not in the repo.
_Avoid_: state file, cache, database
