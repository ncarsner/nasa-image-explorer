"""Tests for the NASA API client and the /api/search endpoint."""

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

import app as app_module
import nasa_api
from nasa_api import (
    NASA_ASSET_URL,
    NASA_SEARCH_URL,
    ImageAsset,
    NasaApiError,
    SearchPage,
    get_asset,
    search_images,
)

SAMPLE_ITEMS = [
    {
        "data": [
            {
                "title": "Galaxy Image",
                "description": "A spiral galaxy.",
                "nasa_id": "PIA00001",
                "date_created": "2004-11-30T21:29:24Z",
                "photographer": "A. Skywatcher",
                "center": "JPL",
            }
        ],
        "links": [
            {"rel": "alternate", "href": "https://example.com/large.jpg"},
            {"rel": "preview", "href": "https://example.com/galaxy.jpg"},
        ],
    },
    {
        "data": [{"title": "Video Only", "nasa_id": "PIA00002"}],
        "links": [{"rel": "canonical", "href": "https://example.com/vid.mp4"}],
    },
    {
        "data": [{"nasa_id": "PIA00003"}],
        "links": [{"rel": "preview", "href": "https://example.com/nova.jpg"}],
    },
]

GALAXY_RESULT = {
    "title": "Galaxy Image",
    "url": "https://example.com/galaxy.jpg",
    "description": "A spiral galaxy.",
    "nasa_id": "PIA00001",
    "date_created": "2004-11-30T21:29:24Z",
    "photographer": "A. Skywatcher",
    "center": "JPL",
}
NOVA_RESULT = {
    "title": "Untitled",
    "url": "https://example.com/nova.jpg",
    "description": "",
    "nasa_id": "PIA00003",
    "date_created": "",
    "photographer": "",
    "center": "",
}


def payload(*, items=None, total_hits=2, links=None) -> dict:
    collection: dict = {
        "items": SAMPLE_ITEMS if items is None else items,
        "metadata": {"total_hits": total_hits},
    }
    if links is not None:
        collection["links"] = [{"rel": rel, "href": "..."} for rel in links]
    return {"collection": collection}


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def responding(response: httpx.Response, seen: dict | None = None):
    """A MockTransport handler that always answers with `response`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["url"] = str(request.url)
            seen["params"] = parse_qs(urlparse(str(request.url)).query)
        return response

    return handler


@pytest.fixture
def test_client():
    with TestClient(app_module.app) as client:
        yield client


async def test_search_images_extracts_preview_images():
    seen: dict = {}
    handler = responding(httpx.Response(200, json=payload()), seen)

    async with mock_client(handler) as client:
        found = await search_images("galaxy", client=client)

    assert seen["url"].startswith(NASA_SEARCH_URL)
    assert seen["params"]["q"] == ["galaxy"]
    assert seen["params"]["media_type"] == ["image"]
    # The item whose only link is `canonical` is skipped.
    assert found.results == [GALAXY_RESULT, NOVA_RESULT]
    assert found.total_hits == 2


async def test_search_images_requests_the_asked_for_page():
    seen: dict = {}
    handler = responding(httpx.Response(200, json=payload()), seen)

    async with mock_client(handler) as client:
        found = await search_images("galaxy", page=3, limit=10, client=client)

    assert seen["params"]["page"] == ["3"]
    assert seen["params"]["page_size"] == ["10"]
    assert found.page == 3
    assert found.page_size == 10


@pytest.mark.parametrize("page", [0, -5])
async def test_search_images_clamps_page_to_the_first(page):
    seen: dict = {}
    handler = responding(httpx.Response(200, json=payload()), seen)

    async with mock_client(handler) as client:
        found = await search_images("galaxy", page=page, client=client)

    assert seen["params"]["page"] == ["1"]
    assert found.page == 1


async def test_search_images_respects_limit():
    handler = responding(httpx.Response(200, json=payload()))

    async with mock_client(handler) as client:
        found = await search_images("galaxy", limit=1, client=client)

    assert len(found.results) == 1


@pytest.mark.parametrize(
    ("links", "page", "has_prev", "has_next"),
    [
        (None, 1, False, False),  # a single page of results carries no links
        ([], 1, False, False),
        (["next"], 1, False, True),
        (["prev", "next"], 2, True, True),
        (["prev"], 4, True, False),
    ],
)
async def test_search_images_reports_neighbouring_pages(
    links, page, has_prev, has_next
):
    handler = responding(httpx.Response(200, json=payload(links=links)))

    async with mock_client(handler) as client:
        found = await search_images("galaxy", page=page, client=client)

    assert (found.has_prev, found.has_next) == (has_prev, has_next)


@pytest.mark.parametrize(
    ("page", "page_size", "has_next"),
    [
        (99, 100, True),  # the next page ends exactly on the cap
        (100, 100, False),  # the next page would end past it
        (415, 24, True),
        (416, 24, False),  # 417 * 24 == 10,008, which the API refuses
    ],
)
async def test_search_images_stops_at_the_api_result_cap(page, page_size, has_next):
    """The last page the API serves still advertises `next`, but asking for it 400s.

    The cap is on the *last* result a page reaches, not its first.
    """
    handler = responding(httpx.Response(200, json=payload(links=["prev", "next"])))

    async with mock_client(handler) as client:
        found = await search_images("galaxy", page=page, limit=page_size, client=client)

    assert found.has_prev is True
    assert found.has_next is has_next


@pytest.mark.parametrize("query", ["", "   "])
async def test_search_images_skips_request_for_blank_query(query):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made for a blank query")

    async with mock_client(handler) as client:
        found = await search_images(query, client=client)

    assert found == SearchPage(page=1, page_size=24)
    assert found.results == []


async def test_search_images_raises_on_http_error():
    handler = responding(httpx.Response(500, text="boom"))

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError):
            await search_images("galaxy", client=client)


async def test_search_images_surfaces_the_api_reason_for_a_rejected_page():
    reason = "Maximum number of search results have been displayed."
    handler = responding(httpx.Response(400, json={"reason": reason}))

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError, match="Maximum number"):
            await search_images("galaxy", page=500, client=client)


async def test_search_images_raises_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError):
            await search_images("galaxy", client=client)


async def test_search_images_tolerates_empty_collection():
    handler = responding(httpx.Response(200, json={"collection": {}}))

    async with mock_client(handler) as client:
        found = await search_images("galaxy", client=client)

    assert found.results == []
    assert found.total_hits == 0
    assert found.has_next is False


def test_search_page_reports_the_range_it_covers():
    found = SearchPage(results=[GALAXY_RESULT, NOVA_RESULT], page=3, page_size=24)
    assert (found.start_index, found.end_index) == (49, 50)


def test_search_page_range_is_zero_when_empty():
    found = SearchPage(page=3, page_size=24)
    assert (found.start_index, found.end_index) == (0, 0)


def test_api_search_returns_results(test_client):
    found = SearchPage(
        results=[GALAXY_RESULT],
        total_hits=26858,
        page=2,
        page_size=24,
        has_prev=True,
        has_next=True,
    )
    with patch.object(
        app_module, "search_images", AsyncMock(return_value=found)
    ) as mock_search:
        response = test_client.get(
            "/api/search", params={"q": "galaxy", "page": 2, "limit": 24}
        )

    assert response.status_code == 200
    assert response.json() == {
        "query": "galaxy",
        "page": 2,
        "page_size": 24,
        "count": 1,
        "total_hits": 26858,
        "has_prev": True,
        "has_next": True,
        "results": [GALAXY_RESULT],
    }
    mock_search.assert_awaited_once_with("galaxy", page=2, limit=24)


def test_api_search_defaults_to_the_first_page(test_client):
    with patch.object(
        app_module, "search_images", AsyncMock(return_value=SearchPage())
    ) as mock_search:
        test_client.get("/api/search", params={"q": "galaxy"})

    mock_search.assert_awaited_once_with("galaxy", page=1, limit=24)


@pytest.mark.parametrize("params", [{"q": ""}, {"q": "galaxy", "page": 0}])
def test_api_search_rejects_bad_input(test_client, params):
    assert test_client.get("/api/search", params=params).status_code == 422


def test_api_search_reports_upstream_failure(test_client):
    failure = AsyncMock(side_effect=NasaApiError("NASA is down"))
    with patch.object(app_module, "search_images", failure):
        response = test_client.get("/api/search", params={"q": "galaxy"})

    assert response.status_code == 502
    assert response.json()["detail"] == "NASA is down"


ASSET_HREFS = [
    "http://images-assets.nasa.gov/image/PIA00001/PIA00001~orig.jpg",
    "http://images-assets.nasa.gov/image/PIA00001/PIA00001~large.jpg",
    "http://images-assets.nasa.gov/image/PIA00001/PIA00001~small.jpg",
    "http://images-assets.nasa.gov/image/PIA00001/PIA00001~thumb.jpg",
    "http://images-assets.nasa.gov/image/PIA00001/metadata.json",
]


def asset_payload(hrefs=None) -> dict:
    items = [{"href": href} for href in (ASSET_HREFS if hrefs is None else hrefs)]
    return {"collection": {"items": items}}


async def test_get_asset_keys_renditions_by_size():
    seen: dict = {}
    handler = responding(httpx.Response(200, json=asset_payload()), seen)

    async with mock_client(handler) as client:
        asset = await get_asset("PIA00001", client=client)

    assert seen["url"] == f"{NASA_ASSET_URL}/PIA00001"
    assert asset.nasa_id == "PIA00001"
    # metadata.json carries no `~size`, so it is not a rendition.
    assert sorted(asset.renditions) == ["large", "orig", "small", "thumb"]


async def test_get_asset_upgrades_hrefs_to_https():
    """The API hands back plain http, which a browser blocks on an https page."""
    handler = responding(httpx.Response(200, json=asset_payload()))

    async with mock_client(handler) as client:
        asset = await get_asset("PIA00001", client=client)

    assert all(url.startswith("https://") for url in asset.renditions.values())


async def test_get_asset_escapes_the_nasa_id():
    seen: dict = {}
    handler = responding(httpx.Response(200, json=asset_payload([])), seen)

    async with mock_client(handler) as client:
        await get_asset("as11/40 5874", client=client)

    assert seen["url"] == f"{NASA_ASSET_URL}/as11%2F40%205874"


@pytest.mark.parametrize(
    ("sizes", "expected"),
    [
        (["large", "medium", "orig", "small", "thumb"], "large"),
        (["medium", "orig", "thumb"], "medium"),
        # Plenty of items publish no `large` at all.
        (["orig", "small", "thumb"], "orig"),
        (["thumb"], "thumb"),
    ],
)
async def test_display_url_falls_back_through_the_available_sizes(sizes, expected):
    hrefs = [f"http://example.com/image/X/X~{size}.jpg" for size in sizes]
    handler = responding(httpx.Response(200, json=asset_payload(hrefs)))

    async with mock_client(handler) as client:
        asset = await get_asset("X", client=client)

    assert asset.display_url == f"https://example.com/image/X/X~{expected}.jpg"


async def test_asset_without_renditions_has_no_urls():
    handler = responding(httpx.Response(200, json=asset_payload([])))

    async with mock_client(handler) as client:
        asset = await get_asset("X", client=client)

    assert asset.renditions == {}
    assert asset.display_url is None
    assert asset.original_url is None


async def test_get_asset_reports_the_original_file():
    handler = responding(httpx.Response(200, json=asset_payload()))

    async with mock_client(handler) as client:
        asset = await get_asset("PIA00001", client=client)

    assert asset.original_url == (
        "https://images-assets.nasa.gov/image/PIA00001/PIA00001~orig.jpg"
    )


@pytest.mark.parametrize("nasa_id", ["", "   "])
async def test_get_asset_skips_request_for_a_blank_id(nasa_id):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made for a blank id")

    async with mock_client(handler) as client:
        assert await get_asset(nasa_id, client=client) == ImageAsset(nasa_id="")


async def test_get_asset_surfaces_the_api_reason_for_a_missing_id():
    reason = "No AssetDB records for nasaid=NOT-A-REAL-ID"
    handler = responding(httpx.Response(404, json={"reason": reason}))

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError, match="No AssetDB records"):
            await get_asset("NOT-A-REAL-ID", client=client)


async def test_get_asset_raises_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError):
            await get_asset("PIA00001", client=client)


async def test_get_asset_rejects_an_unexpected_payload():
    handler = responding(httpx.Response(200, json=["not", "a", "collection"]))

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError):
            await get_asset("PIA00001", client=client)


class CountingHandler:
    """A MockTransport handler that records how many requests it answered."""

    def __init__(self, response: httpx.Response | None = None):
        self.response = response or httpx.Response(200, json=payload())
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self.response


async def test_repeat_search_is_served_from_cache():
    handler = CountingHandler()

    async with mock_client(handler) as client:
        first = await search_images("galaxy", client=client)
        second = await search_images("galaxy", client=client)

    assert handler.calls == 1
    assert first.results == second.results
    assert second.total_hits == first.total_hits


@pytest.mark.parametrize(
    "second_call",
    [
        {"query": "nebula", "page": 1, "limit": 24},
        {"query": "galaxy", "page": 2, "limit": 24},
        {"query": "galaxy", "page": 1, "limit": 10},
    ],
    ids=["query", "page", "limit"],
)
async def test_cache_keys_on_query_page_and_limit(second_call):
    handler = CountingHandler()

    async with mock_client(handler) as client:
        await search_images("galaxy", page=1, limit=24, client=client)
        await search_images(
            second_call["query"],
            page=second_call["page"],
            limit=second_call["limit"],
            client=client,
        )

    assert handler.calls == 2


async def test_cache_entry_expires_after_the_ttl(monkeypatch):
    handler = CountingHandler()
    now = 1000.0
    monkeypatch.setattr(nasa_api, "_clock", lambda: now)

    async with mock_client(handler) as client:
        await search_images("galaxy", client=client)
        now += nasa_api.CACHE_TTL - 1
        await search_images("galaxy", client=client)
        assert handler.calls == 1, "still fresh"

        now += 2
        await search_images("galaxy", client=client)

    assert handler.calls == 2


async def test_a_failed_search_is_not_cached():
    responses = [httpx.Response(500, text="boom"), httpx.Response(200, json=payload())]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError):
            await search_images("galaxy", client=client)
        found = await search_images("galaxy", client=client)

    assert found.results, "the retry reached the API rather than a cached failure"


async def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(nasa_api, "CACHE_MAX_ENTRIES", 3)
    handler = CountingHandler()

    async with mock_client(handler) as client:
        for term in ("one", "two", "three", "four"):
            await search_images(term, client=client)
        assert len(nasa_api._cache) == 3
        # "one" was evicted first, so asking again costs another request.
        await search_images("one", client=client)

    assert handler.calls == 5


async def test_a_caller_cannot_edit_what_is_cached():
    handler = CountingHandler()

    async with mock_client(handler) as client:
        first = await search_images("galaxy", client=client)
        first.results.clear()
        second = await search_images("galaxy", client=client)

    assert handler.calls == 1
    assert len(second.results) == 2


def test_lifespan_opens_one_client_and_closes_it():
    with TestClient(app_module.app):
        shared = nasa_api._shared_client
        assert shared is not None
        assert not shared.is_closed

    assert shared.is_closed
    assert nasa_api._shared_client is None


async def test_searches_fall_back_to_the_shared_client(monkeypatch):
    """A NiceGUI handler passes no client, so the shared one has to be found."""
    handler = CountingHandler()

    async with mock_client(handler) as shared:
        monkeypatch.setattr(nasa_api, "_shared_client", shared)
        found = await search_images("galaxy")

    assert handler.calls == 1
    assert found.results
