import pytest
from nasa_api import NASAApiClient
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app import app

# Test NASA API client functionality
@pytest.fixture
def nasa_api_client():
    return NASAApiClient()

@pytest.fixture
def test_client():
    with TestClient(app) as client:
        yield client

@pytest.mark.asyncio
async def test_search_images(nasa_api_client):
    query = "galaxy"
    mock_result = [{"title": "Galaxy Image", "url": "http://example.com/galaxy.jpg"}]
    with patch.object(nasa_api_client, 'search_images', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_result
        result = await nasa_api_client.search_images(query)
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]['title'] == "Galaxy Image"
        assert result[0]['url'] == "http://example.com/galaxy.jpg"
