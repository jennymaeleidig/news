"""Load and validate sources.toml — the single source of truth.

The registry is the artifact (ADR-0003): this file is the owner's personal
log of sources, and the feeds are one rendering of it. The loader is strict
because everything downstream (public feed paths, the OPML, the index)
derives from it — a malformed registry should fail the run, not silently
publish a half-site. Each hosted source's `[sources.strategy]` block is
validated by its strategy module (`feeds.strategies`), which the loader
resolves by name.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from feeds.strategies import names as strategy_names, resolve as resolve_strategy
from feeds.strategies.base import Strategy, StrategyConfigError

DEFAULT_REGISTRY_PATH = "sources.toml"

_MODES = ("direct", "hosted")


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    mode: str          # "direct" | "hosted"
    url: str           # direct: the subscribe URL; hosted: the upstream we fetch
    site: str = ""
    why: str = ""      # hosted-only, required: what forces the hosting
    note: str = ""     # why the source is worth following; becomes the feed <description>
    strategy: Strategy | None = None


@dataclass(frozen=True)
class FeedMeta:
    """The log's own identity, rendered into channel elements and pages."""

    title: str
    link: str
    language: str = "en"
    description: str = ""
    description_template: str = "Items from {name}."

    def channel_description(self, source: Source) -> str:
        if source.note:
            return source.note
        return self.description_template.format(name=source.name)


@dataclass(frozen=True)
class Registry:
    feed: FeedMeta
    sources: tuple[Source, ...]

    def hosted(self) -> list[Source]:
        return [s for s in self.sources if s.mode == "hosted"]

    def direct(self) -> list[Source]:
        return [s for s in self.sources if s.mode == "direct"]


class RegistryError(ValueError):
    pass


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise RegistryError(message)


def load(path: str | Path = DEFAULT_REGISTRY_PATH) -> Registry:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    feed_raw = raw.get("feed")
    _require(isinstance(feed_raw, dict), "missing [feed] block")
    _require(bool(feed_raw.get("title")), "[feed] title is required")
    _require(bool(feed_raw.get("link")), "[feed] link is required")
    feed = FeedMeta(
        title=feed_raw["title"],
        link=feed_raw["link"],
        language=feed_raw.get("language", "en"),
        description=feed_raw.get("description", ""),
        description_template=feed_raw.get("description_template", "Items from {name}."),
    )

    sources_raw = raw.get("sources")
    _require(isinstance(sources_raw, list) and sources_raw, "[[sources]] must list at least one source")

    sources: list[Source] = []
    seen_ids: set[str] = set()
    for i, row in enumerate(sources_raw):
        label = f"sources[{i}]"
        for req in ("id", "name", "mode", "url"):
            _require(bool(row.get(req)), f"{label}: {req!r} is required")
        sid = row["id"]
        label = f"sources[{sid}]"
        _require(sid not in seen_ids, f"{label}: duplicate id")
        seen_ids.add(sid)

        mode = row["mode"]
        _require(mode in _MODES, f"{label}: mode must be one of {_MODES}")

        strategy_raw = row.get("strategy")
        why = row.get("why", "")

        if mode == "direct":
            _require(strategy_raw is None, f"{label}: a direct source must declare no strategy")
            _require(not why, f"{label}: a direct source needs no 'why' (it is only fetched when hosted)")
            strategy = None
        else:
            _require(bool(why), f"{label}: a hosted source must declare why it is hosted")
            _require(isinstance(strategy_raw, dict), f"{label}: a hosted source needs a [sources.strategy] block")
            name = strategy_raw.get("name")
            module = resolve_strategy(name) if isinstance(name, str) else None
            _require(module is not None, f"{label}: strategy must be one of {strategy_names()}")
            try:
                strategy = module.build(strategy_raw)
            except StrategyConfigError as e:
                raise RegistryError(f"{label}: {e}") from e

        sources.append(Source(
            id=sid,
            name=row["name"],
            mode=mode,
            url=row["url"],
            site=row.get("site", ""),
            why=why,
            note=row.get("note", ""),
            strategy=strategy,
        ))

    return Registry(feed=feed, sources=tuple(sources))
