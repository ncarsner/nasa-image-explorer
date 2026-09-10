"""Client for the NASA Images API (https://images-api.nasa.gov)."""

import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx

NASA_SEARCH_URL = "https://images-api.nasa.gov/search"
NASA_ASSET_URL = "https://images-api.nasa.gov/asset"
DEFAULT_LIMIT = 24
MAX_PAGE_SIZE = 100
REQUEST_TIMEOUT = 15.0

# The API refuses to serve any page reaching past its 10,000th result, answering
# 400 instead - even though the last page it will serve still advertises `next`.
MAX_RESULTS = 10_000

# Not every item is published in every size, so the detail view falls back
# through this order. `orig` sits mid-list because it can be a huge TIFF.
RENDITION_PREFERENCE = ("large", "medium", "orig", "small", "thumb")

CACHE_TTL = 300.0
CACHE_MAX_ENTRIES = 128

# One client for the life of the app, so connections and TLS sessions are reused.
# NiceGUI page handlers have no request to hang a dependency off, so this lives
# at module scope rather than in `app.state`.
_shared_client: httpx.AsyncClient | None = None

# Query, page, page size, then the filters - two searches that differ only by
# filter are different searches.
_CacheKey = tuple[str, int, int, int | None, int | None, str]
_cache: "OrderedDict[_CacheKey, tuple[float, SearchPage]]" = OrderedDict()

# Indirection so tests can wind the clock forward without sleeping.
_clock = time.monotonic


class NasaApiError(RuntimeError):
    """Raised when the NASA API is unreachable or returns something unusable."""


@dataclass(frozen=True, slots=True)
class SearchPage:
    """One page of search results, plus enough context to page through them."""

    results: list[dict[str, str]] = field(default_factory=list)
    total_hits: int = 0
    page: int = 1
    page_size: int = DEFAULT_LIMIT
    has_prev: bool = False
    has_next: bool = False

    @property
    def start_index(self) -> int:
        """1-based index of the first result on this page, or 0 when empty."""
        return (self.page - 1) * self.page_size + 1 if self.results else 0

    @property
    def end_index(self) -> int:
        """1-based index of the last result on this page, or 0 when empty.

        Approximate: results without a preview image are dropped from the page,
        so this can undercount when the API returns items we cannot display.
        """
        return self.start_index + len(self.results) - 1 if self.results else 0


@dataclass(frozen=True, slots=True)
class ImageAsset:
    """The renditions the API publishes for one image, keyed by size."""

    nasa_id: str
    renditions: dict[str, str] = field(default_factory=dict)

    @property
    def display_url(self) -> str | None:
        """The largest rendition worth showing inline, or None if there is none."""
        for size in RENDITION_PREFERENCE:
            if size in self.renditions:
                return self.renditions[size]
        return None

    @property
    def original_url(self) -> str | None:
        """The unresized master file, whatever its format."""
        return self.renditions.get("orig")


@asynccontextmanager
async def api_lifespan(_app: Any = None) -> AsyncIterator[None]:
    """Hold one HTTP client open for the life of the app; close it on shutdown."""
    global _shared_client

    _shared_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    try:
        yield
    finally:
        client, _shared_client = _shared_client, None
        clear_cache()
        await client.aclose()


def clear_cache() -> None:
    """Forget every cached search."""
    _cache.clear()


async def search_images(
    query: str,
    *,
    page: int = 1,
    limit: int = DEFAULT_LIMIT,
    year_start: int | None = None,
    year_end: int | None = None,
    center: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> SearchPage:
    """Search NASA's image library and return one page of preview images.

    Each result is a dict with `title`, `url`, `description` and `nasa_id` keys.
    `year_start`, `year_end` and `center` narrow the search; unset ones are left
    out of the request entirely, because the API answers 400 to an empty
    `year_start` and silently ignores an empty `center`.
    Pass `client` to reuse a connection pool, or to inject a transport in tests.
    """
    query = query.strip()
    page = max(1, page)
    page_size = min(max(1, limit), MAX_PAGE_SIZE)
    # The API matches centers case-insensitively, so folding here keeps searches
    # that differ only in case on a single cache entry.
    center = (center or "").strip().upper()
    if not query:
        return SearchPage(page=page, page_size=page_size)

    key = (query, page, page_size, year_start, year_end, center)
    cached = _cached(key)
    if cached is not None:
        return cached

    params: dict[str, str | int] = {
        "q": query,
        "media_type": "image",
        "page": page,
        "page_size": page_size,
    }
    if year_start is not None:
        params["year_start"] = year_start
    if year_end is not None:
        params["year_end"] = year_end
    if center:
        params["center"] = center
    try:
        response = await _get_url(NASA_SEARCH_URL, params, client)
        _raise_for_status(response)
        payload = response.json()
    except httpx.HTTPError as exc:
        raise NasaApiError(f"NASA image search failed: {exc}") from exc
    except ValueError as exc:
        raise NasaApiError("NASA image search returned malformed JSON") from exc

    found = _parse_page(payload, page, page_size)
    _remember(key, found)
    return found


async def get_asset(
    nasa_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> ImageAsset:
    """Look up every published rendition of one image, keyed by size.

    Sizes vary by item - plenty have no `large` - so read `display_url` rather
    than indexing `renditions` directly.
    """
    nasa_id = nasa_id.strip()
    if not nasa_id:
        return ImageAsset(nasa_id="")

    url = f"{NASA_ASSET_URL}/{quote(nasa_id, safe='')}"
    try:
        response = await _get_url(url, None, client)
        _raise_for_status(response)
        payload = response.json()
    except httpx.HTTPError as exc:
        raise NasaApiError(f"NASA asset lookup failed: {exc}") from exc
    except ValueError as exc:
        raise NasaApiError("NASA asset lookup returned malformed JSON") from exc

    return _parse_asset(nasa_id, payload)


async def _get_url(
    url: str,
    params: dict[str, str | int] | None,
    client: httpx.AsyncClient | None,
) -> httpx.Response:
    """Prefer an injected client, then the shared one, then a throwaway.

    The throwaway keeps the module usable from a script that never ran the
    lifespan, at the cost of a fresh connection per call.
    """
    client = client or _shared_client
    if client is not None:
        return await client.get(url, params=params)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as owned_client:
        return await owned_client.get(url, params=params)


def _cached(key: _CacheKey) -> SearchPage | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, found = entry
    if _clock() - stored_at >= CACHE_TTL:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return _copy(found)


def _remember(key: _CacheKey, found: SearchPage) -> None:
    """Cache `found` under `key`, evicting the least recently used entry."""
    _cache[key] = (_clock(), _copy(found))
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


def _copy(found: SearchPage) -> SearchPage:
    """Hand out a fresh result list, so a caller cannot edit what is cached."""
    return replace(found, results=list(found.results))


def _raise_for_status(response: httpx.Response) -> None:
    """Like `raise_for_status`, but surface the API's own explanation if it sent one.

    Paging past the result cap answers 400 with a `reason` worth showing the user.
    """
    if not response.is_error:
        return
    try:
        reason = response.json().get("reason")
    except ValueError:
        reason = None
    if reason:
        raise NasaApiError(str(reason))
    response.raise_for_status()


def _parse_page(payload: Any, page: int, page_size: int) -> SearchPage:
    if not isinstance(payload, dict):
        raise NasaApiError("NASA image search returned an unexpected payload")

    collection = payload.get("collection") or {}
    results = _parse_items(collection.get("items") or [], page_size)
    links = collection.get("links") or []
    has_more = any(link.get("rel") == "next" for link in links)
    return SearchPage(
        results=results,
        total_hits=_total_hits(collection),
        page=page,
        page_size=page_size,
        has_prev=page > 1,
        has_next=has_more and (page + 1) * page_size <= MAX_RESULTS,
    )


def _parse_asset(nasa_id: str, payload: Any) -> ImageAsset:
    if not isinstance(payload, dict):
        raise NasaApiError("NASA asset lookup returned an unexpected payload")

    renditions: dict[str, str] = {}
    for item in (payload.get("collection") or {}).get("items") or []:
        href = item.get("href")
        size = _rendition_size(str(href)) if href else None
        # The API lists sizes largest-first; keep the first href for each.
        if size and size not in renditions:
            renditions[size] = _https(str(href))
    return ImageAsset(nasa_id=nasa_id, renditions=renditions)


def _rendition_size(href: str) -> str | None:
    """`.../PIA07081~large.jpg` -> `large`. Files without a `~` (metadata.json) -> None."""
    filename = urlparse(href).path.rsplit("/", 1)[-1]
    if "~" not in filename:
        return None
    return filename.rsplit("~", 1)[-1].rsplit(".", 1)[0].lower() or None


def _https(url: str) -> str:
    """Asset hrefs come back as plain http, which browsers block on an https page."""
    parts = urlparse(url)
    if parts.scheme != "http":
        return url
    return urlunparse(parts._replace(scheme="https"))


def _total_hits(collection: dict[str, Any]) -> int:
    raw = (collection.get("metadata") or {}).get("total_hits")
    return raw if isinstance(raw, int) else 0


def _parse_items(items: list[Any], limit: int) -> list[dict[str, str]]:
    """Pull the preview image out of each search result, skipping any without one."""
    results: list[dict[str, str]] = []
    for item in items:
        preview_url = _preview_url(item.get("links") or [])
        if preview_url is None:
            continue
        metadata = (item.get("data") or [{}])[0]
        results.append(
            {
                "title": metadata.get("title") or "Untitled",
                "url": _https(preview_url),
                "description": metadata.get("description") or "",
                "nasa_id": metadata.get("nasa_id") or "",
                "date_created": metadata.get("date_created") or "",
                "photographer": metadata.get("photographer")
                or metadata.get("secondary_creator")
                or "",
                "center": metadata.get("center") or "",
            }
        )
        if len(results) >= limit:
            break
    return results


def _preview_url(links: list[dict[str, Any]]) -> str | None:
    for link in links:
        if link.get("rel") == "preview" and link.get("href"):
            return str(link["href"])
    return None
