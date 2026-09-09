"""Client for the NASA Images API (https://images-api.nasa.gov)."""

from dataclasses import dataclass, field
from typing import Any

import httpx

NASA_SEARCH_URL = "https://images-api.nasa.gov/search"
DEFAULT_LIMIT = 24
MAX_PAGE_SIZE = 100
REQUEST_TIMEOUT = 15.0

# The API refuses to serve any page reaching past its 10,000th result, answering
# 400 instead - even though the last page it will serve still advertises `next`.
MAX_RESULTS = 10_000


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


async def search_images(
    query: str,
    *,
    page: int = 1,
    limit: int = DEFAULT_LIMIT,
    client: httpx.AsyncClient | None = None,
) -> SearchPage:
    """Search NASA's image library and return one page of preview images.

    Each result is a dict with `title`, `url`, `description` and `nasa_id` keys.
    Pass `client` to reuse a connection pool, or to inject a transport in tests.
    """
    query = query.strip()
    page = max(1, page)
    page_size = min(max(1, limit), MAX_PAGE_SIZE)
    if not query:
        return SearchPage(page=page, page_size=page_size)

    params = {
        "q": query,
        "media_type": "image",
        "page": page,
        "page_size": page_size,
    }
    try:
        response = await _get(params, client)
        _raise_for_status(response)
        payload = response.json()
    except httpx.HTTPError as exc:
        raise NasaApiError(f"NASA image search failed: {exc}") from exc
    except ValueError as exc:
        raise NasaApiError("NASA image search returned malformed JSON") from exc

    return _parse_page(payload, page, page_size)


async def _get(
    params: dict[str, str | int], client: httpx.AsyncClient | None
) -> httpx.Response:
    if client is not None:
        return await client.get(NASA_SEARCH_URL, params=params)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as owned_client:
        return await owned_client.get(NASA_SEARCH_URL, params=params)


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
                "url": preview_url,
                "description": metadata.get("description") or "",
                "nasa_id": metadata.get("nasa_id") or "",
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
