def render_main_page():
    # TODO: Add search bar for user input
    # TODO: On submit, call NASA API and display gallery
    # TODO: Render images in a responsive grid
    # TODO: Handle loading and error states
    ui.label("Welcome to the NASA Image Explorer!")
    ui.input(label="Search NASA Images", placeholder="Enter search term...").bind_value("search_query")
    ui.button("Search", on_click=lambda: search_images(ui.value("search_query")))