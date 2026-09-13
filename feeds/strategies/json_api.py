"""json_api: a JSON API with dot-path field mapping.

The `[sources.strategy]` block carries the source's whole shape: dot-paths for
item/title/link/date, an optional `link_prefix` (HF papers have no absolute
URL upstream), and an optional description template whose `{placeholders}`
name other dot-path keys. Nothing about a particular API lives in code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from feeds.model import FetchOutcome, Item
from feeds.strategies.base import StrategyConfigError, json_headers, reject_unknown

NAME = "json_api"
_REQUIRED = ("item", "title", "link", "date")
# Every key a block may carry; the rest are template-resolvable dot-paths.
_ALLOWED = {"name", "item", "title", "link", "date", "summary", "upvotes",
            "link_prefix", "description"}
_DATE_FORMATS = ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d")


def build(block: dict) -> "JsonApi":
    """Validate a `[sources.strategy]` block into a typed strategy."""
    reject_unknown(block, _ALLOWED)
    for req in _REQUIRED:
        if not block.get(req):
            raise StrategyConfigError(f"json_api needs {req!r} (a dot-path)")
    return JsonApi(
        item=block["item"],
        title=block["title"],
        link=block["link"],
        date=block["date"],
        summary=block.get("summary", ""),
        upvotes=block.get("upvotes", ""),
        link_prefix=block.get("link_prefix", ""),
        description=block.get("description", ""),
    )


@dataclass(frozen=True)
class JsonApi:
    item: str
    title: str
    link: str
    date: str
    summary: str = ""
    upvotes: str = ""
    link_prefix: str = ""
    description: str = ""
    name: ClassVar[str] = NAME
    snapshot_filename: ClassVar[str] = "upstream.json"

    def headers(self) -> dict:
        return json_headers()

    def filter(self, items: list[Item]) -> list[Item]:
        return items       # identity: the field mapping is the whole strategy

    def parse(self, data: bytes) -> FetchOutcome:
        try:
            payload = json.loads(data)
        except ValueError as e:
            return FetchOutcome(items=[], error=f"invalid JSON: {e}")

        entries = _dig(payload, self.item)
        if not isinstance(entries, list):
            return FetchOutcome(
                items=[], error=f"item path {self.item!r} did not resolve to a list"
            )

        items = []
        for entry in entries:
            title = _dig(entry, self.title)
            ref = _dig(entry, self.link)
            if not title or not ref:
                continue
            link = f"{self.link_prefix}{ref}"
            summary = _dig(entry, self.summary) or ""
            raw_date = str(_dig(entry, self.date) or "")
            items.append(Item(
                title=str(title).strip(),
                link=link,
                guid=link,
                published=_parse_date(raw_date),
                published_raw=raw_date,
                description=self._compose_description(entry, summary),
            ))
        return FetchOutcome(items=items)

    def _compose_description(self, entry, fallback: str) -> str:
        """Render the template, else pass the summary through.

        A `{placeholder}` names another configured dot-path, so the template
        stays data: HF renders ``▲ {upvotes} — {summary}``. If a placeholder
        is unknown or resolves empty the plain summary wins — HF omits upvotes
        on some papers and "▲  — abstract" reads worse.
        """
        if not self.description:
            return fallback
        fields = {
            "item": self.item, "title": self.title, "link": self.link,
            "date": self.date, "summary": self.summary, "upvotes": self.upvotes,
        }
        values: dict[str, str] = {}
        for name in re.findall(r"\{([^}]+)\}", self.description):
            path = fields.get(name)
            if path is None:
                return fallback
            value = _dig(entry, path)
            if value in (None, ""):
                return fallback
            values[name] = str(value)
        return self.description.format(**values)


def _dig(data, path: str):
    """Resolve a dot-path against JSON-ish data; ``$`` is the whole document.
    Returns None when any key along the path is missing."""
    if path in ("", "$"):
        return data
    cur = data
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _parse_date(raw: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
