# The published site is the store

Generated feeds keep no local state file: each run fetches the **live
predecessor feed from the published GitHub Pages site** and merges it with
upstream (upstream wins on duplicate item identity; predecessor-only items
linger until the retention ceiling — 100 items / 30 days). A source whose
upstream fetch fails re-emits its predecessor unchanged, so last-known-good
output stays in place, and the deploy always runs unless generation itself
crashes.

Considered: stateless regeneration (loses accumulated items for sources
whose upstream windows are short, e.g. HF Daily Papers' daily page) and a
committed state file (an artifact deploy commits nothing, so state would
drift from what is published). Using the published site itself as the store
keeps state exactly where the output is.

Consequences: the generator reads its own output; corrupting or wiping the
published feed loses the accumulated history. First publication of a feed
starts empty.
