"""NiceGUI components and layout for the NASA Image Explorer."""

from nicegui import ui

from nasa_api import NasaApiError, search_images

GRID_CLASSES = "w-full gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"


def render_main_page() -> None:
    """Render the search page: a search bar above a responsive image gallery."""
    ui.page_title("NASA Image Explorer")

    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        ui.label("NASA Image Explorer").classes("text-3xl font-bold")
        with ui.row().classes("w-full items-center gap-2"):
            search_box = ui.input(
                placeholder="Search NASA images, e.g. 'Mars rover'"
            ).classes("grow")
            search_button = ui.button("Search", icon="search")
        status = ui.label("Enter a search term to get started.").classes(
            "text-sm text-gray-500"
        )
        spinner = ui.spinner(size="lg")
        spinner.set_visibility(False)
        gallery = ui.grid().classes(GRID_CLASSES)

    async def run_search() -> None:
        query = (search_box.value or "").strip()
        gallery.clear()
        if not query:
            status.set_text("Enter a search term to get started.")
            return

        search_button.disable()
        spinner.set_visibility(True)
        status.set_text(f"Searching for {query!r}...")
        try:
            images = await search_images(query)
        except NasaApiError as exc:
            status.set_text("Search failed. Please try again.")
            ui.notify(str(exc), type="negative")
            return
        finally:
            spinner.set_visibility(False)
            search_button.enable()

        if not images:
            status.set_text(f"No images found for {query!r}.")
            return

        status.set_text(f"Showing {len(images)} results for {query!r}.")
        with gallery:
            for image in images:
                _render_card(image)

    search_button.on_click(run_search)
    search_box.on("keydown.enter", run_search)


def _render_card(image: dict[str, str]) -> None:
    """Render one search result as an image card with its title underneath."""
    with ui.card().tight().classes("w-full"):
        ui.image(image["url"]).classes("w-full aspect-square object-cover")
        with ui.card_section():
            ui.label(image["title"]).classes("font-medium line-clamp-2")
        if image["description"]:
            ui.tooltip(image["description"][:300])
