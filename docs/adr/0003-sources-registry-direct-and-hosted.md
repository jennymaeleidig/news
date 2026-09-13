# Sources registry: direct and hosted sources

One flat `sources.toml` at the repo root is the single source of truth for
every source. Categories, sections, and trust tiers are gone. Each source
splits by **reader-fetchability, not transformation**: a **Direct** source's
own URL is subscribable as-is (nothing generated; the reader adds it by hand
from the shipped table), while a **Hosted** source needs filtering, a format
conversion, or a request header the reader cannot send — so this repo
generates one RSS feed per hosted source. Example of the rule: Reddit's
native `.rss` is clean and untransformed but needs a browser User-Agent
Reeder cannot send, so Reddit is Hosted; the User-Agent override on PBS was
ours, so PBS is Direct.

Considered: keeping categories with per-category digests; keeping trust
tiers as attribution. Rejected — the product is a personal source log whose
renderings are per-source feeds; grouping is the reader's job and the LLM
pipeline is deleted.

Consequences: explicit `id` slugs are identity and become the feed URLs
(`/feeds/<id>.xml`), so renaming a source id churns reader subscriptions.
