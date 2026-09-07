"""End-to-end tests of the NiceGUI search page, driven by NiceGUI's User simulator."""

from unittest.mock import AsyncMock, patch

from nicegui import ui as nicegui_ui
from nicegui.testing import User

import ui as ui_module
from nasa_api import NasaApiError

IMAGES = [
    {
        "title": "Galaxy Image",
        "url": "https://example.com/galaxy.jpg",
        "description": "A spiral galaxy.",
        "nasa_id": "PIA00001",
    }
]


def patch_search(**kwargs):
    return patch.object(ui_module, "search_images", AsyncMock(**kwargs))


async def test_page_starts_empty(user: User):
    await user.open("/")
    await user.should_see("NASA Image Explorer")
    await user.should_see("Enter a search term to get started.")


async def test_search_renders_gallery(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    with patch_search(return_value=IMAGES) as mock_search:
        user.find(kind=nicegui_ui.button).click()
        await user.should_see("Showing 1 results for 'galaxy'.")

    await user.should_see("Galaxy Image")
    mock_search.assert_awaited_once_with("galaxy")


async def test_search_reports_no_results(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("nonsense")
    with patch_search(return_value=[]):
        user.find(kind=nicegui_ui.button).click()
        await user.should_see("No images found for 'nonsense'.")


async def test_search_reports_api_failure(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    with patch_search(side_effect=NasaApiError("NASA is down")):
        user.find(kind=nicegui_ui.button).click()
        await user.should_see("Search failed. Please try again.")
        await user.should_see("NASA is down")


async def test_blank_search_is_not_sent(user: User):
    await user.open("/")
    with patch_search(side_effect=AssertionError("should not be called")):
        user.find(kind=nicegui_ui.button).click()
        await user.should_see("Enter a search term to get started.")
