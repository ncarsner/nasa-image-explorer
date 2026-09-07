"""Client for the NASA Images API (https://images-api.nasa.gov)."""

from typing import Any

import httpx

NASA_SEARCH_URL = "https://images-api.nasa.gov/search"
DEFAULT_LIMIT = 24
REQUEST_TIMEOUT = 15.0


class NasaApiError(RuntimeError):
    """Raised when the NASA API is unreachable or returns something unusable."""


async def search_images(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, str]]:
    """Search NASA's image library and return up to `limit` preview images.

    Each result is a dict with `title`, `url`, `description` and `nasa_id` keys.
    Pass `client` to reuse a connection pool, or to inject a transport in tests.
    """
    query = query.strip()
    if not query:
        return []

    params = {"q": query, "media_type": "image"}
    try:
        response = await _get(params, client)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise NasaApiError(f"NASA image search failed: {exc}") from exc
    except ValueError as exc:
        raise NasaApiError("NASA image search returned malformed JSON") from exc

    return _parse_items(payload, limit)


async def _get(
    params: dict[str, str], client: httpx.AsyncClient | None
) -> httpx.Response:
    if client is not None:
        return await client.get(NASA_SEARCH_URL, params=params)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as owned_client:
        return await owned_client.get(NASA_SEARCH_URL, params=params)


def _parse_items(payload: Any, limit: int) -> list[dict[str, str]]:
    """Pull the preview image out of each search result, skipping any without one."""
    if not isinstance(payload, dict):
        raise NasaApiError("NASA image search returned an unexpected payload")

    items = payload.get("collection", {}).get("items") or []
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
