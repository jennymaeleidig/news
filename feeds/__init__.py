"""feeds — publish RSS feeds for the sources in sources.toml.

The pipeline is one direction: registry → fetch → transform → merge →
emit → publish. `fetch` and `publish` own I/O (HTTP, writing files);
`transform`, `merge`, and `emit` are pure and golden-file testable.

The published site is the store (ADR-0004): each hosted feed merges the
fresh upstream fetch against the feed currently published on Pages, so
state lives in the artifact, not in this repo. `store` owns that store's
layout and its read.
"""

from feeds.registry import Registry, Source, Strategy, load

__all__ = ["Registry", "Source", "Strategy", "load"]
