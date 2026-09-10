"""NiceGUI components and layout for the NASA Image Explorer."""

from dataclasses import dataclass
from datetime import date

from nicegui import ui

from nasa_api import NasaApiError, SearchPage, get_asset, search_images

GRID_CLASSES = "w-full gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
PROMPT = "Enter a search term to get started."

# Suggestions only - the API takes any center code, and rejects none of them.
CENTERS = (
    "ARC",
    "AFRC",
    "GRC",
    "GSFC",
    "HQ",
    "JPL",
    "JSC",
    "KSC",
    "LARC",
    "MSFC",
    "SSC",
)


@dataclass
class SearchState:
    """The search the gallery is currently showing."""

    query: str = ""
    page: int = 1
    year_start: int | None = None
    year_end: int | None = None
    center: str = ""


def render_main_page() -> None:
    """Render the search page: a search bar above a paged image gallery."""
    ui.page_title("NASA Image Explorer")
    state = SearchState()

    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        ui.label("NASA Image Explorer").classes("text-3xl font-bold")
        with ui.row().classes("w-full items-center gap-2"):
            search_box = (
                ui.input(placeholder="Search NASA images, e.g. 'Mars rover'")
                .classes("grow")
                .mark("query")
            )
            search_button = ui.button("Search", icon="search").mark("search")
        filters = ui.expansion("Filters", icon="filter_alt").classes("w-full")
        filters.mark("filters")
        with filters, ui.row().classes("w-full items-center gap-4"):
            year_start_box = _year_input("From year").mark("year-start")
            year_end_box = _year_input("To year").mark("year-end")
            center_box = (
                ui.input("Center", placeholder="e.g. JPL", autocomplete=list(CENTERS))
                .props("dense outlined clearable debounce=600")
                .classes("grow")
                .mark("center")
            )
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
            status.set_text(
                f"No images found for {state.query!r}.{_filters_text(state)}"
            )
            pager.set_visibility(False)
            return

        status.set_text(
            f"Showing {found.start_index}-{found.end_index} "
            f"of {found.total_hits:,} results for {state.query!r}."
            f"{_filters_text(state)}"
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
            found = await search_images(
                state.query,
                page=state.page,
                year_start=state.year_start,
                year_end=state.year_end,
                center=state.center,
            )
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
        """Start a new search, which always begins at the first page.

        Also how a filter change re-runs: page 1 is the only page whose numbering
        still means anything once the result set underneath it has changed.
        """
        state.query = (search_box.value or "").strip()
        state.year_start = _year(year_start_box.value)
        state.year_end = _year(year_end_box.value)
        state.center = (center_box.value or "").strip().upper()
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

    for box in (year_start_box, year_end_box, center_box):
        box.on_value_change(lambda: run_search())

    search_button.on_click(run_search)
    search_box.on("keydown.enter", run_search)
    prev_button.on_click(lambda: turn_page(-1))
    next_button.on_click(lambda: turn_page(1))


def _year_input(label: str) -> ui.number:
    """A year box. Debounced, so typing 1969 is one search rather than four."""
    return (
        ui.number(label, format="%d", min=1000, max=9999)
        .props("dense outlined clearable debounce=600")
        .classes("w-36")
    )


def _year(value) -> int | None:
    """`ui.number` hands back a float or None; the API wants a plain year."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _filters_text(state: SearchState) -> str:
    """A trailing ' Filtered by ...' clause, or nothing when no filter is set."""
    bits = []
    if state.year_start and state.year_end:
        bits.append(f"{state.year_start}-{state.year_end}")
    elif state.year_start:
        bits.append(f"{state.year_start} onwards")
    elif state.year_end:
        bits.append(f"up to {state.year_end}")
    if state.center:
        bits.append(state.center)
    return f" Filtered by {', '.join(bits)}." if bits else ""


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
