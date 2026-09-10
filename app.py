"""FastAPI + NiceGUI entrypoint for the NASA Image Explorer."""

from fastapi import FastAPI, HTTPException, Query
from nicegui import ui

from nasa_api import (
    DEFAULT_LIMIT,
    MAX_PAGE_SIZE,
    NasaApiError,
    api_lifespan,
    search_images,
)
from ui import render_main_page

app = FastAPI(title="NASA Image Explorer", lifespan=api_lifespan)


@app.get("/api/search")
async def api_search(
    q: str = Query(..., min_length=1, description="Search term"),
    page: int = Query(1, ge=1, description="1-based page number"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_PAGE_SIZE),
    # The API wants four-digit years and answers 400 to anything else.
    year_start: int | None = Query(None, ge=1000, le=9999, description="Earliest year"),
    year_end: int | None = Query(None, ge=1000, le=9999, description="Latest year"),
    center: str | None = Query(None, description="NASA center code, e.g. JPL"),
) -> dict:
    """JSON view of the same search the UI performs."""
    try:
        found = await search_images(
            q,
            page=page,
            limit=limit,
            year_start=year_start,
            year_end=year_end,
            center=center,
        )
    except NasaApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "query": q,
        "filters": {
            "year_start": year_start,
            "year_end": year_end,
            "center": (center or "").strip().upper() or None,
        },
        "page": found.page,
        "page_size": found.page_size,
        "count": len(found.results),
        "total_hits": found.total_hits,
        "has_prev": found.has_prev,
        "has_next": found.has_next,
        "results": found.results,
    }


# Mounted last: NiceGUI claims "/", so any FastAPI route must be registered above.
ui.run_with(app, root=render_main_page, title="NASA Image Explorer", favicon="🚀")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
