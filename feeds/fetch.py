"""Upstream fetching for hosted sources.

Retry and header mechanics are ported verbatim from the digest-era
fetchers/rss.py: bounded retry on transient causes (429/5xx blips,
network errors) with linear backoff, immediate raise on deterministic
4xx, and a full browser-like header set — some CDN-fronted feeds
(Substack/Cloudflare) 403 stripped-down clients even when the
User-Agent is fine. Advertise only encodings `requests` decodes without
extra deps (gzip, deflate).

Two fetch shapes exist, one per hosted strategy:
  rss        the normal case — parse the feed, map entries to Items
  json_api   HF Daily Papers — one JSON fetch, dot-path field mapping

The published store's read is its own module (feeds.store); this module
supplies the HTTP adapter it runs on, because retry and headers are HTTP
concerns. `last_build_date` is the RSS parser's answer for the
predecessor's stamp.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import feedparser
import requests

from feeds.model import FetchOutcome, Item, items_from_entries

# Browser impersonation shared by every outbound request. Reddit 403s
# non-browser agents; PBS 202-empties some impersonation strings but
# serves this one; richmond.com rate-limits plain clients.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_REQUEST_HEADERS = {
    "Accept": (
        "application/rss+xml, application/atom+xml, "
        "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

_HTTP_TIMEOUT_SECONDS = 30
_FETCH_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _fetch_response(url: str, headers: dict) -> requests.Response:
    """GET ``url`` with bounded retry on transient causes.

    Raises the last RequestException, or a requests.HTTPError carrying the
    final status, only once the retry budget is exhausted. A deterministic
    status (403/404 and other non-retryable 4xx) raises immediately —
    the answer won't change on retry.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _FETCH_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=_HTTP_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
        except requests.RequestException as e:
            last_exc = e
        else:
            if resp.status_code < 400:
                return resp
            if resp.status_code not in _RETRYABLE_STATUSES:
                resp.raise_for_status()  # deterministic: fail now
            last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
        if attempt < _FETCH_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise last_exc  # type: ignore[misc]


def _headers(extra_user_agent: str | None = None) -> dict:
    ua = extra_user_agent or BROWSER_USER_AGENT
    return {"User-Agent": ua, **_REQUEST_HEADERS}


def _source_headers(source) -> dict:
    """Request headers for a source: the RSS set, or the JSON set for a
    json_api source."""
    if source.strategy is not None and source.strategy.name == "json_api":
        return {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "application/json, text/plain, */*;q=0.5",
            **{k: v for k, v in _REQUEST_HEADERS.items() if k != "Accept"},
        }
    return _headers()


def fetch_bytes(source) -> bytes:
    """GET a source's raw response body — the fixture-snapshot path.

    A fixture must be upstream's own bytes (CODING_STANDARDS.md), so this
    returns the body untouched and the caller parses it with the matching
    parse_*_bytes, which is the same mapping the live path uses.
    """
    return _fetch_response(source.url, _source_headers(source)).content


def fetch_rss(source, strategy) -> FetchOutcome:
    """Fetch and parse an RSS/Atom upstream into Items."""
    try:
        resp = _fetch_response(source.url, _source_headers(source))
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        return FetchOutcome(items=[], error=f"HTTP {status}" if status else f"fetch failed: {e}")
    except requests.RequestException as e:
        return FetchOutcome(items=[], error=f"fetch failed: {e}")
    return parse_feed_bytes(resp.content)


def parse_feed_bytes(data: bytes) -> FetchOutcome:
    """Parse feed bytes into Items — the mapping both live fetches and
    committed fixtures run through, so goldens test the real code path."""
    parsed = feedparser.parse(data)
    if parsed.bozo and not parsed.entries:
        return FetchOutcome(items=[], error=f"feed parse error: {parsed.bozo_exception}")

    # A well-formed channel with zero entries is a success-with-note, not
    # a failure: arXiv declares <skipDays> (weekends, holidays) and serves
    # a valid empty channel those days.
    note = None
    if not parsed.entries and ("skipdays" in parsed.feed or "day" in parsed.feed):
        rebuilt = parsed.feed.get("lastbuilddate") or parsed.feed.get("updated") or ""
        skip_days = re.findall(
            r"<day>\s*([^<]+?)\s*</day>",
            data.decode("utf-8", errors="replace"),
        )
        days = f" ({', '.join(skip_days)})" if skip_days else ""
        note = (
            "valid but empty channel — source declares skip days"
            f"{days}; channel lastBuildDate {rebuilt or 'unknown'}"
        )

    items = items_from_entries(parsed.entries)
    return FetchOutcome(items=items, note=note)


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


def fetch_json_api(source, strategy) -> FetchOutcome:
    """Fetch a JSON API upstream and hand the body to the parser."""
    try:
        resp = _fetch_response(source.url, _source_headers(source))
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        return FetchOutcome(items=[], error=f"HTTP {status}" if status else f"fetch failed: {e}")
    except requests.RequestException as e:
        return FetchOutcome(items=[], error=f"fetch failed: {e}")
    return parse_json_bytes(resp.content, strategy)


def _compose_description(entry, params: dict, fallback: str) -> str:
    """Render the strategy's ``description`` template, else pass the summary.

    ``{placeholders}`` name other strategy keys (which hold dot-paths), so
    the template stays data: HF renders ``▲ {upvotes} — {summary}``. If any
    placeholder resolves empty the plain summary wins — HF omits upvotes on
    some papers and "▲  — abstract" reads worse than the abstract.
    """
    template = params.get("description")
    if not template:
        return fallback
    values = {n: _dig(entry, params.get(n, "")) for n in re.findall(r"\{([^}]+)\}", template)}
    if any(v in (None, "") for v in values.values()):
        return fallback
    return template.format(**{n: str(v) for n, v in values.items()})


def parse_json_bytes(data: bytes, strategy) -> FetchOutcome:
    """Parse a JSON API body into Items — the mapping both the live fetch
    and committed JSON fixtures run through.

    The strategy block carries the source's whole shape: dot-paths for
    item/title/link/date/summary, an optional ``link_prefix`` (HF papers
    have no absolute URL upstream), and an optional ``description``
    template. Nothing about a particular API lives in this module.
    """
    params = strategy.params
    try:
        payload = json.loads(data)
    except ValueError as e:
        return FetchOutcome(items=[], error=f"invalid JSON: {e}")

    entries = _dig(payload, params["item"])
    if not isinstance(entries, list):
        return FetchOutcome(items=[], error=f"item path {params['item']!r} did not resolve to a list")

    items = []
    for entry in entries:
        title = _dig(entry, params["title"])
        ref = _dig(entry, params["link"])
        if not title or not ref:
            continue
        link = f"{params.get('link_prefix', '')}{ref}"
        summary = _dig(entry, params.get("summary", "")) or ""
        raw_date = str(_dig(entry, params["date"]) or "")
        published = None
        if raw_date:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                try:
                    published = datetime.strptime(raw_date, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
        items.append(Item(
            title=str(title).strip(),
            link=link,
            guid=link,
            published=published,
            published_raw=raw_date,
            description=_compose_description(entry, params, summary),
        ))
    return FetchOutcome(items=items)


def fetch(source) -> FetchOutcome:
    """Dispatch on the source's strategy."""
    name = source.strategy.name if source.strategy else "rss"
    if name == "json_api":
        return fetch_json_api(source, source.strategy)
    return fetch_rss(source, source.strategy)


def http_get(url: str) -> bytes:
    """GET a URL and return its body, retrying transient causes — the
    published store's transport (feeds.store.Transport). Raises
    requests.RequestException once the retry budget is exhausted."""
    return _fetch_response(url, _headers()).content


def last_build_date(data: bytes) -> str | None:
    """The predecessor channel's lastBuildDate, raw. Used to keep the
    freshness stamp truthful when a failed fetch re-emits the predecessor.
    feedparser 6.x maps <lastBuildDate> to the 'updated' key and exposes no
    'lastbuilddate' of its own."""
    stamp = feedparser.parse(data).feed.get("updated")
    return stamp or None
