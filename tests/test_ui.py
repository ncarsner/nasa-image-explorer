"""End-to-end tests of the NiceGUI search page, driven by NiceGUI's User simulator."""

from unittest.mock import AsyncMock, patch

from nicegui import ui as nicegui_ui
from nicegui.testing import User

import ui as ui_module
from nasa_api import ImageAsset, NasaApiError, SearchPage

IMAGES = [
    {
        "title": "Galaxy Image",
        "url": "https://example.com/galaxy.jpg",
        "description": "A spiral galaxy.",
        "nasa_id": "PIA00001",
        "date_created": "2004-11-30T21:29:24Z",
        "photographer": "A. Skywatcher",
        "center": "JPL",
    }
]

ASSET = ImageAsset(
    nasa_id="PIA00001",
    renditions={
        "large": "https://example.com/galaxy~large.jpg",
        "orig": "https://example.com/galaxy~orig.jpg",
        "thumb": "https://example.com/galaxy~thumb.jpg",
    },
)


def patch_asset(**kwargs):
    return patch.object(ui_module, "get_asset", AsyncMock(**kwargs))


def sources(user: User, marker: str) -> list[str]:
    return [element.source for element in user.find(marker=marker).elements]


def result_page(**kwargs) -> SearchPage:
    return SearchPage(**{"results": IMAGES, "total_hits": 26858, **kwargs})


def patch_search(**kwargs):
    return patch.object(ui_module, "search_images", AsyncMock(**kwargs))


def is_enabled(user: User, marker: str) -> bool:
    (button,) = user.find(marker=marker).elements
    return button.enabled


async def test_page_starts_empty(user: User):
    await user.open("/")
    await user.should_see("NASA Image Explorer")
    await user.should_see("Enter a search term to get started.")
    await user.should_not_see("Previous")


async def test_search_renders_gallery(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    with patch_search(return_value=result_page()) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of 26,858 results for 'galaxy'.")

    await user.should_see("Galaxy Image")
    mock_search.assert_awaited_once_with("galaxy", page=1)


async def test_next_advances_a_page(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    pages = [
        result_page(page=1, has_next=True),
        result_page(page=2, has_prev=True, has_next=True),
    ]
    with patch_search(side_effect=pages) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of 26,858 results for 'galaxy'.")
        user.find(marker="next").click()
        await user.should_see("Showing 25-25 of 26,858 results for 'galaxy'.")

    assert mock_search.await_args_list[-1].kwargs["page"] == 2


async def test_prev_returns_to_the_previous_page(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    pages = [
        result_page(page=1, has_next=True),
        result_page(page=2, has_prev=True, has_next=True),
        result_page(page=1, has_next=True),
    ]
    with patch_search(side_effect=pages) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")
        user.find(marker="next").click()
        await user.should_see("Showing 25-25 of")
        user.find(marker="prev").click()
        await user.should_see("Showing 1-1 of")

    assert [call.kwargs["page"] for call in mock_search.await_args_list] == [1, 2, 1]


async def test_pager_is_disabled_at_the_ends(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    pages = [
        result_page(page=1, has_next=True),
        result_page(page=2, has_prev=True, has_next=False),
    ]
    with patch_search(side_effect=pages):
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")
        assert not is_enabled(user, "prev"), "prev is disabled on the first page"
        assert is_enabled(user, "next")

        user.find(marker="next").click()
        await user.should_see("Showing 25-25 of")
        assert is_enabled(user, "prev")
        assert not is_enabled(user, "next"), "next is disabled on the last page"


async def test_a_new_search_starts_over_at_page_one(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    pages = [
        result_page(page=1, has_next=True),
        result_page(page=2, has_prev=True, has_next=True),
        result_page(page=1, has_next=True),
    ]
    with patch_search(side_effect=pages) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")
        user.find(marker="next").click()
        await user.should_see("Showing 25-25 of")

        user.find(kind=nicegui_ui.input).type(" nebula")
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")

    last = mock_search.await_args_list[-1]
    assert last.kwargs["page"] == 1
    assert last.args[0].endswith("nebula")


async def test_search_reports_no_results(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("nonsense")
    with patch_search(return_value=SearchPage()):
        user.find(marker="search").click()
        await user.should_see("No images found for 'nonsense'.")
        await user.should_not_see("Previous")


async def test_search_reports_api_failure(user: User):
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    with patch_search(side_effect=NasaApiError("NASA is down")):
        user.find(marker="search").click()
        await user.should_see("Search failed. Please try again.")
        await user.should_see("NASA is down")


async def test_blank_search_is_not_sent(user: User):
    await user.open("/")
    with patch_search(side_effect=AssertionError("should not be called")):
        user.find(marker="search").click()
        await user.should_see("Enter a search term to get started.")


async def show_results(user: User) -> None:
    """Run a search so the gallery has a card to click."""
    await user.open("/")
    user.find(kind=nicegui_ui.input).type("galaxy")
    with patch_search(return_value=result_page()):
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")


async def test_clicking_a_card_opens_the_detail_view(user: User):
    await show_results(user)
    with patch_asset(return_value=ASSET) as mock_asset:
        user.find(marker="card").click()
        await user.should_see(marker="detail-image")
        await user.should_see("November 30, 2004")

    await user.should_see("A. Skywatcher")
    await user.should_see("JPL")
    await user.should_see("Open the original file")
    mock_asset.assert_awaited_once_with("PIA00001")
    # The dialog shows a bigger rendition than the grid thumbnail.
    assert sources(user, "detail-image") == ["https://example.com/galaxy~large.jpg"]


async def test_detail_view_falls_back_to_the_preview_when_the_lookup_fails(user: User):
    await show_results(user)
    with patch_asset(side_effect=NasaApiError("No AssetDB records")):
        user.find(marker="card").click()
        await user.should_see(marker="detail-image")
        await user.should_see("No AssetDB records")

    # The gallery is untouched and the dialog still shows what it has.
    await user.should_see("Showing 1-1 of")
    assert sources(user, "detail-image") == ["https://example.com/galaxy.jpg"]


async def test_closing_the_detail_view_discards_it(user: User):
    await show_results(user)
    with patch_asset(return_value=ASSET):
        user.find(marker="card").click()
        await user.should_see(marker="detail-image")
        user.find(marker="close-detail").click()
        await user.should_not_see(marker="detail-image")


async def test_reopening_the_detail_view_does_not_leak_elements(user: User):
    await show_results(user)
    with patch_asset(return_value=ASSET):
        for _ in range(3):
            user.find(marker="card").click()
            await user.should_see(marker="detail-image")
            assert len(sources(user, "detail-image")) == 1
            user.find(marker="close-detail").click()
            await user.should_not_see(marker="detail-image")
