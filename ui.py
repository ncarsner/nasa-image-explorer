"""NiceGUI components and layout for the NASA Image Explorer."""

from dataclasses import dataclass
from datetime import date

from nicegui import ui

from nasa_api import NasaApiError, SearchPage, get_asset, search_images

GRID_CLASSES = "w-full gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
PROMPT = "Enter a search term to get started."


@dataclass
class SearchState:
    """The search the gallery is currently showing."""

    query: str = ""
    page: int = 1


def render_main_page() -> None:
    """Render the search page: a search bar above a paged image gallery."""
    ui.page_title("NASA Image Explorer")
    state = SearchState()

    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        ui.label("NASA Image Explorer").classes("text-3xl font-bold")
        with ui.row().classes("w-full items-center gap-2"):
            search_box = ui.input(
                placeholder="Search NASA images, e.g. 'Mars rover'"
            ).classes("grow")
            search_button = ui.button("Search", icon="search").mark("search")
        status = ui.label(PROMPT).classes("text-sm text-gray-500")
        spinner = ui.spinner(size="lg")
        spinner.set_visibility(False)
        gallery = ui.grid().classes(GRID_CLASSES)
        with ui.row().classes("w-full justify-center items-center gap-4") as pager:
            prev_button = ui.button("Previous", icon="chevron_left").mark("prev")
            next_button = (
                ui.button("Next", icon="chevron_right").mark("next").props("icon-right")
            )
        pager.set_visibility(False)

    with ui.dialog() as detail, ui.card().classes("w-full max-w-3xl"):
        detail_body = ui.column().classes("w-full gap-2")
        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=detail.close).props("flat").mark("close-detail")

    def forget_detail(event) -> None:
        """Drop the detail elements once the dialog closes, so none accumulate."""
        if not event.value:
            detail_body.clear()

    detail.on_value_change(forget_detail)

    async def open_detail(image: dict[str, str]) -> None:
        """Open the dialog at once, then swap in the full-size asset when it lands."""
        detail_body.clear()
        with detail_body:
            ui.label(image["title"]).classes("text-xl font-bold")
            ui.spinner(size="lg")
        detail.open()

        url, original = image["url"], None
        try:
            asset = await get_asset(image["nasa_id"])
        except NasaApiError as exc:
            ui.notify(f"Showing the preview instead: {exc}", type="warning")
        else:
            url = asset.display_url or image["url"]
            original = asset.original_url

        if not detail.value:  # dismissed while the lookup was in flight
            return
        detail_body.clear()
        with detail_body:
            _render_detail(image, url, original)

    def show(found: SearchPage) -> None:
        """Paint one page of results and set the pager to match it."""
        gallery.clear()
        if not found.results:
            status.set_text(f"No images found for {state.query!r}.")
            pager.set_visibility(False)
            return

        status.set_text(
            f"Showing {found.start_index}-{found.end_index} "
            f"of {found.total_hits:,} results for {state.query!r}."
        )
        with gallery:
            for image in found.results:
                _render_card(image, open_detail)
        pager.set_visibility(True)
        prev_button.set_enabled(found.has_prev)
        next_button.set_enabled(found.has_next)

    async def load() -> None:
        """Fetch the current query and page, then hand the results to `show`."""
        search_button.disable()
        prev_button.disable()
        next_button.disable()
        spinner.set_visibility(True)
        status.set_text(f"Searching for {state.query!r}...")
        try:
            found = await search_images(state.query, page=state.page)
        except NasaApiError as exc:
            gallery.clear()
            pager.set_visibility(False)
            status.set_text("Search failed. Please try again.")
            ui.notify(str(exc), type="negative")
            return
        finally:
            spinner.set_visibility(False)
            search_button.enable()
        show(found)

    async def run_search() -> None:
        """Start a new search, which always begins at the first page."""
        state.query = (search_box.value or "").strip()
        state.page = 1
        if not state.query:
            gallery.clear()
            pager.set_visibility(False)
            status.set_text(PROMPT)
            return
        await load()

    async def turn_page(step: int) -> None:
        state.page = max(1, state.page + step)
        await load()

    search_button.on_click(run_search)
    search_box.on("keydown.enter", run_search)
    prev_button.on_click(lambda: turn_page(-1))
    next_button.on_click(lambda: turn_page(1))


def _render_card(image: dict[str, str], on_click) -> None:
    """Render one search result as a clickable image card with its title underneath."""
    card = ui.card().tight().classes("w-full cursor-pointer").mark("card")
    with card:
        ui.image(image["url"]).classes("w-full aspect-square object-cover")
        with ui.card_section():
            ui.label(image["title"]).classes("font-medium line-clamp-2")
        if image["description"]:
            ui.tooltip(image["description"][:300])
    card.on("click", lambda _, image=image: on_click(image))


def _render_detail(image: dict[str, str], url: str, original: str | None) -> None:
    """Fill the detail dialog: the biggest available rendition and its metadata."""
    ui.image(url).classes("w-full max-h-[60vh] object-contain").mark("detail-image")
    ui.label(image["title"]).classes("text-xl font-bold")

    facts = [
        ("Date", _format_date(image.get("date_created", ""))),
        ("Photographer", image.get("photographer", "")),
        ("Center", image.get("center", "")),
    ]
    for name, value in facts:
        if value:
            with ui.row().classes("gap-2 text-sm"):
                ui.label(f"{name}:").classes("text-gray-500")
                ui.label(value)

    if image["description"]:
        ui.label(image["description"]).classes("text-sm whitespace-pre-line")
    if original:
        ui.link("Open the original file", original, new_tab=True).classes("text-sm")


def _format_date(value: str) -> str:
    """`2004-11-30T21:29:24Z` -> `November 30, 2004`, or the raw value if unparsable."""
    try:
        return date.fromisoformat(value[:10]).strftime("%B %d, %Y")
    except ValueError:
        return value
