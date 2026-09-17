"""End-to-end tests of the NiceGUI search page, driven by NiceGUI's User simulator."""

from unittest.mock import AsyncMock, patch

import pytest
from nicegui.functions.navigate import History
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


@pytest.fixture(autouse=True)
def no_real_requests():
    """Fail any test whose UI reaches NASA without mocking the call first.

    NiceGUI swallows exceptions raised in event handlers, so a stand-in that
    raised would go unnoticed; this checks the stand-ins at teardown instead.
    """
    stand_ins = {"search_images": AsyncMock(), "get_asset": AsyncMock()}
    with (
        patch.object(ui_module, "search_images", stand_ins["search_images"]),
        patch.object(ui_module, "get_asset", stand_ins["get_asset"]),
    ):
        yield
    unmocked = {name: mock.await_args_list for name, mock in stand_ins.items()}
    assert not any(unmocked.values()), f"unmocked NASA calls: {unmocked}"


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
    user.find(marker="query").type("galaxy")
    with patch_search(return_value=result_page()) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of 26,858 results for 'galaxy'.")

    await user.should_see("Galaxy Image")
    mock_search.assert_awaited_once_with(
        "galaxy", page=1, year_start=None, year_end=None, center=""
    )


async def test_next_advances_a_page(user: User):
    await user.open("/")
    user.find(marker="query").type("galaxy")
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
    user.find(marker="query").type("galaxy")
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
    user.find(marker="query").type("galaxy")
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
    user.find(marker="query").type("galaxy")
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

        user.find(marker="query").type(" nebula")
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")

    last = mock_search.await_args_list[-1]
    assert last.kwargs["page"] == 1
    assert last.args[0].endswith("nebula")


async def test_search_reports_no_results(user: User):
    await user.open("/")
    user.find(marker="query").type("nonsense")
    with patch_search(return_value=SearchPage()):
        user.find(marker="search").click()
        await user.should_see("No images found for 'nonsense'.")
        await user.should_not_see("Previous")


async def test_search_reports_api_failure(user: User):
    await user.open("/")
    user.find(marker="query").type("galaxy")
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
    user.find(marker="query").type("galaxy")
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


async def test_filters_narrow_the_search(user: User):
    await user.open("/")
    user.find(marker="query").type("apollo")
    user.find(marker="year-start").type("1969")
    user.find(marker="year-end").type("1972")
    user.find(marker="center").type("jsc")
    with patch_search(return_value=result_page(total_hits=489)) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Filtered by 1969-1972, JSC.")

    assert mock_search.await_args_list[-1].kwargs == {
        "page": 1,
        "year_start": 1969,
        "year_end": 1972,
        "center": "JSC",
    }


async def test_changing_a_filter_reruns_the_search_from_page_one(user: User):
    await user.open("/")
    user.find(marker="query").type("apollo")
    pages = [
        result_page(page=1, has_next=True),
        result_page(page=2, has_prev=True, has_next=True),
        result_page(page=1, has_next=True, total_hits=798),
    ]
    with patch_search(side_effect=pages) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")
        user.find(marker="next").click()
        await user.should_see("Showing 25-25 of")

        user.find(marker="year-start").type("1969")
        await user.should_see("Showing 1-1 of 798 results")

    last = mock_search.await_args_list[-1]
    assert last.kwargs["page"] == 1, "a filter change starts over at page one"
    assert last.kwargs["year_start"] == 1969


async def test_one_sided_year_ranges_are_reported(user: User):
    await user.open("/")
    user.find(marker="query").type("apollo")
    user.find(marker="year-end").type("1975")
    with patch_search(return_value=result_page()) as mock_search:
        user.find(marker="search").click()
        await user.should_see("Filtered by up to 1975.")

    assert mock_search.await_args_list[-1].kwargs["year_start"] is None


async def test_an_unfiltered_search_says_nothing_about_filters(user: User):
    await user.open("/")
    user.find(marker="query").type("galaxy")
    with patch_search(return_value=result_page()):
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of 26,858 results for 'galaxy'.")
        await user.should_not_see("Filtered by")


async def test_filters_apply_to_an_empty_result_set(user: User):
    await user.open("/")
    user.find(marker="query").type("apollo")
    user.find(marker="center").type("SSC")
    with patch_search(return_value=result_page(results=[], total_hits=0)):
        user.find(marker="search").click()
        await user.should_see("No images found for 'apollo'. Filtered by SSC.")


def record_urls():
    """Capture every address-bar rewrite; `urls(mock)` lists them in order."""
    return patch.object(History, "replace", autospec=True)


def urls(mock_replace) -> list[str]:
    return [call.args[1] for call in mock_replace.call_args_list]


async def test_opening_a_search_url_loads_that_page(user: User):
    page_two = result_page(page=2, has_prev=True, has_next=True)
    with patch_search(return_value=page_two) as mock_search:
        await user.open("/?q=mars&page=2")
        await user.should_see("Showing 25-25 of 26,858 results for 'mars'.")

    mock_search.assert_awaited_once_with(
        "mars", page=2, year_start=None, year_end=None, center=""
    )
    assert user.find(marker="query").elements.pop().value == "mars"


async def test_filters_in_the_url_fill_the_form_and_the_search(user: User):
    with patch_search(return_value=result_page()) as mock_search:
        await user.open("/?q=apollo&year_start=1969&year_end=1972&center=jsc")
        await user.should_see("Filtered by 1969-1972, JSC.")

    assert mock_search.await_args_list[-1].kwargs == {
        "page": 1,
        "year_start": 1969,
        "year_end": 1972,
        "center": "JSC",
    }
    assert user.find(marker="year-start").elements.pop().value == 1969
    assert user.find(marker="center").elements.pop().value == "JSC"


@pytest.mark.parametrize("path", ["/", "/?q=", "/?q=%20%20&page=3"])
async def test_a_url_without_a_query_shows_the_empty_state(user: User, path):
    with patch_search() as mock_search:
        await user.open(path)
        await user.should_see("Enter a search term to get started.")

    mock_search.assert_not_awaited()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/?q=mars&page=abc", {"page": 1}),
        ("/?q=mars&page=-4", {"page": 1}),
        (
            "/?q=mars&year_start=69&year_end=soon",
            {"year_start": None, "year_end": None},
        ),
    ],
)
async def test_unusable_url_values_are_ignored(user: User, path, expected):
    with patch_search(return_value=result_page()) as mock_search:
        await user.open(path)
        await user.should_see("results for 'mars'")

    kwargs = mock_search.await_args_list[-1].kwargs
    assert {k: kwargs[k] for k in expected} == expected


async def test_searching_and_paging_update_the_address_bar(user: User):
    await user.open("/")
    user.find(marker="query").type("mars rover")
    pages = [result_page(page=1, has_next=True), result_page(page=2, has_prev=True)]
    with record_urls() as mock_replace, patch_search(side_effect=pages):
        user.find(marker="search").click()
        await user.should_see("Showing 1-1 of")
        user.find(marker="next").click()
        await user.should_see("Showing 25-25 of")

    assert urls(mock_replace) == ["/?q=mars+rover", "/?q=mars+rover&page=2"]


async def test_the_address_bar_carries_the_filters(user: User):
    await user.open("/")
    user.find(marker="query").type("apollo")
    user.find(marker="center").type("jsc")
    with record_urls() as mock_replace, patch_search(return_value=result_page()):
        user.find(marker="search").click()
        await user.should_see("Filtered by JSC.")

    assert urls(mock_replace)[-1] == "/?q=apollo&center=JSC"


async def test_clearing_the_search_clears_the_address_bar(user: User):
    with patch_search(return_value=result_page()):
        await user.open("/?q=mars")
        await user.should_see("results for 'mars'")

    user.find(marker="query").clear()
    with record_urls() as mock_replace:
        user.find(marker="search").click()
        await user.should_see("Enter a search term to get started.")

    assert urls(mock_replace) == ["/"]


async def test_reloading_the_address_bar_restores_the_search(user: User):
    await user.open("/")
    user.find(marker="query").type("nebula")
    pages = [result_page(page=1, has_next=True), result_page(page=2, has_prev=True)]
    with record_urls() as mock_replace, patch_search(side_effect=pages) as first:
        user.find(marker="year-start").type("2004")  # searches on its own
        await user.should_see("Showing 1-1 of")
        user.find(marker="next").click()
        await user.should_see("Showing 25-25 of")
    address_bar = urls(mock_replace)[-1]

    with patch_search(return_value=pages[1]) as reloaded:
        await user.open(address_bar)
        await user.should_see("Showing 25-25 of")

    assert reloaded.await_args == first.await_args_list[-1]
