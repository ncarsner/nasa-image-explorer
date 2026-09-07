"""Tests for the NASA API client and the /api/search endpoint."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

import app as app_module
from nasa_api import NASA_SEARCH_URL, NasaApiError, search_images

SAMPLE_PAYLOAD = {
    "collection": {
        "items": [
            {
                "data": [
                    {
                        "title": "Galaxy Image",
                        "description": "A spiral galaxy.",
                        "nasa_id": "PIA00001",
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
    }
}


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def test_client():
    with TestClient(app_module.app) as client:
        yield client


async def test_search_images_extracts_preview_images():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=SAMPLE_PAYLOAD)

    async with mock_client(handler) as client:
        results = await search_images("galaxy", client=client)

    assert seen["url"].startswith(NASA_SEARCH_URL)
    assert "q=galaxy" in seen["url"]
    assert "media_type=image" in seen["url"]
    # The item whose only link is `canonical` is skipped.
    assert results == [
        {
            "title": "Galaxy Image",
            "url": "https://example.com/galaxy.jpg",
            "description": "A spiral galaxy.",
            "nasa_id": "PIA00001",
        },
        {
            "title": "Untitled",
            "url": "https://example.com/nova.jpg",
            "description": "",
            "nasa_id": "PIA00003",
        },
    ]


async def test_search_images_respects_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_PAYLOAD)

    async with mock_client(handler) as client:
        results = await search_images("galaxy", limit=1, client=client)

    assert len(results) == 1


@pytest.mark.parametrize("query", ["", "   "])
async def test_search_images_skips_request_for_blank_query(query):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made for a blank query")

    async with mock_client(handler) as client:
        assert await search_images(query, client=client) == []


async def test_search_images_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError):
            await search_images("galaxy", client=client)


async def test_search_images_raises_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    async with mock_client(handler) as client:
        with pytest.raises(NasaApiError):
            await search_images("galaxy", client=client)


async def test_search_images_tolerates_empty_collection():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"collection": {}})

    async with mock_client(handler) as client:
        assert await search_images("galaxy", client=client) == []


def test_api_search_returns_results(test_client):
    images = [{"title": "Galaxy Image", "url": "https://example.com/galaxy.jpg"}]
    with patch.object(
        app_module, "search_images", AsyncMock(return_value=images)
    ) as mock_search:
        response = test_client.get("/api/search", params={"q": "galaxy", "limit": 5})

    assert response.status_code == 200
    assert response.json() == {"query": "galaxy", "count": 1, "results": images}
    mock_search.assert_awaited_once_with("galaxy", limit=5)


def test_api_search_rejects_blank_query(test_client):
    assert test_client.get("/api/search", params={"q": ""}).status_code == 422


def test_api_search_reports_upstream_failure(test_client):
    failure = AsyncMock(side_effect=NasaApiError("NASA is down"))
    with patch.object(app_module, "search_images", failure):
        response = test_client.get("/api/search", params={"q": "galaxy"})

    assert response.status_code == 502
    assert response.json()["detail"] == "NASA is down"
